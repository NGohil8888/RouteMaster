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


async def load_overrides_into_settings() -> None:
    """Apply any persisted overrides onto the settings singleton at startup.

    Invalid values in data/settings.json are silently dropped - a corrupt
    file from a previous bad edit shouldn't keep the gateway from booting.
    """
    overrides = await store.read_json(SETTINGS_FILE, default={}) or {}
    for key, raw in overrides.items():
        if key not in EDITABLE_FIELDS:
            continue
        try:
            setattr(settings, key, _validate(key, raw))
        except (ValueError, TypeError, SettingsValidationError):
            # Bad persisted value - skip and let the env/default take over.
            continue


async def get_editable_settings() -> Dict[str, Any]:
    return {field: getattr(settings, field) for field in EDITABLE_FIELDS}


async def update_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    current = await store.read_json(SETTINGS_FILE, default={}) or {}
    for key, value in updates.items():
        if key not in EDITABLE_FIELDS:
            continue
        casted = _validate(key, value)
        setattr(settings, key, casted)
        current[key] = casted
    await store.write_json(SETTINGS_FILE, current)
    return await get_editable_settings()
