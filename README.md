# NAVI Coding Context

## Purpose

This file is the full coding context for NAVI. Agents should use it as the source of truth when implementing robot-side scripts, backend services, dashboard features, AI workflows, demo flows, and hardware integrations.

NAVI is an embodied indoor guide built on the newest Bracket Bot platform. It helps people navigate large indoor buildings while respecting NFC-card-based access rules. It can also record walking meetings with audio only, summarize them, and send the summary to an app dashboard.

Agents must preserve the actual hardware and project constraints:

- The robot uses the newest Bracket Bots, invented by Waterloo students.
- The team can only add its own Bracket Bot scripts in Python.
- The implementation must use Bracket Bot's custom libraries and robot operating system.
- The robot uses two RGB cameras working together for 3D SLAM.
- Do not describe the cameras as depth cameras.
- A small monitor is connected to the Jetson and mounted near the top as the robot's animated face.
- A Freenove ESP32-WROVER-E board with a PN532 NFC module is connected to the Jetson over USB serial.
- Google models and Google Cloud services should be used heavily for AI: STT, TTS, LLM reasoning, summarization, and optional vision.
- Meeting recording is audio only.
- NFC card ID determines where the robot is allowed to guide someone.

---

## WHO

NAVI is built by a hackathon team using the newest Bracket Bot platform. Bracket Bot is an open-source robotics development kit originally created by University of Waterloo students as a low-cost, modular robot platform with mapping, navigation, camera, microphone, speaker, and Python app-layer examples.

The project stakeholders are:

- Event visitors who need help navigating a large indoor venue.
- Staff, organizers, sponsors, judges, and volunteers who may have different access permissions.
- Security or operations teams who need physical access rules respected.
- Meeting participants who want audio-only summaries of walking meetings.
- Developers building the robot, cloud services, app dashboard, and AI pipeline.
- Sponsors evaluating whether an embodied AI robot could help in large venues.

NAVI should be treated as an embodied indoor guide, not just a chatbot on wheels. It must combine navigation, identity, permissions, speech, mapping, meeting recording, summarization, face display, NFC hardware integration, and basic physical interaction.

---

## WHAT

NAVI is a speech-to-speech, identity-aware indoor robot for large buildings.

A user taps an NFC card, speaks a destination request, and NAVI checks whether that NFC card ID has clearance for the requested destination. If the user is allowed, NAVI guides them through the building. If the user is not allowed, NAVI refuses to guide them there and may suggest permitted destinations.

NAVI also supports audio-only walking meeting recording. A user can say, "Start recording this meeting." NAVI records audio only. When the user says, "Stop recording," NAVI transcribes the audio, generates a meeting summary, extracts decisions and action items, and sends the result to the app dashboard.

NAVI uses two RGB cameras together for 3D SLAM. Do not describe the cameras as depth cameras. The system should assume stereo-style visual SLAM from two RGB camera feeds, plus robot odometry and onboard sensors where available.

NAVI's arm is planned for building interaction, especially pressing elevator buttons. Meta Quest teleoperation is used to collect demonstrations for a VLA-style manipulation policy so the robot can learn simple physical actions such as pressing elevator controls.

NAVI has a small monitor mounted near the top of the robot. This monitor is connected to the Jetson and is used as the robot's animated face. The face should communicate robot state at a glance, including idle, listening, navigating, recording, access granted, access denied, elevator mode, thinking, summarizing, and error states.

NAVI includes a Freenove ESP32-WROVER-E board connected to a PN532 NFC module. The ESP32 talks to the Jetson over USB serial. The PN532 reads NFC card IDs, and the ESP32 exposes scan events to the Jetson through a simple polling protocol.

---

## WHERE

NAVI is intended for large indoor environments where normal GPS-based navigation does not work well.

Primary target environments:

- Hackathon venues.
- Conference centers.
- University buildings.
- Multi-floor event spaces.
- Hospitals.
- Offices.
- Museums.
- Malls.
- Large secured facilities.

The first demo should be scoped to a small reliable indoor route, not an entire campus. Build around three to five labeled destinations such as:

- Registration.
- Judging area.
- Sponsor booth.
- Hardware room.
- Elevator.
- Staff-only room.
- Washroom.
- Main hall.

