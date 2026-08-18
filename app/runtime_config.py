"""Dashboard-editable subset of gateway settings.

Only operational knobs that are safe to change while the gateway is running
are exposed here (retries, timeouts, cooldowns). Values are persisted to
data/settings.json and applied directly onto the live `settings` singleton,
so every module that reads `settings.<field>` picks up the change immediately
- no restart required.
"""

from typing import Any, Dict

from app import store
from app.config import settings

SETTINGS_FILE = "settings"

# field -> caster. Only these fields can be changed from the dashboard.
EDITABLE_FIELDS = {
    "max_retries": int,
    "account_cooldown_seconds": float,
    "health_check_interval_seconds": float,
    "request_timeout_seconds": float,
    "stream_timeout_seconds": float,
    "max_concurrent_requests_per_account": int,
}


async def load_overrides_into_settings() -> None:
    """Apply any persisted overrides onto the settings singleton at startup."""
    overrides = await store.read_json(SETTINGS_FILE, default={}) or {}
    for key, value in overrides.items():
        if key in EDITABLE_FIELDS:
            setattr(settings, key, EDITABLE_FIELDS[key](value))


async def get_editable_settings() -> Dict[str, Any]:
    return {field: getattr(settings, field) for field in EDITABLE_FIELDS}


async def update_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    current = await store.read_json(SETTINGS_FILE, default={}) or {}
    for key, value in updates.items():
        if key not in EDITABLE_FIELDS:
            continue
        casted = EDITABLE_FIELDS[key](value)
        setattr(settings, key, casted)
        current[key] = casted
    await store.write_json(SETTINGS_FILE, current)
    return await get_editable_settings()
