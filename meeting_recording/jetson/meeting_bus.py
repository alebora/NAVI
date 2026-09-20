"""Small JSON-file bus for the standalone meeting recorder.

This deliberately mirrors the existing NAVI `/dev/shm` style without importing
or editing the working app modules.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

BUS_DIR = Path(os.environ.get("NAVI_MEETING_BUS_DIR", "/dev/shm/navi"))
COMMAND_PATH = BUS_DIR / "meeting_command.json"
STATUS_PATH = BUS_DIR / "meeting_status.json"


def _atomic_write(path: Path, value: dict) -> dict:
    BUS_DIR.mkdir(parents=True, exist_ok=True)
    value = dict(value)
    value["ts"] = time.time()
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value))
    tmp.replace(path)
    return value


def publish_command(command: str, **fields) -> dict:
    return _atomic_write(COMMAND_PATH, {"command": command, **fields})


def publish_status(state: str, **fields) -> dict:
    return _atomic_write(STATUS_PATH, {"state": state, **fields})


def read_command() -> dict | None:
    try:
        return json.loads(COMMAND_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def clear_command() -> None:
    try:
        COMMAND_PATH.unlink()
    except FileNotFoundError:
        pass
