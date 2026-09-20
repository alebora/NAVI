# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "pyserial",
#   "pyyaml",
# ]
# ///
"""NAVI badge reader bridge: ESP32/PN532 over USB serial -> the `badge` topic.

    uv run nfc_bridge.py                 # normal: publish taps for face/voice
    uv run nfc_bridge.py --monitor       # just print what the ESP32 sends
    uv run nfc_bridge.py --enroll "Ada Lovelace"   # tap a card to name its owner

Two ESP32 firmwares are supported, detected automatically at connect:

  "check"  The original PlatformIO firmware. The host sends CHECK_NFC and it
           answers NONE, NFC_AUTH:<uid> (uid is on its internal whitelist) or
           NFC_DENIED:<uid>. We treat AUTH and DENIED the same, because the UID
           is all we need and badges.yaml decides who is who.
  "json"   esp32/navi_nfc/navi_nfc.ino, which streams JSON lines unprompted and
           can also read a name straight off an NDEF tag.

A username can arrive two ways, and the first one that works wins:
  1. The tag itself carries an NDEF text record (NTAG213/215/216 written by a
     phone). Only the "json" firmware can read this.
  2. badges.yaml maps the card's UID to a name. Use --enroll to add entries;
     this is the only option for MIFARE Classic badges and blank fobs.

The ESP32 is a CH340 board, so it is /dev/ttyESP32 (see
/etc/udev/rules.d/99-esp32-nfc.rules). It is deliberately NOT one of the
/dev/ttyACM* ports, which belong to the BracketBot baseboard and the two arms.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import serial
import serial.tools.list_ports
import yaml

import bus

SCRIPT_DIR = Path(__file__).parent
BADGES_PATH = SCRIPT_DIR / "badges.yaml"
ENROLL_TOPIC = "enroll"  # /dev/shm/navi/enroll.json — handoff when serial is busy
PORT_HINTS = ("/dev/ttyESP32",)
BAUD = 115200
# The CH340 has no serial number, so identify the board by its USB IDs.
USB_IDS = {(0x1A86, 0x7523), (0x1A86, 0x55D3), (0x10C4, 0xEA60)}


def find_port():
    """Preferred symlink first, then any recognised USB-serial bridge."""
    for hint in PORT_HINTS:
        if Path(hint).exists():
            return hint
    for p in serial.tools.list_ports.comports():
        if p.vid is not None and (p.vid, p.pid) in USB_IDS:
            return p.device
    return None


def load_badges():
    """UID (lowercase hex) -> display name."""
    if not BADGES_PATH.exists():
        return {}
    doc = yaml.safe_load(BADGES_PATH.read_text()) or {}
    entries = doc.get("badges", doc) or {}
    out = {}
    for uid, value in entries.items():
        uid = str(uid).lower().replace(":", "").replace(" ", "")
        out[uid] = value.get("name") if isinstance(value, dict) else str(value)
    return out


def save_badge(uid, name):
    doc = {}
    if BADGES_PATH.exists():
        doc = yaml.safe_load(BADGES_PATH.read_text()) or {}
    doc.setdefault("badges", {})[uid] = name
    BADGES_PATH.write_text(yaml.safe_dump(doc, sort_keys=True))


def port_in_use():
    """True if a long-running nfc_bridge (not --enroll/--monitor) holds the ESP32."""
    import os
    import subprocess

    me = os.getpid()
    try:
        out = subprocess.check_output(["pgrep", "-af", "nfc_bridge.py"], text=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    for line in out.splitlines():
        if "nfc_bridge.py" not in line or "pgrep" in line:
            continue
        if "--enroll" in line or "--monitor" in line:
            continue
        try:
            pid = int(line.split(None, 1)[0])
        except ValueError:
            continue
        if pid != me:
            return True
    return False


def request_enroll(name, timeout_s=90.0):
    """Ask the already-running bridge to enroll the next tap as `name`."""
    bus.publish(ENROLL_TOPIC, name=str(name).strip(), status="pending")
    print(
        f"[nfc] serial busy — asked the running bridge to enroll {name!r}. "
        f"Tap a card within {int(timeout_s)}s.",
        flush=True,
    )
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        state = bus.read(ENROLL_TOPIC) or {}
        if state.get("status") == "done" and state.get("name") == str(name).strip():
            uid = state.get("uid", "?")
            print(f"[nfc] saved {uid} -> {name} in {BADGES_PATH.name}", flush=True)
            bus.clear(ENROLL_TOPIC)
            return 0
        if state.get("status") == "error":
            print(f"[nfc] enroll failed: {state.get('detail', 'unknown')}", flush=True)
            bus.clear(ENROLL_TOPIC)
            return 1
        time.sleep(0.25)
    print("[nfc] enroll timed out waiting for a tap", flush=True)
    bus.clear(ENROLL_TOPIC)
    return 1


def pending_enroll_name():
    state = bus.read(ENROLL_TOPIC) or {}
    if state.get("status") == "pending":
        name = (state.get("name") or "").strip()
        return name or None
    return None


def open_serial(port):
    """Open without banging DTR/RTS, so we do not reset the ESP32 on connect."""
    s = serial.Serial()
    s.port = port
    s.baudrate = BAUD
    s.timeout = 0.2
    s.dtr = False
    s.rts = False
    s.open()
    return s


POLL_INTERVAL = 0.3        # how often to ask the "check" firmware


def detect_protocol(s):
    """Work out which firmware is on the board.

    The "json" firmware talks unprompted, so listen first. Only if it stays
    quiet do we poke it with CHECK_NFC.
    """
    deadline = time.time() + 2.5
    buf = b""
    while time.time() < deadline:
        buf += s.read(256)
        if b'{"t":' in buf:
            return "json", buf

    s.reset_input_buffer()
    s.write(b"CHECK_NFC\n")
    s.flush()
    reply = b""
    deadline = time.time() + 2.0
    while time.time() < deadline:
        reply += s.read(64)
        if b"NONE" in reply or b"NFC_" in reply:
            return "check", b""
    return None, buf


def read_json(s, buf):
    """Yield events from the streaming firmware."""
    buf += s.read(256)
    while b"\n" in buf:
        raw, buf = buf.split(b"\n", 1)
        raw = raw.strip()
        if not raw:
            continue
        try:
            yield json.loads(raw.decode("utf-8", "replace")), buf
        except json.JSONDecodeError:
            # ESP-IDF boot chatter is not JSON; show it, because that is how you
            # find out the PN532 is unhappy.
            print(f"[esp32] {raw.decode('utf-8', 'replace')}", flush=True)
            yield None, buf
    yield None, buf


def poll_check(s, raw=False):
    """Ask the original firmware once; return an event dict or None."""
    s.reset_input_buffer()
    s.write(b"CHECK_NFC\n")
    s.flush()

    reply = b""
    deadline = time.time() + 1.0
    while time.time() < deadline:
        reply += s.read(64)
        if b"\n" in reply:
            break
    text = reply.decode("utf-8", "replace").strip()
    if raw:
        print(f"[raw] CHECK_NFC -> {text!r}", flush=True)
    if not text:
        return None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("NFC_AUTH:") or line.startswith("NFC_DENIED:"):
            label, _, uid = line.partition(":")
            uid = uid.strip()
            if uid:
                return {"t": "tag", "uid": uid,
                        "whitelisted": label == "NFC_AUTH"}
        elif line == "NONE":
            return {"t": "gone"}
        elif line:
            print(f"[esp32] {line}", flush=True)
    return None


def events(port, raw=False):
    """Yield events from whichever firmware is attached, reconnecting as needed."""
    s, proto, buf = None, None, b""
    while True:
        if s is None:
            dev = port or find_port()
            if dev is None:
                print("[nfc] no ESP32 found; waiting...", flush=True)
                time.sleep(2)
                continue
            try:
                s = open_serial(dev)
            except (OSError, serial.SerialException) as e:
                print(f"[nfc] cannot open {dev}: {e}", flush=True)
                time.sleep(2)
                continue
            proto, buf = detect_protocol(s)
            if proto is None:
                print(f"[nfc] {dev} is not answering as either firmware; retrying",
                      flush=True)
                s.close()
                s = None
                time.sleep(2)
                continue
            print(f"[nfc] connected to {dev} @ {BAUD}, {proto!r} firmware",
                  flush=True)

        try:
            if proto == "check":
                event = poll_check(s, raw)
                if event:
                    yield event
                time.sleep(POLL_INTERVAL)
            else:
                for event, buf in read_json(s, buf):
                    if event:
                        yield event
        except (OSError, serial.SerialException) as e:
            print(f"[nfc] link lost: {e}", flush=True)
            s.close()
            s, proto, buf = None, None, b""


def main():
    ap = argparse.ArgumentParser(description="NAVI NFC serial bridge")
    ap.add_argument("--port", help="serial device (default: autodetect)")
    ap.add_argument("--monitor", action="store_true", help="print only, do not publish")
    ap.add_argument("--raw", action="store_true", help="show every serial reply, even NONE")
    ap.add_argument("--enroll", metavar="NAME", help="assign the next tapped card to NAME")
    args = ap.parse_args()

    # If assistant already owns the ESP32, --enroll hands off via /dev/shm/navi/enroll.json
    # instead of failing on a busy serial port (the usual "I enrolled but…" failure).
    if args.enroll and port_in_use():
        return request_enroll(args.enroll)

    badges = load_badges()
    if args.enroll:
        print(f"[nfc] enrolling as {args.enroll!r} — tap a card now", flush=True)
    else:
        print(f"[nfc] {len(badges)} known badge(s); waiting for taps", flush=True)

    present = None      # UID currently sitting on the reader, so one tap = one event

    for msg in events(args.port, raw=args.raw):
        kind = msg.get("t")

        if kind == "boot":
            print(f"[nfc] ESP32 up: PN532 v{msg.get('pn532')} over {msg.get('iface')}", flush=True)
            continue
        if kind == "err":
            print(f"[nfc] ESP32 error: {msg.get('msg')}", flush=True)
            continue
        if kind == "gone":
            if present is not None:
                present = None
                if not (args.monitor or args.enroll):
                    bus.publish("badge_present", present=False)
            continue
        if kind != "tag":
            continue

        uid = str(msg.get("uid", "")).lower().replace(":", "").replace(" ", "")
        if not uid or uid == present:
            continue
        present = uid

        if args.enroll:
            save_badge(uid, args.enroll)
            print(f"[nfc] saved {uid} -> {args.enroll} in {BADGES_PATH.name}", flush=True)
            return 0

        # Remote --enroll while this process holds the serial port.
        enroll_as = pending_enroll_name()
        if enroll_as:
            save_badge(uid, enroll_as)
            bus.publish(ENROLL_TOPIC, name=enroll_as, uid=uid, status="done")
            print(f"[nfc] enrolled {uid} -> {enroll_as} in {BADGES_PATH.name}", flush=True)
            # Also publish as a known tap so navigate waiting on verify can proceed.
            bus.publish("badge", uid=uid, name=enroll_as, known=True)
            bus.publish("badge_present", present=True)
            continue

        # Always re-read so an enroll in another terminal is picked up before this tap.
        badges = load_badges()

        # Tag-provided name beats the registry: a badge that says who it is is
        # more trustworthy than a mapping someone typed weeks ago.
        name = (msg.get("name") or "").strip() or badges.get(uid)
        known = bool(name)
        if not known:
            name = "guest"

        print(f"[nfc] tap {uid} -> {name}{'' if known else ' (unregistered)'}", flush=True)
        if not args.monitor:
            bus.publish("badge", uid=uid, name=name, known=known)
            bus.publish("badge_present", present=True)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[nfc] stopped", flush=True)
