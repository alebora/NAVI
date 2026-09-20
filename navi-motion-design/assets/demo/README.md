# Demo footage handoff

The cut is 90 seconds. Each feature chapter now runs: typography title ->
animated schematic ("how it works") -> a LIVE FOOTAGE slot holding a shot brief.
The schematics stay; only the live slots are replaced with real video.

| Section | Timeline | Clip length | Filename |
| --- | --- | --- | --- |
| Navigation | 24–34s | 10s | navigation.mp4 |
| NFC access | 46–54s | 8s | nfc.mp4 |
| Walking meeting | 72–86s | 14s | meeting.mp4 |

## What to film

1. Navigation: an audible destination request, the robot guiding someone,
   and a clear arrival. Use one readable route, not several unrelated angles.
2. NFC: a close-up badge tap and visible access response. Hide identifiers.
3. Meeting: clear recording consent, a wider shot of NAVI following the
   participants, then the recording or summary result. Only include actual
   working behavior, and permission-cleared participants.

Shoot landscape. Prefer 1920×1080, 30fps, H.264 MP4 with AAC audio.
Trim each edit to the slot length before adding it. Do not rely on a short
clip auto-looping or holding its last frame. The default object-fit is contain
so screen details won't be cropped.

## Replace a schematic with footage

Place the three files in this directory. For each sub-composition below, remove
the complete div with the matching schematic id. Insert the video markup
inside the existing root. Leave its template, stylesheet, script, and host
in index.html intact.

Media time is local to that chapter (starts at zero); the host in index.html
owns its position in the whole film. Paths below resolve from the project root.

### Navigation (live)

File: compositions/live-navigation.html
Remove: div#live-navigation-slot

```html
<video id="live-navigation-video" class="demo-video clip"
  src="assets/demo/navigation.mp4"
  data-start="0" data-duration="10" data-track-index="0"
  muted playsinline></video>
```

If this clip's recorded audio is cleared and should be audible, also insert:

```html
<audio id="live-navigation-audio" class="clip"
  src="assets/demo/navigation.mp4"
  data-start="0" data-duration="10"
  data-track-index="1" data-volume="1"></audio>
```

### NFC access (live)

File: compositions/live-access.html
Remove: div#live-access-slot

```html
<video id="live-access-video" class="demo-video clip"
  src="assets/demo/nfc.mp4"
  data-start="0" data-duration="8" data-track-index="0"
  muted playsinline></video>
```

If this clip's recorded audio is cleared and should be audible, also insert:

```html
<audio id="live-access-audio" class="clip"
  src="assets/demo/nfc.mp4"
  data-start="0" data-duration="8"
  data-track-index="1" data-volume="1"></audio>
```

### Walking meeting (live)

File: compositions/live-meeting.html
Remove: div#live-meeting-slot

```html
<video id="live-meeting-video" class="demo-video clip"
  src="assets/demo/meeting.mp4"
  data-start="0" data-duration="14" data-track-index="0"
  muted playsinline></video>
```

If this clip's recorded audio is cleared and should be audible, also insert:

```html
<audio id="live-meeting-audio" class="clip"
  src="assets/demo/meeting.mp4"
  data-start="0" data-duration="14"
  data-track-index="1" data-volume="1"></audio>
```


## Preview and check

From the project directory:

```sh
npm run dev
npm run check -- --samples 32 --strict
```

Check the start and end of each inserted clip. If changing slot lengths,
update the host's duration, the child media duration, every following host start,
the main duration, and STORYBOARD.md together.

The backup of the previous motion-only edit is
.hyperframes/backups/pre-demo-chapters.html.

## Each live slot already carries its shot brief

Open `compositions/live-*.html` to see the exact beats to film, they are also
on screen in the current render, so anyone watching knows what is still missing.
Film in one take per slot, landscape, and trim to the slot length before adding.
