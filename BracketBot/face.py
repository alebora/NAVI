# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "pygame-ce",
# ]
# ///
"""NAVI's face on the DisplayPort screen.

    uv run face.py                  # fullscreen on the attached display
    uv run face.py --windowed       # 1280x720 window, for working over VNC/X
    uv run face.py --demo           # cycle every state, no other processes needed

The expression comes from the `face` topic on the little /dev/shm/navi bus, and
badge taps come from `badge`, so this process owns nothing but the screen:

    voice.py       -> face: listening / thinking / speaking
    nfc_bridge.py  -> badge: {uid, name}      -> greets the person by name

Deliberately no microphone here. The BBOS `mic` daemon owns the capture device
and voice.py already consumes mic.audio through shared memory, so a second
listener (the Vosk/PyAudio version of this script) would contend for the same
hardware and burn CPU duplicating speech recognition Gemini is already doing.
"""

import argparse
import math
import os
import sys
import time

import bus

BLACK = (0, 0, 0)
CYAN_BLUE = (60, 170, 255)
RED = (230, 40, 40)
BLUE = (40, 120, 235)
WHITE = (240, 244, 255)

GREET_SECONDS = 4.0
POLL_HZ = 10
STATES = ("IDLE", "LISTENING", "THINKING", "SPEAKING", "RECORDING", "ELEVATOR")


def init_display(windowed):
    """Bring up a surface with or without an X server.

    On this Jetson there is usually no X session, so SDL talks to the kernel
    modesetting driver directly. kmsdrm needs the display attached at boot,
    because tegra-drm only enumerates connectors during probe.
    """
    import pygame

    candidates = []
    if os.environ.get("SDL_VIDEODRIVER"):
        candidates.append(os.environ["SDL_VIDEODRIVER"])
    elif os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        candidates += ["x11", "wayland", "kmsdrm"]
    else:
        candidates += ["kmsdrm", "x11"]

    errors = []
    for driver in candidates:
        os.environ["SDL_VIDEODRIVER"] = driver
        try:
            pygame.display.quit()
            pygame.display.init()
        except pygame.error as e:
            errors.append(f"{driver}: {e}")
            continue

        try:
            if windowed:
                surface = pygame.display.set_mode((1280, 720))
            else:
                info = pygame.display.Info()
                surface = pygame.display.set_mode(
                    (info.current_w, info.current_h), pygame.FULLSCREEN
                )
        except pygame.error as e:
            errors.append(f"{driver}: {e}")
            continue

        print(f"[face] video driver: {driver} "
              f"{surface.get_width()}x{surface.get_height()}", flush=True)
        return surface

    print("[face] could not open a display. Tried:", flush=True)
    for e in errors:
        print(f"         {e}", flush=True)
    print("[face] If the monitor was plugged in after boot, reboot with it "
          "connected and powered on: tegra-drm only finds connectors at probe "
          "time (`sudo modetest -M tegra -c` should list a connected output).",
          flush=True)
    sys.exit(1)


def pick_font(pygame, size, bold=True):
    """A font that actually exists on a headless Jetson."""
    for name in ("dejavusans", "liberationsans", "freesans", "arial"):
        path = pygame.font.match_font(name, bold=bold)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


# Eyes sit above centre and the mouth below it, so the two never overlap.
EYE_CY = 0.40
MOUTH_CY = 0.74