Every destination must have metadata describing whether it is public or restricted and which NFC card IDs, roles, or clearance groups can be guided there.

---

## WHEN

NAVI operates in real time during an event.

Core runtime moments:

- Startup: robot boots, connects to cloud services, loads venue map, starts local navigation stack, starts microphone listener, verifies cameras, verifies the face monitor, verifies the ESP32 NFC serial connection, and syncs permission data.
- Check-in: user taps NFC card.
- Intent capture: user asks to go somewhere or asks to start or stop recording.
- Clearance check: backend or local permission module verifies whether the NFC card ID can access the requested destination.
- Navigation: robot guides the user while monitoring position, obstacles, route state, and user following behavior.
- Arrival: robot announces destination arrival.
- Meeting recording: robot records audio only after an explicit start command and consent flow.
- Meeting processing: after stop command, robot transcribes, summarizes, extracts action items, and uploads the result to the dashboard.
- Teleoperation/training: Meta Quest is used to collect arm demonstrations for tasks like elevator button pressing.
- Shutdown: robot stops movement, closes audio streams, flushes logs, stops face animation, and stores session state.

---

## WHY

Large buildings are hard to navigate. Static signs are easy to miss, indoor maps are often incomplete, and phone maps are weak indoors. Events like Hack the North happen in massive buildings where visitors, sponsors, judges, and organizers may need help finding the right place quickly.

NAVI solves this by physically guiding people to destinations, while also enforcing access rules based on NFC card clearance.

The security motivation comes from a team member's experience working in a security company. The insight was that a robot like NAVI could help with two problems at once:

- Recording and summarizing meetings while people walk through a facility.
- Enforcing physical access rules by refusing to guide people to restricted areas.

At least two sponsors at Hack the North said this type of robot would be useful for navigating a massive event building. That sponsor feedback should guide product decisions: prioritize reliable indoor guidance, visible access control, and useful meeting summaries over flashy but fragile features.

---

## HOW

## System Architecture

NAVI should be built as a hybrid edge-cloud system.

The robot handles low-latency physical behavior locally:

- Motor control.
- Camera capture.
- SLAM input.
- Local map pose.
- Obstacle response.
- Audio capture.
- Wake phrase or push-to-talk.
- Speaker playback.
- NFC reads through ESP32 serial.
- Face monitor rendering.
- Safety stop.
- Teleoperation bridge.

The cloud handles heavier app and AI workflows:

- User/card registry.
- Destination registry.
- Permission checks.
- Session logs.
- Meeting transcription.
- Meeting summarization.
- Dashboard sync.
- Long-term storage.
- Admin configuration.

The preferred AI provider is Google for all AI tasks.

Use Google models and Google Cloud services wherever practical:

- Speech-to-text: Google Cloud Speech-to-Text v2 or Gemini Live transcription.
- Text-to-speech: Google Cloud Text-to-Speech Chirp 3 HD voices.
- LLM reasoning and summarization: Gemini through Vertex AI or Google Gen AI SDK.
- Vision reasoning if needed: Gemini multimodal vision models.
- Backend hosting: Cloud Run.
- Database: Firestore.
- File storage: Cloud Storage.
- Event messaging: Pub/Sub.
- Authentication: Firebase Auth or Google Identity Platform.
- Dashboard: Firebase Hosting, Cloud Run, or a Next.js deployment.
- Logs/monitoring: Cloud Logging and Cloud Monitoring.

## Hardware Assumptions

Use the newest Bracket Bot available to the team.

Expected hardware:

- Bracket Bot mobile base.
- Two RGB cameras for 3D SLAM.
- Microphone for voice commands and meeting audio.
- Speaker for spoken responses.
- Small Jetson-connected monitor mounted near the top as the robot face.
- Freenove ESP32-WROVER-E board.
- PN532 NFC module connected to ESP32.
- USB serial connection from ESP32 to Jetson.
- Onboard compute, preferably Jetson-class if available.
- Robot arms or one arm for interaction.
- Meta Quest headset/controllers for teleoperation and demonstration collection.
- Battery-powered mobile operation.
- Wi-Fi connection to local dashboard/backend.

Important hardware rule:

