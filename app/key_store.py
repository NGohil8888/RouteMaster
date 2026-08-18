"""Persisted API key storage.

Keys are stored in data/keys.json rather than only in .env, so they can be
added, edited, and removed from the dashboard at runtime without restarting
the gateway. On first run (no keys.json yet), existing keys from
OLLAMA_API_KEYS in .env are migrated in automatically so nothing is lost.
"""

import logging
import uuid
from typing import List, Optional

from pydantic import BaseModel

from app import store
from app.config import settings

logger = logging.getLogger(__name__)

KEYS_FILE = "keys"


class KeyRecord(BaseModel):
    id: str
    label: str
    api_key: str


async def load_keys() -> List[KeyRecord]:
    """Load all stored keys, migrating from .env on first run."""
    raw = await store.read_json(KEYS_FILE, default=None)

    if raw is None:
        bootstrapped = [
            KeyRecord(id=str(uuid.uuid4()), label=f"Account {i + 1}", api_key=key)
            for i, key in enumerate(settings.api_keys_list)
        ]
        await store.write_json(KEYS_FILE, [k.model_dump() for k in bootstrapped])
        if bootstrapped:
            logger.info(
                f"Migrated {len(bootstrapped)} key(s) from OLLAMA_API_KEYS into data/{KEYS_FILE}.json"
            )
        return bootstrapped

    return [KeyRecord(**item) for item in raw]


async def save_keys(keys: List[KeyRecord]) -> None:
    await store.write_json(KEYS_FILE, [k.model_dump() for k in keys])


async def add_key(label: str, api_key: str) -> KeyRecord:
    keys = await load_keys()
    record = KeyRecord(
        id=str(uuid.uuid4()),
        label=label.strip() if label and label.strip() else f"Account {len(keys) + 1}",
        api_key=api_key,
    )
    keys.append(record)
    await save_keys(keys)
    return record


async def update_key(
    key_id: str, label: Optional[str] = None, api_key: Optional[str] = None
) -> Optional[KeyRecord]:
    keys = await load_keys()
    for i, k in enumerate(keys):
        if k.id == key_id:
            updated = KeyRecord(
                id=k.id,
                label=label if label is not None and label.strip() else k.label,
                api_key=api_key if api_key is not None and api_key.strip() else k.api_key,
            )
            keys[i] = updated
            await save_keys(keys)
            return updated
    return None


async def delete_key(key_id: str) -> bool:
    keys = await load_keys()
    remaining = [k for k in keys if k.id != key_id]
    if len(remaining) == len(keys):
        return False
    await save_keys(remaining)
    return True
