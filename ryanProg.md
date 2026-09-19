# Ryan's progress: NAVI voice + navigation

_Last updated: Sat Sep 19, 2026_

## TL;DR

- NAVI **talks**: voice conversation through the robot's mic and speaker works (Gemini Live).
- NAVI **can drive to saved places**: code is written and on the robot, not tested on the floor yet.
- Code is on branch `navi-voice-nav`, in `apps/navi/`.

## How the robot's software works (what we found)

The robot runs **bbos**: each piece of hardware is a background service ("daemon"), and apps talk to them through named shared-memory channels (`Reader("name")` / `Writer("name", Type(...))`).

| Channel | What it is | Used by us |
|---|---|---|
| `slam.pose` | robot position (x, y, heading) | yes, save places |
| `nav.command` | send goal waypoints to the built-in planner | yes, drive to a place |
| `nav.state` | planner status: `navigating` / `reached` / `failed` | yes |
| `mic.audio` / `speaker.audio` | robot mic in / speaker out | yes, voice |
| `arm_left.ctrl` / `arm_right.ctrl` | arm commands | next (elevator button) |
| `dataset.flag` | start/stop recording demos (Quest teleop) | next |

Key points:
- **Path planning and obstacle avoidance already exist** in the nav daemon. We only send it a goal.
- **Only one app can own `nav.command` at a time.** Press **Stop** in the nav web UI before running our apps.
- The robot's built-in `greeter` app already does Gemini Live voice. Our voice app is based on it.
- `mimic` / `greeter` replay recorded arm motions from JSON files. We can do the same for the elevator button.
- Dashboard for turning apps on and off: `https://bracketbot-189.local:8001`

## What's in `apps/navi/`

### `places.py`: save places and drive to them
```bash
uv run places.py where            # print current position
uv run places.py save judging     # save current spot as "judging"
uv run places.py forget judging
uv run places.py list
uv run places.py go judging       # drive there, prints progress until reached/failed
```
Places are stored in `places.yaml` next to the script. It always cancels the goal on exit, Ctrl+C, or timeout.

### `voice.py`: talk to NAVI
```bash
uv run voice.py --no-nav   # talk only, never drives (safe testing)
uv run voice.py            # full mode: "take me to judging" -> it drives there
```
- Prints what it heard (`[you ]`) and what it said (`[navi]`).
- Tools Gemini can call: `navigate_to(place)`, `save_place(place)`, `forget_place(place)`,
  `list_places`, `stop_navigation`.
- **Set up places by voice** — no laptop needed: push the robot to a spot and say
  "NAVI, remember this as the judging area." Saving is blocked while it's driving.
- Spoken names are matched loosely: "judging", "the judging area" and even "juding"
  all resolve to the saved `judging area`.
- Says out loud when it arrives or gets stuck. Saying "stop" halts it.
- Flags: `--mic-gain 5` if it can't hear you, `--volume 0.6`, `--voice Puck`.
- Stop the app: **Ctrl+C**.

## Running it on the robot

```bash
ssh bracketbot@bracketbot-189.local
cd ~/NAVI && git pull              # get latest code (repo is cloned on the robot)
cd ~/bbapps/navi                   # symlink to ~/NAVI/apps/navi
uv run voice.py --no-nav
```

Setup already done on robot 189:
- Repo cloned at `~/NAVI` (branch `navi-voice-nav`), symlinked to `~/bbapps/navi`.
- Gemini API key is in `~/bbapps/navi/.env`. It's **never committed**, and `.env` is git-ignored. Ask Ryan if you need the key.

To update code on the robot: push from your laptop, then `git pull` on the robot. No more `scp`.

## Status

| Thing | Status |
|---|---|
| Voice conversation (talk-only) | ✅ working on robot |
| `places.py where` (SLAM tracking) | ⏳ not tested |
| Save 3–4 places (CLI or by voice) | ⏳ not done |
| `places.py go <place>` (robot drives) | ⏳ not tested |
| Voice + driving ("take me to judging") | ⏳ not tested |
| NFC badge check-in | ❌ not started |
| Arm: elevator button press (Quest record + replay) | ❌ not started |
| Walking-meeting mode (record + summary) | ❌ not started |

## Next steps

1. `uv run places.py where`: confirm SLAM gives a position.
2. Drive around (WASD in the nav web UI) and `save` registration / judging / hardware.
3. `uv run places.py go judging`: first real drive. Keep someone next to the robot ready to press Ctrl+C.
4. `uv run voice.py`: "take me to judging".
5. Then: NFC badge → only allow certain places per badge; record an elevator-button press with the Quest.

## Gotchas

- **SSH drops / `scp` times out**: the robot's Wi-Fi is flaky. Retry `ssh`, and use `git pull` instead of `scp`.
- **"Writer for speaker.audio already exists"**: another app (e.g. greeter) is using the speaker. Turn it off in the dashboard.
- **"nav.command is owned by another app"**: press Stop in the nav web UI.
- The first `uv run` is slow because it installs packages. After that it's fast.
