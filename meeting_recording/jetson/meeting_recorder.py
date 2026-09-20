#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pymongo"]
# ///
"""Standalone NAVI meeting recorder.

This is additive: it does not import or patch the working NAVI voice/assistant
stack. It watches `/dev/shm/navi/meeting_command.json` and records with an
external audio command, usually `arecord`.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from meeting_bus import clear_command, publish_status, read_command

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
AUDIO_DIR = DATA_DIR / "audio"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
OUTBOX_DIR = DATA_DIR / "outbox"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def meeting_id(started: dt.datetime) -> str:
    stamp = started.strftime("%Y%m%d_%H%M%S")
    suffix = hashlib.sha1(f"{stamp}-{time.time_ns()}".encode()).hexdigest()[:6]
    return f"meet_{stamp}_{suffix}"


def wav_duration_s(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes() / float(handle.getframerate())
    except Exception:
        return 0.0


def play_tone(kind: str) -> None:
    """Best-effort short cue. Never fail recording if audio feedback fails."""
    freq = "880" if kind == "start" else "440"
    cmd = os.environ.get(
        "NAVI_TONE_COMMAND",
        f"speaker-test -t sine -f {freq} -l 1 >/dev/null 2>&1",
    )
    try:
        subprocess.Popen(cmd, shell=True, start_new_session=True)
    except OSError:
        pass


def set_lights(color: str) -> None:
    command = os.environ.get("NAVI_LED_COMMAND")
    if not command:
        return
    try:
        subprocess.run([*shlex.split(command), color], timeout=2, check=False)
    except OSError:
        pass


def summarize_fallback(transcript: str) -> dict:
    cleaned = " ".join(transcript.split())
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    useful = [s for s in sentences if len(s.split()) >= 5]
    summary = " ".join(useful[:4]) or cleaned[:800] or "No speech was transcribed."
    actions = []
    for sentence in useful:
        lowered = sentence.lower()
        if any(word in lowered for word in ("todo", "action", "follow up", "next step")):
            actions.append({"task": sentence.strip(), "owner": None, "due": None, "done": False})
    return {
        "title": (useful[0][:70] if useful else "Recorded meeting").strip(),
        "summary": summary,
        "decisions": [],
        "actionItems": actions[:8],
    }


def transcribe_whisper_cpp(wav_path: Path) -> str | None:
    binary = os.environ.get("WHISPER_CPP_BIN")
    model = os.environ.get("WHISPER_CPP_MODEL")
    if not binary or not model:
        return None
    out_base = TRANSCRIPT_DIR / wav_path.stem
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        binary,
        "-m",
        model,
        "-f",
        str(wav_path),
        "-otxt",
        "-of",
        str(out_base),
    ]
    subprocess.run(cmd, check=True)
    txt = out_base.with_suffix(".txt")
    return txt.read_text(errors="replace") if txt.exists() else ""


def transcribe_faster_whisper(wav_path: Path) -> str | None:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    model_name = os.environ.get("FASTER_WHISPER_MODEL", "tiny.en")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(wav_path), beam_size=1, vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip()


def transcribe(wav_path: Path) -> str:
    for fn in (transcribe_whisper_cpp, transcribe_faster_whisper):
        try:
            text = fn(wav_path)
            if text is not None:
                return text.strip()
        except Exception as exc:
            print(f"[record] STT backend {fn.__name__} failed: {exc}", flush=True)
    return ""


SUMMARY_PROMPT = """Summarize this meeting transcript as compact JSON.
Return keys: title, summary, decisions, actionItems.
actionItems must be an array of objects with task, owner, due, done.