Do not assume a depth camera unless the actual robot kit has one installed. The project description should say "two RGB cameras for 3D SLAM," not "depth camera."

## Programming Constraints

All Jetson-side additions must be Python.

Do not assume Node.js, ROS changes, C++ extensions, or custom system services unless explicitly required by the Bracket Bot SDK.

Preferred Jetson-side Python packages:

- `pyserial` for ESP32 NFC serial communication.
- `pygame` for the monitor face.
- `pyaudio` or Bracket Bot microphone APIs for local audio capture.
- Google Cloud Python SDKs for cloud AI calls.
- Bracket Bot's custom Python libraries for robot motion, camera access, microphone/speaker access, and navigation.
- `asyncio`, `threading`, or `queue` for coordinating face state, audio, NFC, and robot state.
- `requests`, `httpx`, or Google client SDKs for backend communication.

Do not bypass Bracket Bot's operating system or low-level control stack. NAVI should be implemented as an app-layer Python system that sits on top of Bracket Bot's provided runtime.

## Recommended Repository Layout

```text
navi/
  robot/
    main.py
    config/
      robot.yaml
      venue.yaml
      cards.json
      destinations.json
    perception/
      cameras.py
      slam_bridge.py
      obstacle_events.py
    audio/
      microphone.py
      wake_listener.py
      recorder.py
      playback.py
      stt_client.py
      tts_client.py
    nfc/
      reader.py
      card_events.py
    face/
      display.py
      states.py
      animations.py
    navigation/
      map_client.py
      route_planner.py
      mission_controller.py
      follower.py
      safety.py
    arm/
      teleop_bridge.py
      demo_recorder.py
      elevator_button_policy.py
    app_client/
      api.py
      websocket.py
      upload.py
    state/
      session_store.py
      robot_state.py

  backend/
    api/
      main.py
      auth.py
      cards.py
      destinations.py
      clearance.py
      sessions.py
      recordings.py
      summaries.py
    workers/
      transcribe_meeting.py
      summarize_meeting.py
      process_demo_data.py
    schemas/
      card.json
      destination.json
      navigation_session.json
      meeting_session.json
      arm_demo.json

  dashboard/
    app/
      page.tsx
      sessions/
      recordings/
      destinations/
      cards/
      admin/
    components/
    lib/

  shared/
    types/
    prompts/
    protocol/

  docs/
    AGENTS.md
    setup.md
    demo_script.md
```

## Robot Runtime Loop

The robot should run a central mission controller.

High-level loop:

```text
1. Boot robot.
2. Load config.
3. Connect to backend.
4. Start SLAM/map bridge.
5. Start face monitor display.
6. Start NFC serial listener.
7. Start speech listener.
8. Wait for user.
9. On NFC tap, create or update active user session.
10. On voice command, classify intent.
11. If destination request, run clearance check.
12. If allowed, plan route and guide user.
13. If denied, explain refusal politely.
14. If start recording, begin audio-only meeting session.
15. If stop recording, upload audio and trigger summary.
16. Keep dashboard updated through API/WebSocket events.
```

## Jetson Process Plan

Recommended Python process/module layout for the hackathon:

```text
main_navi.py
  owns mission state

face.py
  pygame fullscreen face display

nfc_reader.py
  pyserial polling client for ESP32

speech.py
  Google STT primary, Vosk fallback

tts.py
  Google TTS playback

clearance.py
  checks card permissions against local JSON or backend

navigation.py
  wraps Bracket Bot navigation libraries

meeting_recorder.py
  records audio-only meetings and uploads/processes them

dashboard_client.py
  sends events and summaries to app dashboard
```

For hackathon reliability, allow local JSON config if backend is not ready:

```text
config/cards.json
config/destinations.json
config/venue_map.json
```

## Face Monitor

The face monitor should be launched on the Jetson display.

Example launch pattern:

```bash
export DISPLAY=:0
python3 ~/Documents/test/navi_face_voice.py
```

The existing face example uses:

- `pygame` for fullscreen rendering.
- A black background.
- Light blue animated eyes for idle mode.
- A red microphone icon for recording mode.
- A blue elevator/up-arrow state for elevator mode.
- A background speech listener using Vosk.
- Simple keyword detection for local state changes.

