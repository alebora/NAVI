# NAVI meeting recording add-on

This directory is intentionally separate from the existing NAVI robot apps.
Nothing here patches `apps/navi/voice.py`, `assistant.py`, `face.py`, NFC, or
BBOS daemons. The recorder can run as a standalone process and later receive a
small approved trigger hook from the working voice layer.

## MVP flow

1. A trigger writes `/dev/shm/navi/meeting_command.json`:
   - `{"command":"start","phrase":"Navi record"}`
   - `{"command":"stop","phrase":"Navi stop"}`
2. `jetson/meeting_recorder.py` records audio with `arecord`.
3. A local free STT backend transcribes the WAV:
   - preferred: `whisper.cpp`
   - optional: `faster-whisper`
4. A local/free small summarizer creates a meeting summary:
   - preferred: Ollama or llama.cpp with a small instruct model
   - fallback: deterministic extractive summary so the pipeline still saves
5. The final document is inserted into MongoDB, or written to `outbox/` if
   MongoDB is not configured.
6. The website reads meeting summaries from the API and displays them.

## Jetson quick start

Install optional runtime pieces:

```bash
sudo apt-get install -y alsa-utils
python3 -m pip install --user pymongo faster-whisper
```

Create a local env file from the example:

```bash
cp meeting_recording/jetson/.env.example meeting_recording/jetson/.env
```

Run in dry/manual mode:

```bash
python3 meeting_recording/jetson/meeting_recorder.py --manual
```

Trigger from another terminal:

```bash
python3 meeting_recording/jetson/send_command.py start
python3 meeting_recording/jetson/send_command.py stop
```

## Voice integration later

The safe integration point is a tiny hook in the existing command-intent layer:

```python
from meeting_recording.jetson.meeting_bus import publish_command

if user_asked_to_record:
    publish_command("start", phrase=text)
elif user_asked_to_stop_recording:
    publish_command("stop", phrase=text)
```

Do not add that hook until the current robot code is backed up and the team
approves the exact patch.

## Mongo document

Documents are written to `meetingSummaries`:

```json
{
  "meetingId": "meet_20260919_190100_ab12cd",
  "robotId": "bracketbot-189",
  "title": "Generated title",
  "startedAt": "2026-09-19T19:01:00Z",
  "endedAt": "2026-09-19T19:12:20Z",
  "durationSeconds": 680,
  "status": "ready",
  "recordingType": "audio_only",
  "audioPath": "/home/bracketbot/NAVI/meeting_recording/data/audio/...",
  "transcript": "...",
  "summary": "...",
  "decisions": [],
  "actionItems": []
}
```

## Status lights

The recorder writes `/dev/shm/navi/meeting_status.json` with states such as
`idle`, `recording`, `processing`, `ready`, and `failed`.

By default it does not directly claim LED writers. If `NAVI_LED_COMMAND` is set,
the recorder calls it as:

```bash
$NAVI_LED_COMMAND blue
$NAVI_LED_COMMAND red
```

That lets the team attach the correct BBOS LED command later without risking the
working robot stack.
