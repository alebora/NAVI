#!/usr/bin/env python3
"""Record the BracketBot OS processed mic stream to a WAV file.

This subscribes to the existing `mic.audio` shared-memory stream instead of
opening the USB microphone directly. It is intentionally standalone so the
meeting recorder can capture audio without interrupting the working assistant.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
import wave
from pathlib import Path

import numpy as np
from bbos import Reader

DEFAULT_RATE = 16_000

running = True


def _handle_signal(_signum, _frame) -> None:
    global running
    running = False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--stream", default="mic.audio")
    parser.add_argument("--rate", type=int, default=DEFAULT_RATE)
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    args.path.parent.mkdir(parents=True, exist_ok=True)
    with Reader(args.stream, keeptime=False) as reader, wave.open(str(args.path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(args.rate)

        while running:
            if not reader.ready():
                time.sleep(0.01)
                continue
            audio = reader.data["audio"]
            pcm = np.asarray(audio, dtype=np.int16).reshape(-1)
            wav.writeframes(pcm.tobytes())
            wav._file.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