For the full NAVI system, the face should not only listen independently. It should subscribe to central robot state.

Recommended robot face states:

```python
FACE_IDLE = "IDLE"
FACE_LISTENING = "LISTENING"
FACE_THINKING = "THINKING"
FACE_NAVIGATING = "NAVIGATING"
FACE_ACCESS_GRANTED = "ACCESS_GRANTED"
FACE_ACCESS_DENIED = "ACCESS_DENIED"
FACE_RECORDING = "RECORDING"
FACE_SUMMARIZING = "SUMMARIZING"
FACE_ELEVATOR = "ELEVATOR"
FACE_ERROR = "ERROR"
```

Recommended architecture:

```text
main_navi.py
  starts:
    - face display thread/process
    - NFC serial listener
    - audio command listener
    - robot navigation controller
    - backend/dashboard sync client

shared robot_state object
  controls:
    - face expression
    - spoken response
    - navigation mode
    - recording mode
    - dashboard updates
```

Clean face interface:

```python
face.set_state("IDLE")
face.set_state("LISTENING")
face.set_state("ACCESS_GRANTED")
face.set_state("ACCESS_DENIED")
face.set_state("RECORDING")
face.set_state("SUMMARIZING")
face.set_state("ELEVATOR")
```

The face should remain usable without internet. If Google AI services are down, the face should still show local state changes from NFC, recording, navigation, and errors.

Face state mapping:

```python
if card_read:
    face.set_state("THINKING")

if clearance.allowed:
    face.set_state("ACCESS_GRANTED")

if not clearance.allowed:
    face.set_state("ACCESS_DENIED")

if navigation.active:
    face.set_state("NAVIGATING")

if meeting_recording.active:
    face.set_state("RECORDING")

if meeting_summary.processing:
    face.set_state("SUMMARIZING")
```

The face should not imply video recording. Use a microphone icon, waveform, or red recording dot rather than camera imagery.

## NFC Hardware

NFC hardware stack:

```text
PN532 NFC module
  -> UART
Freenove ESP32-WROVER-E
  -> USB serial
Jetson
  -> Python pyserial reader
NAVI backend / clearance system
```

The ESP32 firmware currently:

- Uses `HardwareSerial PN532Serial(2)`.
- Uses UART2 with RX pin 13 and TX pin 14.
- Uses Adafruit PN532 library.
- Talks to the Jetson over `Serial` at 115200 baud.
- Reads ISO14443A NFC cards.
- Converts UID bytes into colon-separated uppercase hex.
- Stores the latest card event.
- Responds to Jetson polling request `CHECK_NFC`.
- Returns one of:
  - `NFC_AUTH:<UID>`
  - `NFC_DENIED:<UID>`
  - `NONE`

Important implementation note:

The ESP32 may contain hardcoded authorized cards for quick demo testing, but production-style NAVI logic should treat the ESP32 as a card reader, not the final permission authority.

Better long-term protocol:

```text
NFC_CARD:04:B3:69:7A:65:23:90
NONE
NFC_ERROR:PN532_DISCONNECTED
```

Then the Jetson/backend decides:

```text
card UID + requested destination -> clearance decision
```

This matters because clearance is destination-specific. A card may be allowed to go to the judging area but not the hardware room. The ESP32 cannot know the requested destination unless the full permission model is pushed onto it, which would make the system harder to update.

## NFC Serial Protocol

For the current firmware, the Jetson should poll over serial:

```text
Jetson -> ESP32:
CHECK_NFC\n

ESP32 -> Jetson:
NFC_AUTH:04:B3:69:7A:65:23:90\n
```

or:

```text
NFC_DENIED:B3:34:D4:E7\n
```

or:

```text
NONE\n
```

Recommended Python reader:

