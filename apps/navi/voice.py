# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "bbos",
#   "google-genai",
#   "python-dotenv",
#   "numpy",
#   "soxr",
#   "pyyaml",
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/bbos", editable = true }
# ///
"""NAVI voice: talk to the robot through Gemini Live; it answers "where is X?"
for the whole venue and drives to the places it has actually mapped.

  uv run voice.py
  uv run voice.py --no-nav     # talk only, never drives (safe for first test)

Two separate kinds of knowledge, deliberately kept apart:
  venue.yaml   — every room on all 7 floors (floor, room number, directions).
                 Transcribed from the official floor maps. NAVI can TALK about
                 all of it, on any floor.
  places.yaml  — SLAM poses saved with `places.py save <name>`. Only these can
                 actually be DRIVEN to, and only on the floor the robot mapped.

Needs GEMINI_API_KEY in ./.env (or ~/bbapps/greeter/.env).
Audio I/O and the Gemini loop follow ~/bbapps/greeter/main.py.
"""
import argparse
import asyncio
import math
import os
import queue
import threading
import time
from pathlib import Path

import numpy as np
import soxr
from dotenv import load_dotenv
from google import genai
from google.genai import types

from bbos import Config, Reader, Type, Writer

import bus
import places
import venue

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")
load_dotenv(Path.home() / "bbapps" / "greeter" / ".env")

CFG = Config("speaker")
CHUNK = CFG.chunk_size
BBOS_RATE = Config("mic").sample_rate
GEMINI_RATE = 24000                   # Gemini outputs 24kHz PCM16
JITTER_BUFFER_CHUNKS = 4

stop_event = threading.Event()
interrupt_flag = threading.Event()
mic_queue = queue.Queue(maxsize=50)
speaker_queue = queue.Queue(maxsize=500)

_face_state = None


def set_face(state):
    """Tell face.py what to show. Best-effort: no face running is not an error."""
    global _face_state
    if state == _face_state:
        return
    _face_state = state
    try:
        bus.publish("face", state=state)
    except OSError:
        pass

SYSTEM_PROMPT = """You are NAVI, a friendly indoor guide robot at Hack the North, in the
E5 and PSE (E7) engineering buildings at the University of Waterloo. People talk to you to
find their way around, and you can physically drive and lead them to places you have mapped.

You have two different abilities, and you must not confuse them:
1. TELLING someone where a place is. Works for every room on all 7 floors.
   Call find_place with whatever they said, then say the answer out loud.
2. DRIVING someone there. Only works for the places in list_places, because those are
   the only spots the robot has a saved position for, and only on the floor it mapped.

How to handle requests:
- "Where is X?" / "How do I get to X?" -> call find_place, then answer in one or two
  sentences with the floor and room number. Do not drive unless they ask you to take them.
- "Take me to X" / "Lead me to X" -> call find_place first. If X is also in list_places,
  say one short sentence like "Sure, follow me to judging" and call navigate_to. If X is
  NOT a saved place, give the walking directions instead and say you cannot drive there
  yet, for example because it is on another floor and you cannot use the elevator.
- If you cannot tell which place someone means, ask one short clarifying question.
- If someone says stop, wait, or hold on, call stop_navigation immediately.
- "Where are we?" / "Where am I?" -> call where_am_i.
- When you receive a message starting with [nav], tell the person what happened in one sentence.

Always speak naturally: 1-2 short sentences, no lists, no markdown, no room numbers read
digit by digit. Say "room seventy-three sixty-three" style phrasing when it sounds better."""


