"""Dashboard-editable subset of gateway settings.

Only operational knobs that are safe to change while the gateway is running
are exposed here (retries, timeouts, cooldowns). Values are persisted to
data/settings.json and applied directly onto the live `settings` singleton,
so every module that reads `settings.<field>` picks up the change immediately
- no restart required.

Validation is enforced in `app.dashboard_api.SettingsIn` (Pydantic Field
constraints). This module intentionally trusts inputs that reach it via
the dashboard endpoint, but applies the same bounds defensively in case
runtime_config.update_settings is ever called from elsewhere (cron, tests).
"""

from typing import Any, Dict

from app import store
from app.config import settings

SETTINGS_FILE = "settings"

# field -> (caster, min, max). Bounds mirror app.dashboard_api.SettingsIn.
# Keep these in sync if either side changes.
EDITABLE_FIELDS = {
    "max_retries": (int, 1, 64),
    "account_cooldown_seconds": (float, 0.0, 86400.0),
    "health_check_interval_seconds": (float, 1.0, 3600.0),
    "request_timeout_seconds": (float, 1.0, 3600.0),
    "stream_timeout_seconds": (float, 1.0, 86400.0),
    "max_concurrent_requests_per_account": (int, 1, 10000),
}


# String-typed fields live separately from the numeric EDITABLE_FIELDS dict -
# they need a length cap instead of min/max, and no numeric coercion. The
# dashboard exposes these through the same /api/settings endpoint, but with
# different validation rules.
EDITABLE_STRING_FIELDS = {
    # (min_length, max_length)
    "gateway_admin_token": (8, 256),
}


class SettingsValidationError(ValueError):
    """Raised when a runtime settings update is out of bounds."""


def _validate(key: str, value: Any) -> Any:
    caster, low, high = EDITABLE_FIELDS[key]
    casted = caster(value)
    if casted < low or casted > high:
        raise SettingsValidationError(
            f"{key} must be between {low} and {high}, got {casted}"
        )
    return casted


def _validate_string(key: str, value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    low, high = EDITABLE_STRING_FIELDS[key]
    if len(text) < low:
        raise SettingsValidationError(
            f"{key} must be at least {low} characters, got {len(text)}"
        )
    if len(text) > high:
        raise SettingsValidationError(
            f"{key} must be at most {high} characters, got {len(text)}"
        )
    return text


async def load_overrides_into_settings() -> None:
    """Apply any persisted overrides onto the settings singleton at startup.

    Invalid values in data/settings.json are silently dropped - a corrupt
    file from a previous bad edit shouldn't keep the gateway from booting.
    """
    overrides = await store.read_json(SETTINGS_FILE, default={}) or {}
    for key, raw in overrides.items():
        if key in EDITABLE_FIELDS:
            try:
                setattr(settings, key, _validate(key, raw))
            except (ValueError, TypeError, SettingsValidationError):
                continue
        elif key in EDITABLE_STRING_FIELDS:
            try:
                setattr(settings, key, _validate_string(key, raw))
            except (ValueError, TypeError, SettingsValidationError):
                continue


async def get_editable_settings() -> Dict[str, Any]:
    out: Dict[str, Any] = {field: getattr(settings, field) for field in EDITABLE_FIELDS}
    # String fields are sensitive - return whether a token is *set* but never
    # the value itself, so /api/settings never leaks it to the dashboard.
    for field in EDITABLE_STRING_FIELDS:
        current = getattr(settings, field, None)
        out[field] = bool(current)
    return out


async def update_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    current = await store.read_json(SETTINGS_FILE, default={}) or {}
    for key, value in updates.items():
        if key in EDITABLE_FIELDS:
            casted = _validate(key, value)
            setattr(settings, key, casted)
            current[key] = casted
        elif key in EDITABLE_STRING_FIELDS:
            casted = _validate_string(key, value)
            setattr(settings, key, casted or None)
            # Persist as empty string when cleared so the file structure is
            # stable; load_overrides_into_settings will normalize to None.
            current[key] = casted
    await store.write_json(SETTINGS_FILE, current)
    return await get_editable_settings()