```python
import serial
import time


class NFCReader:
    def __init__(self, port="/dev/ttyUSB0", baudrate=115200):
        self.ser = serial.Serial(port, baudrate, timeout=0.25)
        time.sleep(2.0)

    def check(self):
        self.ser.write(b"CHECK_NFC\n")
        line = self.ser.readline().decode("utf-8", errors="ignore").strip()

        if not line or line == "NONE":
            return None

        if line.startswith("NFC_AUTH:"):
            return {
                "status": "CARD_READ",
                "uid": line.split(":", 1)[1],
                "reader_label": "esp32_pn532",
                "esp32_hint": "AUTH",
            }

        if line.startswith("NFC_DENIED:"):
            return {
                "status": "CARD_READ",
                "uid": line.split(":", 1)[1],
                "reader_label": "esp32_pn532",
                "esp32_hint": "DENIED",
            }

        return {
            "status": "ERROR",
            "raw": line,
        }
```

The `esp32_hint` field should not be treated as final destination clearance. The backend or Jetson clearance module should still check the UID against the requested destination.

## NFC Clearance Model

NFC card ID is the key identity signal for the prototype.

The robot should never guide a user to a restricted location unless the backend or local clearance module confirms that the active NFC card ID has clearance.

Recommended data model:

```json
{
  "card_id": "nfc_04AABBCCDD",
  "display_name": "Sponsor Mentor",
  "role": "sponsor",
  "clearance_groups": ["public", "sponsor", "judging"],
  "allowed_destination_ids": ["main_hall", "judging_area", "sponsor_lounge"],
  "denied_destination_ids": ["hardware_storage", "organizer_ops"],
  "active": true
}
```

Destination model:

```json
{
  "destination_id": "judging_area",
  "name": "Judging Area",
  "aliases": ["judging", "judge room", "project judging"],
  "floor": 1,
  "map_node_id": "node_judging_area",
  "access_level": "restricted",
  "required_clearance_groups": ["judging", "organizer"],
  "description": "Area where project judging happens."
}
```

Clearance decision response:

```json
{
  "allowed": true,
  "reason": "Card has judging clearance.",
  "destination_id": "judging_area",
  "route_allowed": true
}
```

Denied response:

```json
{
  "allowed": false,
  "reason": "This card does not have clearance for the hardware storage room.",
  "suggested_destinations": ["registration", "main_hall", "help_desk"]
}
```

Local cards file example:

```json
{
  "04:B3:69:7A:65:23:90": {
    "display_name": "Organizer",
    "clearance_groups": ["public", "judging", "hardware", "staff"]
  },
  "B3:34:D4:E7": {
    "display_name": "Visitor",
    "clearance_groups": ["public"]
  }
}
```

Local destinations file example:

```json
{
  "registration": {
    "name": "Registration",
    "aliases": ["front desk", "check in", "registration"],
    "required_clearance_groups": ["public"],
    "map_node_id": "node_registration"
  },
  "judging_area": {
    "name": "Judging Area",
    "aliases": ["judging", "judge area", "judging room"],
    "required_clearance_groups": ["judging"],
    "map_node_id": "node_judging"
  },
  "hardware_room": {
    "name": "Hardware Room",
    "aliases": ["hardware", "hardware room", "parts room"],
    "required_clearance_groups": ["hardware", "staff"],
    "map_node_id": "node_hardware"
  }
}
```

## Access-Control Flow With NFC

The correct flow is:

```text
1. User taps NFC card.
2. ESP32 reads card UID through PN532.
3. Jetson polls ESP32 and receives UID.
4. Jetson stores active_card_id.
5. User asks for destination.
6. Jetson sends active_card_id + destination_text to clearance checker.
7. Clearance checker resolves destination.
8. Clearance checker decides whether that card can be guided there.
9. If allowed, NAVI guides the user.
10. If denied, NAVI refuses and shows access-denied face state.
```

Do not make navigation decisions from `NFC_AUTH` alone.

A user is not globally "authorized." A user is authorized for specific places.

Better spoken language:

```text
Card recognized.
Checking whether you have access to the judging area.
You have access. I can guide you there now.
```

Denied:

```text
Card recognized.
I can't guide you to the hardware room with this card.
I can take you to registration or the help desk instead.
```

## Voice Interaction

Voice should be practical and short.

Use Google STT for speech recognition. For live conversational behavior, use Gemini Live API if latency and quota allow. For simpler implementation, use Cloud Speech-to-Text streaming for commands and Cloud Speech-to-Text batch/asynchronous transcription for meeting audio.

Use Google TTS Chirp 3 HD voices for robot speech.

Command examples:

```text
"Take me to the judging area."
"Can you guide me to the sponsor booth?"
"Start recording this meeting."
"Stop recording."
"Where am I allowed to go?"
"Take me to the nearest elevator."
"Cancel navigation."
"Wait here."
"Continue."
```

The robot should parse voice into structured intents:

```json
{
  "intent": "NAVIGATE_TO_DESTINATION",
  "destination_text": "judging area",
  "confidence": 0.92
}
```

```json
{
  "intent": "START_MEETING_RECORDING",
  "confidence": 0.96
}
```

```json
{
  "intent": "STOP_MEETING_RECORDING",
  "confidence": 0.98
}
```

Use Gemini for intent parsing when possible, but keep a local fallback keyword parser for demo reliability.

## Audio and AI Stack

The pasted face script currently uses Vosk for local keyword detection. This is useful for offline demo fallback and quick testing.

However, the preferred final AI stack should lean heavily on Google models:

- Google Cloud Speech-to-Text v2 for voice commands.
- Google Cloud Speech-to-Text v2 or Gemini transcription for meeting audio.
- Gemini for intent parsing.
- Gemini for route explanation.
- Gemini for meeting summaries.
- Gemini for action item extraction.
- Google Cloud Text-to-Speech Chirp 3 HD for robot speech.
- Gemini vision models only if visual reasoning is needed.
- Local Vosk only as a fallback when internet or Google credentials fail.

Recommended strategy:

```text
Primary:
  microphone -> Google STT -> Gemini intent parser -> robot action

Fallback:
  microphone -> local Vosk keywords -> limited demo actions
```

Fallback commands should include:

```text
"take me to registration"
"take me to judging"
"start recording"
"stop recording"
"elevator"
"cancel"
"wait"
"continue"
```

Never let an LLM directly decide physical motion without constraints. The LLM can produce a goal, explanation, or structured intent. The navigation controller must decide whether a route is valid and safe.

## Meeting Recording

Meeting recording is audio-only.

Do not capture meeting video or screenshots for this project unless explicitly added later.

Flow:

```text
1. User says: "Start recording this meeting."
2. NAVI confirms consent.
3. Face changes to RECORDING.
4. NAVI starts audio-only recording.
5. Dashboard meeting session starts.
6. Robot optionally follows or leads the group.
7. User says: "Stop recording."
8. Face changes to SUMMARIZING.
9. NAVI stops audio capture.
10. Audio is uploaded to Cloud Storage.
11. Backend creates transcription job.
12. Transcript is generated.
13. Gemini summarizes transcript.
14. Summary, decisions, action items, timestamps, and participants are saved.
15. Dashboard shows the meeting result.
16. Face returns to IDLE or NAVIGATING.
```

Meeting summary schema:

```json
{
  "meeting_id": "meet_2026_09_19_001",
  "started_at": "2026-09-19T14:30:00-04:00",
  "ended_at": "2026-09-19T14:42:00-04:00",
  "recording_type": "audio_only",
  "participants": [
    {
      "card_id": "nfc_04AABBCCDD",
      "display_name": "Sponsor Mentor"
    }
  ],
  "summary": "The group discussed NAVI's indoor navigation and access-control use cases.",
  "decisions": [
    "Prioritize reliable NFC-based destination clearance for the demo."
  ],
  "action_items": [
    {
      "task": "Add dashboard view for meeting summaries.",
      "owner": "software team",
      "due": null
    }
  ],
  "locations": [
    {
      "timestamp": "2026-09-19T14:35:00-04:00",
      "map_node_id": "node_main_hall",
      "label": "Main Hall"
    }
  ]
}
```

## Navigation

The navigation system should use the Bracket Bot's mapping/navigation stack where possible.

NAVI adds an app-layer mission planner above the robot's existing mapping and movement capabilities.

Responsibilities:

- Convert destination names into map node IDs.
- Check clearance before route planning.
- Request path from navigation stack.
- Start movement.
- Monitor progress.
- Detect blocked route events.
- Reroute if needed.
- Pause if user falls behind.
- Announce arrival.

Navigation state machine:

```text
IDLE
CARD_ACTIVE
DESTINATION_REQUESTED
CHECKING_CLEARANCE
CLEARANCE_DENIED
PLANNING_ROUTE
GUIDING
WAITING_FOR_USER
REROUTING
ARRIVED
CANCELLED
ERROR
```