# ── Navigation (runs places.go on a worker thread) ───────────────────
class Navigator:
    def __init__(self, enabled, notify):
        self.enabled = enabled
        self.notify = notify          # callable(str) -> tells Gemini what happened
        self.cancel = threading.Event()
        self.thread = None

    @property
    def busy(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, place):
        known = places.load_places()
        if place not in known:
            return {"error": f"unknown place '{place}'", "known_places": list(known)}
        if not self.enabled:
            return {"status": "navigation disabled (--no-nav); pretend you would go", "place": place}
        if self.busy:
            self.stop()
            self.thread.join(timeout=2)
        self.cancel = threading.Event()
        self.thread = threading.Thread(target=self._run, args=(place, self.cancel), daemon=True)
        self.thread.start()
        return {"status": "started", "place": place}

    def _run(self, place, cancel):
        try:
            ok = places.go(place, cancel=cancel, on_status=lambda s: print(f"[nav] {s}", flush=True))
            if cancel.is_set():
                return
            self.notify(f"[nav] Arrived at {place}." if ok
                        else f"[nav] Could not reach {place}; the path may be blocked.")
        except Exception as e:
            print(f"[nav] error: {e}", flush=True)
            self.notify(f"[nav] Navigation problem: {e}")

    def stop(self):
        self.cancel.set()
        return {"status": "stopped"}


# ── Audio I/O thread (mic.audio -> mic_queue, speaker_queue -> speaker.audio) ──
def audio_io_loop():
    playing = False
    with Reader("mic.audio") as r_mic, \
         Writer("speaker.audio", Type("speaker_audio")) as w_spk:
        while not w_spk.ready():
            pass
        for _ in range(3):
            with w_spk.buf() as b:
                b["audio"] = np.zeros((CHUNK, CFG.channels), dtype=np.int16)
        print("[audio] running", flush=True)

        while not stop_event.is_set():
            did_work = False
            if r_mic.ready():
                did_work = True
                audio = r_mic.data["audio"].copy()
                try:
                    mic_queue.put_nowait(audio)
                except queue.Full:
                    try: mic_queue.get_nowait()
                    except queue.Empty: pass
                    mic_queue.put_nowait(audio)

            if w_spk._update():
                did_work = True
                if interrupt_flag.is_set():
                    while not speaker_queue.empty():
                        try: speaker_queue.get_nowait()
                        except queue.Empty: break
                    interrupt_flag.clear()
                    playing = False
                if not playing and speaker_queue.qsize() >= JITTER_BUFFER_CHUNKS:
                    playing = True
                chunk = np.zeros(CHUNK, dtype=np.int16)
                if playing:
                    try:
                        chunk = speaker_queue.get_nowait()
                    except queue.Empty:
                        pass
                with w_spk.buf() as b:
                    b["audio"] = chunk.reshape(-1, CFG.channels)

            if not did_work:
                time.sleep(0.001)


# ── Gemini Live session ───────────────────────────────────────────────
TOOLS = [
    types.FunctionDeclaration(
        name="find_place",
        description=(
            "Look up where somewhere is in the venue: which floor, which building, the room "
            "number and how to walk there. Covers every room on all 7 floors. Use this for any "
            "'where is', 'how do I get to' or 'take me to' request, before deciding to drive. "
            "Accepts whatever the person said, including vague phrasing like 'a bathroom', "
            "'somewhere to sleep' or 'I need a sensor'."
        ),
        behavior="NON_BLOCKING",
        parameters={"type": "object",
                    "properties": {"query": {"type": "string",
                                             "description": "What the person is looking for, in their words"}},
                    "required": ["query"]},
    ),
    types.FunctionDeclaration(
        name="navigate_to",
        description=(
            "Physically drive to a saved place and lead the person there. Only works for names "
            "returned by list_places. Call find_place first to confirm what they mean."
        ),
        behavior="NON_BLOCKING",
        parameters={"type": "object",
                    "properties": {"place": {"type": "string",
                                             "description": "Exact saved place name from list_places"}},
                    "required": ["place"]},
    ),
    types.FunctionDeclaration(
        name="list_places",
        description="List the saved places NAVI can actually drive to right now.",
        behavior="NON_BLOCKING",
        parameters={"type": "object", "properties": {}},
    ),
    types.FunctionDeclaration(
        name="where_am_i",
        description="Report the robot's current position and the nearest saved place.",
        behavior="NON_BLOCKING",
        parameters={"type": "object", "properties": {}},
    ),
    types.FunctionDeclaration(
        name="stop_navigation",
        description="Stop moving immediately.",
        behavior="NON_BLOCKING",
        parameters={"type": "object", "properties": {}},
    ),
]


