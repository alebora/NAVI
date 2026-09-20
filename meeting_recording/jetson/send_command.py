#!/usr/bin/env python3
"""Send a manual start/stop command to the standalone meeting recorder."""

from __future__ import annotations

import argparse

from meeting_bus import publish_command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("start", "stop"))
    parser.add_argument("--phrase", default="")
    args = parser.parse_args()
    publish_command(args.command, phrase=args.phrase or f"manual {args.command}")
    print(f"sent {args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