The route planner must never route into restricted zones unless clearance is granted.

## SLAM and Perception

Use two RGB cameras for 3D SLAM.

The SLAM module should expose:

```json
{
  "robot_pose": {
    "x": 1.42,
    "y": 3.91,
    "z": 0.0,
    "yaw": 1.57,
    "frame": "map"
  },
  "tracking_ok": true,
  "map_id": "venue_demo_map",
  "timestamp": "2026-09-19T14:30:10-04:00"
}
```

The app layer should not rewrite the SLAM stack during the hackathon unless absolutely necessary. Consume its output and build semantic navigation on top.

Semantic map model:

```json
{
  "map_id": "venue_demo_map",
  "nodes": [
    {
      "node_id": "node_registration",
      "label": "Registration",
      "x": 0.0,
      "y": 0.0,
      "floor": 1,
      "destination_id": "registration"
    }
  ],
  "edges": [
    {
      "from": "node_registration",
      "to": "node_main_hall",
      "distance_m": 8.5,
      "requires_clearance": false
    }
  ]
}
```

## Dashboard

The dashboard should be the operational control center.

Pages:

- Live robot status.
- Active navigation session.
- NFC cards and clearance groups.
- Destination registry.
- Meeting recordings.
- Meeting summaries.
- Route/session logs.
- Admin settings.
- Demo mode controls.

Dashboard should show:

- Current robot state.
- Current face state.
- Active user/card.
- Requested destination.
- Clearance result.
- Current route.
- Meeting recording status.
- Completed summaries.
- Errors and warnings.

Use Firebase/Firestore for fast hackathon iteration, unless the team already has another stack.

## Backend API

Recommended endpoints:

```text
POST /api/cards/resolve
POST /api/clearance/check
GET  /api/destinations
POST /api/navigation/session
PATCH /api/navigation/session/:id
POST /api/meeting/start
POST /api/meeting/:id/audio
POST /api/meeting/:id/stop
GET  /api/meeting/:id/summary
POST /api/robot/heartbeat
POST /api/robot/event
```

Clearance check request:

```json
{
  "card_id": "nfc_04AABBCCDD",
  "destination_text": "judging area",
  "robot_id": "navi_01"
}
```

Clearance check response:

```json
{
  "matched_destination": {
    "destination_id": "judging_area",
    "name": "Judging Area"
  },
  "allowed": true,
  "spoken_response": "You have access to the judging area. I can guide you there now."
}
```

## Arm and Meta Quest VLA Plan

The arm feature should be framed as planned/experimental unless working in the demo.

Goal:

- Use Meta Quest teleoperation to control the robot arm.
- Record demonstrations of pressing elevator buttons or safe mock panel buttons.
- Store observations, actions, timestamps, and camera frames.
- Use collected demonstrations to train or fine-tune a VLA-style policy later.

Demo data schema:

```json
{
  "demo_id": "armdemo_001",
  "task": "press_elevator_button",
  "operator": "quest_user_01",
  "frames_uri": "gs://navi-demo-data/armdemo_001/frames/",
  "actions_uri": "gs://navi-demo-data/armdemo_001/actions.jsonl",
  "success": true,
  "notes": "Pressed floor 2 button on mock elevator panel."
}
```

For the hackathon, teleoperation plus saved demonstrations is enough. Autonomous VLA manipulation is a stretch goal.

## Build Plan

Phase 1: Robot basics

- Boot Bracket Bot.
- Verify mobility.
- Verify two RGB camera streams.
- Verify microphone.
- Verify speaker.
- Verify Jetson monitor face.
- Verify ESP32 PN532 NFC reader over USB serial.
- Verify network connection.
- Verify map/localization output.

Phase 2: Backend and dashboard

- Create Firestore schema.
- Add destination registry.
- Add card registry.
- Add clearance check endpoint.
- Add robot heartbeat endpoint.
- Add dashboard views.

Phase 3: Speech interface

- Add Google STT command listener.
- Add Gemini intent parser.
- Add Google TTS responses.
- Add fallback command parser.

Phase 4: Clearance-gated navigation

