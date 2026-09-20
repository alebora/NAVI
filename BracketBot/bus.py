"""Dirt-simple JSON state bus for the NAVI processes, under /dev/shm/navi.

The three NAVI processes (voice, nfc_bridge, face) each own a topic and poll the
others. This is deliberately not BBOS IPC: BBOS topics have to be declared in a
daemon's constants.py and get a Writer lock, which is the wrong shape for
best-effort UI state, and it keeps NAVI from having to patch bbos to iterate.

Each topic is one small file, written atomically, so a reader never sees a
half-written document and you can debug the whole system with `cat`:

    cat /dev/shm/navi/face.json
    cat /dev/shm/navi/badge.json
"""

import json
import os
import time
from pathlib import Path

DIR = Path("/dev/shm/navi")


def publish(topic, **fields):
    """Overwrite `topic` with `fields` plus a fresh `ts`."""
    DIR.mkdir(parents=True, exist_ok=True)
    fields["ts"] = time.time()
    target = DIR / f"{topic}.json"
    tmp = target.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(fields))
    tmp.replace(target)          # atomic: readers see old or new, never partial
    return fields


def read(topic, default=None):
    """Latest value of `topic`, or `default` if it was never published."""
    try:
        return json.loads((DIR / f"{topic}.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def clear(topic):
    (DIR / f"{topic}.json").unlink(missing_ok=True)


class Latest:
    """Polls one topic and tells you only when a genuinely new value shows up.

    Used for treating a state file as an event stream, e.g. one badge tap should
    trigger one greeting no matter how often the face's render loop polls.
    """

    def __init__(self, topic):
        self.topic = topic
        # Adopt whatever is already published as the baseline, so a restart does
        # not replay the last tap. Anything that appears after this is new,
        # including the first value on a topic that does not exist yet.
        current = read(topic)
        self._ts = current.get("ts") if current else None

    def poll(self):
        """Return the value if it changed since the last poll, else None."""
        value = read(self.topic)
        if value is None:
            return None
        ts = value.get("ts")
        if ts == self._ts:
            return None
        self._ts = ts
        return value
