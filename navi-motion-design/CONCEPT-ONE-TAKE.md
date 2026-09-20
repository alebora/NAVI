---
title: NAVI, "Inside Knowledge"
format: one continuous take, 90s, 16:9
status: concept / not yet shot
supersedes: nothing (STORYBOARD.md v2 remains the fallback cut)
---

# The idea in one line

**One unbroken 90-second shot, filmed in the building the judges are standing in,
with everything NAVI knows drawn onto the real floor in real time.**

No cuts, except one, at the very end, and it lands like a hammer *because* it is
the only one. A one-take is self-verifying: an audience cannot suspect a montage
of hiding the failures.

---

# Why this wins the room

Every other team's video is a screen recording with a voiceover. This one has:

1. **A real robot in the real venue.** Embodiment is the differentiator; lean on it.
2. **A one-take.** Impossible to fake, and everyone watching knows it.
3. **The floor lighting up.** The SLAM occupancy grid drawing itself across the
   actual carpet of E5, in perspective, is a shot nobody else will have.
4. **Real latency numbers on screen.** `replanned · 0.3 s` is a bigger flex than
   any adjective. Honesty reads as confidence.
5. **Strangers reacting.** People glancing at the robot in the hall is credibility
   that cannot be staged. Leave every one of them in.

---

# Shot script

Times are from the single take's timecode. The camera never stops moving.

## 0:00–0:08: The blue dot dies

Low, behind a visitor standing at a hallway junction, phone in hand. On the phone:
a GPS dot spinning and drifting. Ambient hackathon noise, muffled, no music.

Type, small, lower-left: `Indoors, the blue dot dies.`

Camera pushes past their shoulder down the corridor.

## 0:08–0:14: The arrival

Camera rounds the corner and finds NAVI idle, face monitor showing the idle smile.
**Music enters on the frame the eyes blink.** Type: `NAVI`. Camera orbits to the
visitor's side without cutting.

## 0:14–0:24: The tap

Visitor taps their badge on the PN532 reader.

**Speed ramp to ~10% for 1.2s**, not a cut. Graphics fly in around the badge:

```
UID  ••••••4A      read in 40 ms
Judging        ✓
Hardware       ✓
Staff lounge   ✕   staff only
```

Resume full speed as the face transitions to LISTENING (cyan dots). The access
decision *is* the product; the ramp makes a 200ms software event cinematic
without faking anything.

## 0:24–0:32: The ask

Visitor: *"Take me to judging."* Real voice, real audio. A single thin blue
waveform draws across the bottom of frame; the transcript types in sync at the
**actual** latency. Put the number on screen: `intent → route · 1.1 s`.

## 0:32–0:58: The floor lights up  ← hero section

NAVI turns and rolls. Camera follows at robot height, close, wide lens.

The SLAM grid blooms outward across the real floor in correct perspective:
free cells as a faint blue mesh, unknown space as void, and the planned route as
one bright ribbon running ahead of the robot down the real corridor.

Then **a group of people walks across the route.** The ribbon goes amber, snaps,
and re-solves through a different corridor, in frame, in real time.
Type: `replanned · 0.3 s`.

That moment is the proof it isn't scripted. Do not stage it too tightly; a real
crowd crossing is better than a rehearsed one.

## 0:58–1:12: The walking meeting

Two teammates fall in beside the robot mid-walk. One asks:
*"NAVI, record this, is everyone okay with that?"* Two nods, two spoken yeses.
**Keep the consent on camera, uncut.** Face switches to RECORDING; a slim REC
clock and waveform ride the lower third.

As they talk while walking, **pins drop onto the drawn map behind them**, each
decision anchored to the place it was said. This is the idea no one else has:
*meeting notes with coordinates.*

## 1:12–1:24: Arrival, and the only cut

NAVI stops. Face returns to the smile. *"You've arrived at judging."*

**Hard cut**, the first and last of the film, to a phone in hand, the real app,
the real summary:

```
3 decisions · 2 action items
"Ship the NFC gate before demos"     E5 · 2F corridor · 1:04
```

## 1:24–1:30: Lockup

Back wide on NAVI in the real hall, people around it.

`Guide. Verify. Remember.` → `NAVI` → then, small:

> Shot in one take at Hack the North. Badge IDs masked. Recorded with consent.

That last line is the mic drop: it tells the judges every frame was real.

---

# Production plan

**Crew:** one gimbal operator walking backward, one spotter, one person driving
the beat (badge tap → ask → crowd cross → consent). Three people total.

**Kit:** iPhone or mirrorless on a gimbal, wide lens, robot-height. A clapper
(or a hand clap) at the head of every take for audio/telemetry sync.

**Budget ~90 minutes on the floor and plan for ~15 takes.** You need one clean one.

**Capture real telemetry alongside the footage.** Run `assistant.py` with the BBOS
nav UI on `:8010` and screen-record it, starting on the same clap. Key every
overlay to that recording rather than inventing numbers, the honesty is the
whole point, and it is also *less* work than making values up.

**The one hard part** is the 3D floor grid. To make the camera solve easy:

- keep the camera at a consistent height and a steady, slow speed
- keep plenty of floor in frame at all times
- avoid whip pans; let the robot create the motion, not the operator
- shoot in a corridor with high-contrast floor features for the tracker to lock onto

**Fallback if the 3D solve fails:** a 2D-tracked ribbon on the floor still reads
beautifully. Do not let the grid block the edit.

**Fallback if the one-take cannot be landed:** shoot one take per chapter, the
"three-take" version keeps the same floor-grid language and about 80% of the
wow. The existing 58s typography cut in `STORYBOARD.md` remains a safe floor.

---

# Reusable from the current system

Art direction is unchanged: black canvas, white Lexend, `#1255CC` accent, no
gradients or fake telemetry. The overlays are the same visual language as
`compositions/`, they simply live on top of real footage instead of standing in
for it. `assets/demo/README.md` already describes the footage handoff.

---

# Optional cold open (5s, only if it earns its place)

A split screen with two running clocks: a human wandering to judging (`2:41`)
against NAVI escorting someone there (`0:52`). Cut to black on the gap, then
begin the one-take. Cheap to shoot and very persuasive, but only add it if it
does not dilute the "one unbroken shot" promise.

---

# Truth constraints (carry over from BRIEF.md)

- NFC is a prototype identity signal, not strong authentication. Say so on screen.
- Mask badge UIDs.
- Consent is shown on camera, not claimed in a caption.
- No arm or elevator interaction in this cut, it is not implemented.
- No fabricated footage, no mocked product screenshots, no invented latencies.