def find_place(query):
    """Venue lookup, annotated with whether the robot can actually drive to each hit."""
    saved = set(places.load_places())
    hits = venue.search(query, limit=3)
    if not hits:
        return {"found": False,
                "query": query,
                "hint": "No venue match. Ask them to rephrase, or offer the saved places.",
                "saved_places": sorted(saved)}
    return {"found": True,
            "matches": [venue.as_dict(p, navigable=p.get("name") in saved) for p in hits],
            "saved_places": sorted(saved)}


def where_am_i():
    """Current SLAM pose plus the closest saved place, if any."""
    try:
        x, y, yaw = places.read_pose()
    except Exception as e:
        return {"error": f"no SLAM pose: {e}"}
    nearest, best = None, None
    for name, p in places.load_places().items():
        d = math.hypot(p["x"] - x, p["y"] - y)
        if best is None or d < best:
            nearest, best = name, d
    result = {"x": round(x, 2), "y": round(y, 2), "heading_deg": round(math.degrees(yaw), 1)}
    if nearest is not None:
        result["nearest_saved_place"] = nearest
        result["metres_away"] = round(best, 1)
    return result


async def gemini_session(args):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[!] GEMINI_API_KEY not set (put it in apps/navi/.env)", flush=True)
        return
    client = genai.Client(api_key=api_key)
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=args.voice))),
        system_instruction=types.Content(parts=[types.Part(
            text=SYSTEM_PROMPT
            + "\n\nVenue index (use find_place for room numbers and directions):\n"
            + venue.index_for_prompt()
            + f"\n\nPlaces you can actually DRIVE to right now: "
              f"{', '.join(places.load_places()) or 'none saved yet'}.")]),
        tools=[types.Tool(function_declarations=TOOLS)],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    loop = asyncio.get_running_loop()
    session_ref = {"s": None}

    def notify(text):
        """Called from the nav thread: inject a text turn so NAVI speaks the outcome."""
        s = session_ref["s"]
        if s is None:
            return
        asyncio.run_coroutine_threadsafe(
            s.send_client_content(turns=types.Content(role="user", parts=[types.Part(text=text)]),
                                  turn_complete=True), loop)

    def watch_badges():
        """A badge tap becomes a text turn, so NAVI greets whoever just arrived."""
        watcher = bus.Latest("badge")
        while not stop_event.is_set():
            tap = watcher.poll()
            if tap:
                name = tap.get("name") or "someone"
                print(f"[badge] {name} tapped in", flush=True)
                notify(f"[badge] {name} just tapped their badge. Greet them by name in "
                       "one short sentence and ask where they would like to go."
                       + ("" if tap.get("known") else
                          " Their badge is not registered, so do not use the name as if "
                          "you know them."))
            time.sleep(0.2)

    threading.Thread(target=watch_badges, daemon=True).start()

    nav = Navigator(enabled=not args.no_nav, notify=notify)
    attempt = 0
    try:
        while not stop_event.is_set():
            attempt += 1
            try:
                while not mic_queue.empty():
                    mic_queue.get_nowait()
                if attempt > 1:
                    await asyncio.sleep(min(2 ** (attempt - 2), 10))
                async with client.aio.live.connect(model=args.model, config=config) as session:
                    session_ref["s"] = session
                    attempt = 1
                    set_face("LISTENING")
                    print("[gemini] connected — start talking", flush=True)

                    async def handle_tools(tool_call):
                        for fc in tool_call.function_calls:
                            args_ = dict(fc.args or {})
                            set_face("THINKING")
                            print(f"[tool] {fc.name}({args_})", flush=True)
                            if fc.name == "find_place":
                                result = find_place(str(args_.get("query", "")).strip())
                            elif fc.name == "navigate_to":
                                result = nav.start(str(args_.get("place", "")).strip().lower())
                            elif fc.name == "list_places":
                                result = {"places": list(places.load_places())}
                            elif fc.name == "where_am_i":
                                result = where_am_i()
                            elif fc.name == "stop_navigation":
                                result = nav.stop()
                            else:
                                result = {"error": f"unknown tool {fc.name}"}
                            await session.send_tool_response(function_responses=[types.FunctionResponse(
                                name=fc.name, id=fc.id, response=result, scheduling="WHEN_IDLE")])

                    async def send_audio():
                        while not stop_event.is_set():
                            try:
                                audio = mic_queue.get_nowait().flatten()
                            except queue.Empty:
                                await asyncio.sleep(0.02)
                                continue
                            boosted = (audio.astype(np.float32) * args.mic_gain).clip(-32768, 32767).astype(np.int16)
                            await session.send_realtime_input(audio=types.Blob(
                                data=boosted.tobytes(), mime_type=f"audio/pcm;rate={BBOS_RATE}"))

                    async def receive():
                        pcm = bytearray()
                        heard, said = [], []
                        while not stop_event.is_set():
                            async for resp in session.receive():
                                sc = resp.server_content
                                if sc:
                                    if sc.input_transcription and sc.input_transcription.text:
                                        heard.append(sc.input_transcription.text)
                                    if sc.output_transcription and sc.output_transcription.text:
                                        said.append(sc.output_transcription.text)
                                    if sc.model_turn and sc.model_turn.parts:
                                        for part in sc.model_turn.parts:
                                            if part.inline_data and part.inline_data.data:
                                                set_face("SPEAKING")
                                                p24 = np.frombuffer(part.inline_data.data, dtype=np.int16)
                                                p16 = soxr.resample(p24.astype(np.float32), GEMINI_RATE, BBOS_RATE)
                                                p16 = (p16 * args.volume).clip(-32768, 32767).astype(np.int16)
                                                pcm.extend(p16.tobytes())
                                                while len(pcm) >= CHUNK * 2:
                                                    chunk = np.frombuffer(bytes(pcm[:CHUNK * 2]), dtype=np.int16)
                                                    del pcm[:CHUNK * 2]
                                                    try:
                                                        speaker_queue.put_nowait(chunk)
                                                    except queue.Full:
                                                        pass
                                    if sc.interrupted:
                                        interrupt_flag.set()
                                    if sc.turn_complete:
                                        set_face("LISTENING")
                                        if heard:
                                            print(f"[you ] {''.join(heard).strip()}", flush=True)
                                        if said:
                                            print(f"[navi] {''.join(said).strip()}", flush=True)
                                        heard.clear(); said.clear()
                                if resp.tool_call:
                                    asyncio.create_task(handle_tools(resp.tool_call))

                    tasks = [asyncio.create_task(c) for c in (send_audio(), receive())]
                    _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for t in pending:
                        t.cancel()
                session_ref["s"] = None
                print("[gemini] session ended, reconnecting...", flush=True)
            except Exception as e:
                session_ref["s"] = None
                if stop_event.is_set():
                    break
                print(f"[gemini] connection error: {e}", flush=True)
    finally:
        nav.stop()
        set_face("IDLE")


def main():
    parser = argparse.ArgumentParser(description="NAVI voice guide")
    parser.add_argument("--model", default="gemini-2.5-flash-native-audio-preview-12-2025")
    parser.add_argument("--voice", default="Puck")
    parser.add_argument("--volume", type=float, default=0.45)
    parser.add_argument("--mic-gain", type=float, default=3.0)
    parser.add_argument("--no-nav", action="store_true", help="talk only, never drive")
    args = parser.parse_args()

    known = venue.load_venue()["places"]
    print(f"NAVI voice | venue: {len(known)} places on 7 floors | "
          f"drivable: {', '.join(places.load_places()) or 'none saved yet'} | "
          f"nav {'OFF' if args.no_nav else 'ON'}", flush=True)
    threading.Thread(target=audio_io_loop, daemon=True).start()
    try:
        asyncio.run(gemini_session(args))
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        print("\n[+] stopped", flush=True)


if __name__ == "__main__":
    main()