Transcript:
{transcript}
"""


def _parse_jsonish(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if isinstance(value, dict):
        return value
    return None


def summarize_ollama(transcript: str) -> dict | None:
    model = os.environ.get("OLLAMA_MODEL")
    if not model:
        return None
    prompt = SUMMARY_PROMPT.format(transcript=transcript[:12000])
    proc = subprocess.run(
        ["ollama", "run", model, prompt],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
        check=False,
    )
    return _parse_jsonish(proc.stdout)


def summarize_llama_cpp(transcript: str) -> dict | None:
    binary = os.environ.get("LLAMA_CPP_BIN")
    model = os.environ.get("LLAMA_CPP_MODEL")
    if not binary or not model:
        return None
    prompt = SUMMARY_PROMPT.format(transcript=transcript[:12000])
    proc = subprocess.run(
        [binary, "-m", model, "-p", prompt, "-n", "800", "--temp", "0.2"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=240,
        check=False,
    )
    return _parse_jsonish(proc.stdout)


def summarize(transcript: str) -> dict:
    for fn in (summarize_ollama, summarize_llama_cpp):
        try:
            value = fn(transcript)
            if value:
                return {
                    "title": str(value.get("title") or "Recorded meeting"),
                    "summary": str(value.get("summary") or ""),
                    "decisions": list(value.get("decisions") or []),
                    "actionItems": list(value.get("actionItems") or []),
                }
        except Exception as exc:
            print(f"[record] summary backend {fn.__name__} failed: {exc}", flush=True)
    return summarize_fallback(transcript)


def save_document(doc: dict) -> None:
    uri = os.environ.get("MONGODB_URI")
    if uri:
        from pymongo import MongoClient

        db_name = os.environ.get("MONGODB_DATABASE", "navi")
        collection = os.environ.get("MONGODB_COLLECTION", "meetingSummaries")
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client[db_name][collection].replace_one(
            {"meetingId": doc["meetingId"]}, doc, upsert=True
        )
        client.close()
        return
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    (OUTBOX_DIR / f"{doc['meetingId']}.json").write_text(json.dumps(doc, indent=2))


@dataclass
class ActiveRecording:
    meeting_id: str
    started_at: dt.datetime
    path: Path
    proc: subprocess.Popen


class Recorder:
    def __init__(self) -> None:
        self.active: ActiveRecording | None = None
        self.last_command_ts = None
        self.robot_id = os.environ.get("ROBOT_ID", "bracketbot-unknown")

    def start(self, phrase: str = "") -> None:
        if self.active:
            print("[record] already recording", flush=True)
            return
        started = now_utc()
        mid = meeting_id(started)
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        path = AUDIO_DIR / f"{mid}.wav"
        template = os.environ.get(
            "NAVI_RECORD_COMMAND", "arecord -q -f S16_LE -c 1 -r 16000 {path}"
        )
        cmd = shlex.split(template.format(path=str(path)))
        publish_status("recording", meetingId=mid, audioPath=str(path), phrase=phrase)
        set_lights("red")
        play_tone("start")
        proc = subprocess.Popen(cmd, start_new_session=True)
        self.active = ActiveRecording(mid, started, path, proc)
        print(f"[record] started {mid}: {path}", flush=True)

    def stop(self, phrase: str = "") -> None:
        if not self.active:
            print("[record] stop ignored; not recording", flush=True)
            return
        active = self.active
        self.active = None
        publish_status("processing", meetingId=active.meeting_id, audioPath=str(active.path))
        try:
            os.killpg(active.proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            active.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(active.proc.pid, signal.SIGKILL)
            active.proc.wait(timeout=2)
        play_tone("stop")
        set_lights("blue")
        self.process(active, phrase)

    def process(self, active: ActiveRecording, phrase: str = "") -> None:
        ended = now_utc()
        try:
            transcript = transcribe(active.path)
            summary = summarize(transcript)
            doc = {
                "meetingId": active.meeting_id,
                "robotId": self.robot_id,
                "title": summary["title"],
                "startedAt": iso(active.started_at),
                "endedAt": iso(ended),
                "durationSeconds": round(wav_duration_s(active.path), 2),
                "status": "ready",
                "recordingType": "audio_only",
                "audioPath": str(active.path),
                "transcript": transcript,
                "summary": summary["summary"],
                "decisions": summary["decisions"],
                "actionItems": summary["actionItems"],
                "stopPhrase": phrase,
            }
            save_document(doc)
            publish_status("ready", meetingId=active.meeting_id, title=doc["title"])
            print(f"[record] saved summary {active.meeting_id}", flush=True)
        except Exception as exc:
            publish_status("failed", meetingId=active.meeting_id, error=str(exc))
            set_lights("blue")
            raise

    def tick(self) -> None:
        cmd = read_command()
        if not cmd:
            return
        ts = cmd.get("ts")
        if ts == self.last_command_ts:
            return
        self.last_command_ts = ts
        command = str(cmd.get("command") or "").lower()
        phrase = str(cmd.get("phrase") or "")
        clear_command()
        if command == "start":
            self.start(phrase)
        elif command == "stop":
            self.stop(phrase)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", type=Path, default=Path(__file__).with_name(".env"))
    parser.add_argument("--manual", action="store_true", help="read commands from stdin")
    args = parser.parse_args()
    load_env(args.env)
    recorder = Recorder()
    publish_status("idle")
    set_lights("blue")
    print("[record] recorder ready", flush=True)
    try:
        if args.manual:
            for line in sys.stdin:
                word = line.strip().lower()
                if word in ("start", "record"):
                    recorder.start("manual")
                elif word in ("stop", "end"):
                    recorder.stop("manual")
                elif word in ("quit", "exit"):
                    break
        else:
            while True:
                recorder.tick()
                time.sleep(0.1)
    finally:
        if recorder.active:
            recorder.stop("shutdown")
        publish_status("idle")
        set_lights("blue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
