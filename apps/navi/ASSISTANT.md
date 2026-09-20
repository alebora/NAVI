# NAVI — speech, vision and navigation

`assistant.py` is one entry point for **BracketBot's Jetson and BBOS**. It does not replace the team's voice, face, NFC or places apps, change balance mode, reset SLAM, or start robot services. No ROS installation needed.

## Run on the Jetson

Reads `GEMINI_API_KEY` from `~/NAVI/apps/navi/.env`, then `~/bbapps/greeter/.env`. Keep keys out of source control. Internet is required for Gemini; local navigation/person detection do not themselves need cloud inference.

```bash
cd ~/NAVI/apps/navi
uv run assistant.py --check
uv run assistant.py --download-detector
uv run assistant.py
```

The last command enables speech/vision **without movement**. Audio and one left-camera JPEG per second are sent to Google while running. The app does not save meetings, camera images or conversation transcripts.

After health checks pass, in a clear supervised area:

```bash
uv run assistant.py --enable-motion
```

To have NAVI explore the currently mapped floor, use the separate supervised mode:

```bash
uv run assistant.py --enable-motion --explore
```

Exploration finds frontiers—confirmed free cells near unmapped space—then sends one short goal at a time through the native planner. It never sends a goal inside unknown space. Explore keeps going through SLAM hitches, failed frontiers, and the three-minute cap; it only stops if you say “stop” or press `Ctrl+C`. This is floor exploration, not an elevator/door routine, and dynamic obstacles still require a clear supervised test area.

## Visualize the map

Starting `assistant.py` (without `--check`) also launches the BBOS nav UI on port **8010**. On a laptop open:

```
http://bracketbot-189.local:8010
```

Turn on `BBMap` and `Floor`. Leave **Start** and **Manual Drive** off — this assistant owns `nav.command`. Use `--no-map` to skip the UI.

**Name a place:** right-click the map, type a name (e.g. `judging`). Cyan pins are destinations. Then say “take me to judging.” Click × in the list to forget one.

Optional SLAM timing charts (separate process):

```bash
uv run ~/bbapps/slam_debug_web.py
# http://bracketbot-189.local:8020
```

The nav web UI is not needed. Stop other **apps** owning `nav.command` or `speaker.audio`, such as the old voice/greeter or an active web-navigation session. Keep camera, mic, speaker, SLAM, depth, mapping and nav **daemons** running. This script refuses writer conflicts instead of terminating other apps.

**Ctrl+C stops this assistant's route and closes it.** Keep physical stop/operator control available. Cloud speech recognition is not an emergency stop. Don't test near stairs, crowds, glass or hazards the map may miss.

## Say

- “What can you see?”
- “Remember here as judging.” — save the current healthy SLAM position while stopped.
- “What places do you know?”
- “Take me to judging.”
- “Follow me.” — stand alone in front, about 1.5–1.9 metres away, and walk slowly.
- “Explore this floor.” — starts the same frontier explorer when the process was launched with `--enable-motion`.
- “Stop.” / “Wait.”

CLI alternatives for teaching locations:

```bash
uv run assistant.py --save-place judging
uv run assistant.py --list-places
```

Coordinates are saved to `assistant-places.yaml`, separate from the team's `places.yaml`. Names are not room-number guesses, floor-plan pixels or vision-generated coordinates. Existing names aren't overwritten automatically. Re-teach under a new name after a SLAM restart/reset or pose-graph correction. This conservative prototype does not remap saved landmarks through loop closures.

## Implementation

