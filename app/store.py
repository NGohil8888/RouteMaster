"""Simple JSON-file backed persistence for dashboard-managed data (API keys, runtime settings).

Not a database - this is a single-user local gateway, so a small JSON file per
concern is enough, and it keeps the project dependency-free.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

_lock = asyncio.Lock()


def _path(name: str) -> Path:
    return DATA_DIR / f"{name}.json"


async def read_json(name: str, default: Any = None) -> Any:
    """Read a JSON file by name. Returns `default` if the file doesn't exist or is corrupt."""
    path = _path(name)
    async with _lock:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default


async def write_json(name: str, data: Any) -> None:
    """Write a JSON file by name, atomically (write to temp file, then replace)."""
    path = _path(name)
    tmp_path = path.with_suffix(".tmp")
    async with _lock:
        tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp_path.replace(path)
