# Demo footage handoff

The draft is 53 seconds. Three calm slates mark the missing footage; no
video files are currently required to preview it.

| Section | Timeline | Clip length | Filename |
| --- | --- | --- | --- |
| Navigation | 9–19s | 10s | navigation.mp4 |
| NFC access | 24–31s | 7s | nfc.mp4 |
| Walking meeting | 37–49s | 12s | meeting.mp4 |

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

## Replace a placeholder

Place the three files in this directory. For each sub-composition below, remove
the complete div with the matching placeholder id. Insert the video markup
inside the existing root. Leave its template, stylesheet, script, and host
in index.html intact.

Media time is local to that chapter (starts at zero); the host in index.html
owns its position in the whole film. Paths below resolve from the project root.

### Navigation demo

File: compositions/demo-navigation.html
Remove: div#demo-navigation-placeholder

```html
<video id="demo-navigation-video" class="demo-video clip"
  src="assets/demo/navigation.mp4"
  data-start="0" data-duration="10" data-track-index="0"
  muted playsinline></video>
```

If this clip's recorded audio is cleared and should be audible, also insert:

```html
<audio id="demo-navigation-audio" class="clip"
  src="assets/demo/navigation.mp4"
  data-start="0" data-duration="10"
  data-track-index="1" data-volume="1"></audio>
```

### NFC demo

File: compositions/demo-access.html
Remove: div#demo-access-placeholder

```html
<video id="demo-access-video" class="demo-video clip"
  src="assets/demo/nfc.mp4"
  data-start="0" data-duration="7" data-track-index="0"
  muted playsinline></video>
```

If this clip's recorded audio is cleared and should be audible, also insert:

```html
<audio id="demo-access-audio" class="clip"
  src="assets/demo/nfc.mp4"
  data-start="0" data-duration="7"
  data-track-index="1" data-volume="1"></audio>
```

### Walking meeting demo

File: compositions/demo-meeting.html
Remove: div#demo-meeting-placeholder

```html
<video id="demo-meeting-video" class="demo-video clip"
  src="assets/demo/meeting.mp4"
  data-start="0" data-duration="12" data-track-index="0"
  muted playsinline></video>
```

If this clip's recorded audio is cleared and should be audible, also insert:

```html
<audio id="demo-meeting-audio" class="clip"
  src="assets/demo/meeting.mp4"
  data-start="0" data-duration="12"
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
