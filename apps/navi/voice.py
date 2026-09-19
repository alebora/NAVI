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
"""NAVI voice: talk to the robot through Gemini Live; it can guide you to saved places.

  uv run voice.py
  uv run voice.py --no-nav     # talk only, never drives (safe for first test)

Needs GEMINI_API_KEY in ./.env (or ~/bbapps/greeter/.env). Places come from
places.yaml — save them first with `uv run places.py save <name>`.
Audio I/O and the Gemini loop follow ~/bbapps/greeter/main.py.
"""
import argparse
import asyncio
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

import places

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

SYSTEM_PROMPT = """You are NAVI, a friendly indoor guide robot at a hackathon venue.
People talk to you to find their way around. You can physically drive and lead them.
- When someone asks to go somewhere, call navigate_to with the closest matching saved place.
  If you are unsure which place they mean, call list_places first, then ask briefly.
- Say one short sentence before you start moving, e.g. "Sure, follow me to judging."
- If someone says stop, wait, or hold on, call stop_navigation immediately.
- When you receive a message starting with [nav], tell the person what happened in one sentence.
- Keep every reply to 1-2 short sentences. You are speaking out loud, so no lists or markdown."""


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
        name="navigate_to",
        description="Drive to a saved place and lead the person there.",
        behavior="NON_BLOCKING",
        parameters={"type": "object",
                    "properties": {"place": {"type": "string",
                                             "description": "Exact saved place name from list_places"}},
                    "required": ["place"]},
    ),
    types.FunctionDeclaration(
        name="list_places",
        description="List the saved places NAVI can guide people to.",
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
            text=SYSTEM_PROMPT + f"\nSaved places right now: {', '.join(places.load_places()) or 'none'}.")]),
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
                    print("[gemini] connected — start talking", flush=True)

                    async def handle_tools(tool_call):
                        for fc in tool_call.function_calls:
                            args_ = dict(fc.args or {})
                            print(f"[tool] {fc.name}({args_})", flush=True)
                            if fc.name == "navigate_to":
                                result = nav.start(str(args_.get("place", "")).strip().lower())
                            elif fc.name == "list_places":
                                result = {"places": list(places.load_places())}
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


def main():
    parser = argparse.ArgumentParser(description="NAVI voice guide")
    parser.add_argument("--model", default="gemini-2.5-flash-native-audio-preview-12-2025")
    parser.add_argument("--voice", default="Puck")
    parser.add_argument("--volume", type=float, default=0.45)
    parser.add_argument("--mic-gain", type=float, default=3.0)
    parser.add_argument("--no-nav", action="store_true", help="talk only, never drive")
    args = parser.parse_args()

    print(f"NAVI voice | places: {', '.join(places.load_places()) or 'none yet'} | "
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
