# NAVI — motion and demo edit

## Art direction

Simple editorial type, not a dashboard. One dominant message per beat.
Black canvas, white type, restrained blue highlights (#4ea3ff).
Footage slates use near-black (#090a0c) solely to distinguish unfinished footage.

Montserrat 700 for motion typography; 600 for demo titles; 500 for metadata.
Display size 174–300px, deliberately relaxed tracking (-0.052em).
Keep key content within the 10% title-safe inset.
No gradients, underlines, decorative rails, orbit rings, borders, fake telemetry,
or perpetual background movement.

## Choreography

- Per-word clip reveals adapted from registry caption-clip-wipe: the complete
  phrase stays in a stable layout as words accumulate.
- Occasional short vertical masked reveals, without bounce or rotation.
- Hand-set word timings vary by sentence; short closing words use clean cuts.
- Arrow, badge, and recording symbols appear only when they explain the action.
  SVG stroke lengths are measured, not guessed.
- Hard cuts separate ideas. Footage slots are calm holds, not 10-second
  loops of decorative animation.
- Intro and final brand lockup get two seconds each.
- All motion is driven by paused, deterministic GSAP timelines.

## Editorial rhythm

Fast introduction → navigation footage → NFC introduction → NFC footage →
walking-meeting introduction → walking footage → short brand close.

Footage is the proof, not a background texture. A 10-second navigation shot,
7-second badge sequence, and 12-second walking-meeting sequence have room to
breathe. Replace the whole slate with full-frame footage, without placeholder
labels or shot notes in the final cut.

## Schematic demos

Until footage exists, each demo slot is a "how it works" diagram in the same
language: grey line work (#4a4e55), grey labels (#8a8e95), one blue path or
state, white type. Every schematic is labeled in its eyebrow, masks badge IDs,
and states NFC's limits. Motion is deterministic: line draws, clip wipes, and
a polyline-interpolated travel (no DOM measurement inside callbacks).

## Editing

Eight separate sub-compositions appear in Studio. Each host has an explicit
start, duration, and graphics kind. Speech captions and music are not present.
The final follow/brand beats are separate local graphics tracks for quick editing.

See assets/demo/README.md for the footage handoff and exact integration markup.
The prior 29-second composition is preserved under
.hyperframes/backups/pre-demo-chapters.html.