1. **Speech/vision:** Gemini Live receives mic audio and camera frames; tools request high-level actions only.
2. **Navigation:** An exact saved destination is checked against healthy SLAM and clear mapped floor, then published to `nav.command`. The native nav daemon uses `mapping.grid2d` for obstacle-aware planning/replanning and controls wheels. SLAM supplies location, not obstacle avoidance by itself.
3. **Following:** Local OpenCV/YOLOX detects people on `camera.rect`; matched `camera.points` supplies calibrated stereo-derived base-frame positions. Synchronized `slam.pose` transforms the target to map coordinates. Short waypoint requests maintain about 1.2 m stand-off. Gemini never provides guessed metric coordinates or velocities.
4. **Exploration:** Local frontier selection reads `mapping.grid2d`, treats `1` as known free and `0` as unknown, chooses a confirmed-free goal near an unmapped boundary, and sends it through the existing nav daemon. The native planner still handles the route and obstacle inflation; this script never commands wheel velocities or drives into unknown cells.
5. **Watchdog:** Independent checks run about 10 Hz. Stale pose/depth/map, tracking loss/jumps, rebuilding, planner failures, lost/ambiguous follow targets and app/session shutdown cancel the route. Sessions expire after three minutes. Native navigation also stops when this app's writer disappears.

Following is an **experimental single-person, front-facing prototype**, not identity recognition. Multiple detected people, unreliable depth, lost target, blocked/unmapped floor or slow inference stop it; ask again to reacquire. No blind reversing or searching behind the robot. Current BBOS point-cloud settings clip to about 2 m horizontally, limiting acquisition range. Crowds, occlusions and long-distance tracking need further work.

Escorting **to a destination** and **following someone** are distinct modes: escort does not yet check whether the person behind has fallen behind. Arms, elevators, recording and multi-floor travel are not implemented here.

## Optional NFC gate

```bash
uv run assistant.py --enable-motion --require-badge
```

Checks the existing NFC bridge's `badge.json` for a UID in `badges.yaml`, tapped within 60 seconds of each motion request. Does not trust a tag's self-supplied display name. This is a demo allowlist, not cryptographic authentication, per-room permissions or proof the visible person owns that badge. Off by default.

## Diagnostics

```bash
uv run assistant.py --check
uv run assistant.py --check-follow
uv run assistant.py --check-api
uv run --with numpy --with pyyaml python -m unittest discover -s . -p test_assistant.py -v
```

- `--check`: read-only health, key presence and saved places; no cloud/audio/motion writes.
- `--check-follow`: one local detector benchmark; no cloud, speaker or movement.
- `--check-api`: small billable cloud test using only a synthetic black image and silent PCM. No robot I/O.
- Unit tests use fake robot records, never live writers.

Select another supported Live model with `--model MODEL_NAME` or `GEMINI_LIVE_MODEL`. Default matches the existing voice app: `gemini-2.5-flash-native-audio-preview-12-2025`; verify availability with the team's key. Connection failure stops the app; movement never automatically resumes after reconnecting.

## Deploy from the Mac

Copy only these new files; preserve the team's apps and credentials:

```bash
cd /Users/yehyunlee/Documents/Repositories/HTN/NAVI/apps/navi
scp assistant.py test_assistant.py ASSISTANT.md bracketbot@bracketbot-189.local:/home/bracketbot/NAVI/apps/navi/
```

## Verification

The final script and checksum-verified detector are installed on the Jetson. Simulated control/geometry and I/O-failure regression tests cover 29 cases. The Gemini synthetic smoke test completed a real function-call round trip and received 26,880 bytes of generated audio, without using robot I/O. The model supports 320-pixel input, benchmarked at about 0.20–0.25 seconds on the Jetson with two CPU threads (640-pixel input took about 1.1 seconds).

At the latest health check after reconnecting, depth and navigation status were publishing, but SLAM pose and mapping grid had no valid timestamp, so movement remained blocked. No physical motion, speaker playback or upload of actual room audio/video was performed during implementation. Real spoken interaction, correct person acquisition and physical obstacle avoidance still require supervised acceptance testing.

## References

- [Gemini Live API](https://ai.google.dev/gemini-api/docs/live-api) — audio/video and function calls.
- [OpenCV Zoo YOLOX](https://github.com/opencv/opencv_zoo/tree/main/models/object_detection_yolox) — COCO person detector; licensing upstream. Downloads are checked against SHA-256 `c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063`.
- Actual robot-side BBOS nav/depth/mapping/SLAM/mic/speaker source and existing `voice.py` were inspected for the topic and audio contracts.