def draw_eyes(pygame, surface, w, h, blink, colour):
    eye_w = int(w * 0.11)
    eye_h = max(2, int(int(h * 0.34) * blink))
    radius = eye_w // 2
    spacing = int(w * 0.16)
    cx, cy = w // 2, int(h * EYE_CY)
    y = cy - eye_h // 2
    for x in (cx - spacing - eye_w // 2, cx + spacing - eye_w // 2):
        pygame.draw.rect(surface, colour, pygame.Rect(x, y, eye_w, eye_h),
                         border_radius=radius)


def draw_smile(pygame, surface, w, h, openness, curve, colour):
    """A parabolic mouth under the eyes.

    curve    1.0 = happy upturn, 0.0 = flat.
    openness 0.0 = a drawn line, 1.0 = jaw fully open (mid-syllable).

    Drawn as a thick polyline rather than pygame.draw.arc, which produces a
    thin, visibly jagged curve at the sizes this screen uses.
    """
    cx = w // 2
    cy = int(h * MOUTH_CY)
    half = int(w * 0.155)
    depth = int(h * 0.085 * curve)
    thickness = max(8, int(h * 0.026))

    def parabola(scale):
        pts = []
        for i in range(25):
            t = -1.0 + 2.0 * i / 24
            pts.append((cx + int(t * half), cy + int(depth * (1 - t * t) * scale)))
        return pts

    if openness < 0.05:
        pts = parabola(1.0)
        pygame.draw.lines(surface, colour, False, pts, thickness)
        # Round off the ends; pygame leaves polylines with square corners.
        for end in (pts[0], pts[-1]):
            pygame.draw.circle(surface, colour, end, thickness // 2)
        return

    # Open mouth: upper and lower lips bow apart, filled so it reads at distance.
    gap = int(h * 0.10 * openness)
    upper = parabola(1.0)
    lower = [(x, y + gap) for x, y in parabola(1.0 + 0.5 * openness)]
    pygame.draw.polygon(surface, colour, upper + lower[::-1])


def draw_listening_dots(pygame, surface, w, h, t):
    """Three dots bobbing below the mouth: NAVI has the mic open."""
    cx, cy = w // 2, int(h * 0.91)
    gap = int(w * 0.045)
    r = max(4, int(h * 0.018))
    for i in (-1, 0, 1):
        lift = math.sin(t * 6 + i * 0.9) * h * 0.02
        pygame.draw.circle(surface, CYAN_BLUE, (cx + i * gap, int(cy - lift)), r)


def draw_recording_symbol(pygame, surface, w, h, progress):
    cx, cy = w // 2, h // 2
    scale = progress
    mic_w = int(w * 0.12 * scale)
    mic_h = int(h * 0.30 * scale)
    if mic_w < 4 or mic_h < 4:
        return
    mic_x = cx - mic_w // 2
    mic_y = cy - mic_h // 2 - int(20 * scale)
    pygame.draw.rect(surface, RED, (mic_x, mic_y, mic_w, mic_h),
                     border_radius=mic_w // 2)

    arc_r = int(mic_w * 1.1)
    arc = pygame.Rect(cx - arc_r, mic_y + mic_h // 2, arc_r * 2, arc_r)
    if arc.width > 2 and arc.height > 2:
        pygame.draw.arc(surface, RED, arc, math.pi, 2 * math.pi,
                        max(4, int(6 * scale)))

    stem_top = mic_y + mic_h + int(10 * scale)
    stem_bottom = stem_top + int(40 * scale)
    width = max(4, int(6 * scale))
    pygame.draw.line(surface, RED, (cx, stem_top), (cx, stem_bottom), width)
    pygame.draw.line(surface, RED, (cx - int(30 * scale), stem_bottom),
                     (cx + int(30 * scale), stem_bottom), width)


def draw_elevator_symbol(pygame, surface, w, h, progress, floor):
    cx, cy = w // 2, h // 2
    offset = int(w * 0.22 * progress)
    size = int(h * 0.18 * progress)
    if size > 5:
        ax = cx - offset
        pygame.draw.polygon(surface, BLUE, [
            (ax, cy - size), (ax - size, cy + size // 2), (ax + size, cy + size // 2)])
        pygame.draw.rect(surface, BLUE, pygame.Rect(
            ax - size // 3, cy + size // 2, int(size / 1.5), int(size * 0.8)))

    if progress > 0.3:
        font = pick_font(pygame, int(h * 0.45 * progress))
        text = font.render(str(floor), True, BLUE)
        surface.blit(text, text.get_rect(
            center=(cx + offset, cy + int(10 * progress))))


def draw_greeting(pygame, surface, w, h, name, fade):
    """Name across the middle of the face right after a badge tap."""
    overlay = pygame.Surface((w, h), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, int(190 * fade)))
    surface.blit(overlay, (0, 0))

    big = pick_font(pygame, int(h * 0.16))
    small = pick_font(pygame, int(h * 0.06), bold=False)
    hello = big.render(f"Hi, {name}!", True, WHITE)
    sub = small.render("Ask me where to go", True, CYAN_BLUE)
    surface.blit(hello, hello.get_rect(center=(w // 2, int(h * 0.44))))
    surface.blit(sub, sub.get_rect(center=(w // 2, int(h * 0.60))))


def main():
    ap = argparse.ArgumentParser(description="NAVI animated face")
    ap.add_argument("--windowed", action="store_true")
    ap.add_argument("--demo", action="store_true",
                    help="cycle through every state to prove the screen works")
    args = ap.parse_args()

    import pygame

    pygame.init()
    surface = init_display(args.windowed)
    pygame.mouse.set_visible(False)
    pygame.display.set_caption("NAVI")
    clock = pygame.time.Clock()
    W, H = surface.get_size()

    state = "IDLE"
    floor = 3
    progress = 0.0            # 0 = eyes, 1 = symbol fully shown
    blinking = False
    blink_timer = 0.0
    blink_every = 3.0
    blink_len = 0.15
    next_blink = time.time() + blink_every

    badge_watch = bus.Latest("badge")
    face_watch = bus.Latest("face")
    greet_name, greet_until = None, 0.0
    next_poll = 0.0
    last = time.time()
    t0 = last

    if args.demo:
        print(f"[face] demo mode: cycling {', '.join(STATES)}", flush=True)
    else:
        print("[face] waiting on the `face` and `badge` topics "
              "(run voice.py and nfc_bridge.py)", flush=True)

    running = True
    while running:
        now = time.time()
        dt = now - last
        last = now

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_ESCAPE, pygame.K_q):
                running = False

        if args.demo:
            state = STATES[int((now - t0) / 2.5) % len(STATES)]
            if greet_name is None and int(now - t0) % 15 == 14:
                greet_name, greet_until = "Ada", now + GREET_SECONDS
        elif now >= next_poll:
            next_poll = now + 1.0 / POLL_HZ
            update = face_watch.poll()
            if update:
                want = str(update.get("state", "IDLE")).upper()
                if want in STATES and want != state:
                    state = want
                    print(f"[face] {state.lower()}", flush=True)
                floor = update.get("floor", floor)
            tap = badge_watch.poll()
            if tap:
                greet_name = tap.get("name") or "there"
                greet_until = now + GREET_SECONDS
                print(f"[face] greeting {greet_name}", flush=True)

        symbolic = state in ("RECORDING", "ELEVATOR")
        progress = (min(1.0, progress + dt * 5) if symbolic
                    else max(0.0, progress - dt * 4))

        if symbolic:
            blink = 0.0
        else:
            if blinking:
                blink_timer -= dt
                if blink_timer <= 0:
                    blinking = False
                    next_blink = now + blink_every
            elif now > next_blink:
                blinking = True
                blink_timer = blink_len
            blink = (max(0.1, abs(math.sin((blink_timer / blink_len) * math.pi)))
                     if blinking else 1.0)

        surface.fill(BLACK)
        if progress < 1.0:
            draw_eyes(pygame, surface, W, H, blink, CYAN_BLUE)
            if state == "SPEAKING":
                # Two mixed rates, so the jaw does not flap like a metronome.
                jaw = abs(math.sin(now * 11) * math.sin(now * 3.3))
                draw_smile(pygame, surface, W, H, 0.25 + 0.75 * jaw, 1.0, CYAN_BLUE)
            elif state == "THINKING":
                draw_smile(pygame, surface, W, H, 0.0, 0.35, CYAN_BLUE)
                draw_listening_dots(pygame, surface, W, H, now * 0.4)
            else:
                draw_smile(pygame, surface, W, H, 0.0,
                           0.85 + 0.15 * math.sin(now * 1.6), CYAN_BLUE)
                if state == "LISTENING":
                    draw_listening_dots(pygame, surface, W, H, now)

        if state == "RECORDING" and progress > 0:
            draw_recording_symbol(pygame, surface, W, H, progress)
        elif state == "ELEVATOR" and progress > 0:
            draw_elevator_symbol(pygame, surface, W, H, progress, floor)

        if greet_name and now < greet_until:
            remaining = greet_until - now
            draw_greeting(pygame, surface, W, H, greet_name,
                          min(1.0, remaining / 0.4))
        elif greet_name:
            greet_name = None

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[face] stopped", flush=True)