- NFC card tap creates active session.
- Destination command triggers clearance check.
- Allowed users get route guidance.
- Denied users get polite refusal.
- Dashboard logs all attempts.
- Face displays access granted or access denied.

Phase 5: Audio-only meeting recording

- Start recording by voice.
- Stop recording by voice.
- Upload audio.
- Transcribe with Google STT.
- Summarize with Gemini.
- Send result to dashboard.
- Face shows recording and summarizing states.

Phase 6: Arm/Quest demo

- Connect Meta Quest teleoperation.
- Record button-press demonstrations.
- Show planned VLA pipeline.
- If possible, replay or assist simple button press.

## Safety Rules

The robot must always prioritize safety over demo completeness.

Rules:

- Never move without an active navigation mission.
- Never guide into restricted destinations without clearance.
- Never record audio without explicit start command and consent.
- Always stop recording on command.
- Always provide a physical or software emergency stop.
- Keep robot speed low indoors.
- Treat elevator button pressing as mock/demo unless supervised.
- Keep LLM outputs constrained to structured commands.
- Log denied access attempts without exposing private information unnecessarily.
- Treat ESP32 NFC output as a card read, not as final permission.
- Keep the face monitor honest: do not imply recording, clearance, or navigation states that are not actually active.

## Demo Script

1. Visitor taps NFC card.
2. NAVI face changes to thinking/card-read state.
3. Visitor says: "Take me to the judging area."
4. NAVI checks clearance.
5. If allowed, NAVI says: "You have access to the judging area. Follow me."
6. NAVI face shows access granted, then navigating.
7. NAVI guides visitor along a mapped route.
8. Another card asks for a restricted room.
9. NAVI says: "I can't guide you there with this card. I can take you to registration or the help desk."
10. NAVI face shows access denied.
11. User says: "Start recording this meeting."
12. NAVI confirms consent and starts audio-only recording.
13. NAVI face shows recording.
14. User says: "Stop recording."
15. NAVI face shows summarizing.
16. NAVI uploads audio, creates transcript and summary, and dashboard displays the result.
17. Optional: show Meta Quest teleoperation pressing a mock elevator button.

## Non-Goals

Do not build these first:

- Full-campus mapping.
- Fully autonomous elevator riding.
- Face recognition as primary identity.
- Video meeting recording.
- Screenshot-based meeting notes.
- Unconstrained LLM robot control.
- High-security authentication claims.
- Perfect VLA arm autonomy during the first demo.
- Replacing Bracket Bot's operating system.
- Rewriting Bracket Bot's navigation stack.
- Treating the ESP32 as the final authorization authority.

## Agent Build Rules

Agents coding NAVI must follow these rules:

- Use Python for all Jetson-side project scripts.
- Use Bracket Bot's own Python libraries and operating system.
- Do not rewrite the Bracket Bot navigation stack.
- Do not assume a depth camera.
- Use two RGB cameras as the vision basis.
- Treat the ESP32 PN532 system as a serial NFC reader.
- Do not rely on ESP32 hardcoded authorization for final clearance.
- Make destination clearance depend on NFC card ID plus requested destination.
- Use the monitor face as a state display controlled by the mission controller.
- Use Google models for STT, TTS, LLM reasoning, summarization, and optional vision wherever possible.
- Keep Vosk/local keyword recognition only as a fallback or demo shortcut.
- Keep meeting recording audio-only.
- Send meeting summaries to the dashboard.
- Keep robot movement gated by safety, route validity, and clearance.

## Key Product Sentence

NAVI is an embodied indoor guide that uses NFC card clearance to decide where it is allowed to guide someone, uses two RGB cameras for 3D SLAM, displays robot state through a Jetson-connected face monitor, reads NFC cards through an ESP32 PN532 serial bridge, records walking meetings with audio only, summarizes them to a dashboard with Google AI, and uses Meta Quest demonstrations as the path toward learned arm interactions like pressing elevator buttons.

## Most Important Architecture Rule

The Jetson is the brain, the ESP32 is the NFC reader, and the monitor face is a state display for the mission controller.

Keep those responsibilities separate. The ESP32 reads cards. The face shows state. The Jetson and backend decide what NAVI is allowed to do.
