# /// script
# requires-python = ">=3.10"
# dependencies = ["bbos", "numpy", "pyyaml", "pillow"]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/bbos", editable = true }
# ///
"""Tie the SLAM frame to the venue floor plans (1.png .. 7.png).

SLAM has no idea which building it is in: its origin is wherever the robot was
switched on. floorplan.yaml says where landmarks and rooms are on the drawings.
The link between the two is a handful of *anchors*: drive the robot to a
landmark, stand still, and record the live SLAM pose against that landmark's
plan position. Two anchors on a floor fix a similarity transform (rotation,
uniform scale, translation); a third or more exposes a bad one via residuals.
Once a floor is fitted, every room drawn on the plan is a drive target and the
robot can say which room it is standing in.

  uv run floorplan.py landmarks                 # what you can anchor on
  uv run floorplan.py rooms 2                   # rooms drawn on floor 2
  uv run floorplan.py anchor 2 "e5 elevators"   # robot is standing there now: record it
  uv run floorplan.py anchors                   # list, with fit residuals per floor
  uv run floorplan.py forget 2 "e5 elevators"   # drop a bad anchor
  uv run floorplan.py fit 2                     # scale (px/m), rotation, residuals
  uv run floorplan.py where 2                   # which room the robot is in right now
  uv run floorplan.py goal 2 "sponsor bay"      # SLAM x,y for a room (no driving)
  uv run floorplan.py go 2 "sponsor bay"        # drive there via the nav daemon
  uv run floorplan.py render 2 /tmp/f2.png      # plan + SLAM floor cells + robot

Coordinates: plan positions are normalised (u, v) with origin top-left, as in
floorplan.yaml. Internally they become an isotropic, y-up "plan metre" frame
(u * aspect, 1 - v) so a similarity transform is legitimate on non-square images.
"""
import math
import struct
import sys
import time
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
PLAN_FILE = HERE / "floorplan.yaml"
ANCHORS_FILE = HERE / "anchors.yaml"
MIN_ANCHORS = 2


# -- data ----------------------------------------------------------------------

def load_plan():
    return yaml.safe_load(PLAN_FILE.read_text()) or {}


def load_anchors():
    """{floor: [ {landmark, u, v, x, y, yaw, time}, ... ]}"""
    if not ANCHORS_FILE.exists():
        return {}
    raw = yaml.safe_load(ANCHORS_FILE.read_text()) or {}
    return {int(k): list(v) for k, v in raw.items()}


def save_anchors(anchors):
    ANCHORS_FILE.write_text(yaml.safe_dump(
        {int(k): v for k, v in anchors.items()}, sort_keys=True))


def landmark_uv(plan, name):
    lm = plan.get("landmarks", {}).get(_key(name))
    if lm is None:
        known = ", ".join(plan.get("landmarks", {}))
        raise KeyError(f"Unknown landmark '{name}'. Known: {known}")
    return float(lm["u"]), float(lm["v"])


def rooms_on(plan, floor):
    """{room name: (u, v)} for one floor."""
    rooms = plan.get("rooms", {}).get(int(floor), {}) or {}
    return {name: (float(r["u"]), float(r["v"])) for name, r in rooms.items()}


def _key(name):
    return " ".join(str(name).lower().split())


def _png_size(path):
    """(width, height) from the IHDR chunk; avoids decoding a 2 MB image."""
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    w, h = struct.unpack(">II", head[16:24])
    return w, h


_ASPECT = {}


def aspect_of(plan, floor):
    """width / height of that floor's drawing (cached)."""
    floor = int(floor)
    if floor not in _ASPECT:
        img = plan.get("images", {}).get(floor)
        if img and (HERE / img).exists():
            w, h = _png_size(HERE / img)
            _ASPECT[floor] = w / h
        else:
            _ASPECT[floor] = 1.0
    return _ASPECT[floor]


def _yup(uv, aspect):
    """normalised image (u, v) -> isotropic y-up plan frame (u * aspect, 1 - v)."""
    u, v = uv
    return np.array([u * aspect, 1.0 - v], dtype=float)


def _ydown(p, aspect):
    """inverse of _yup."""
    return float(p[0] / aspect), float(1.0 - p[1])


# -- similarity transform --------------------------------------------------------

class Transform:
    """p_plan = s * R(theta) @ p_slam + t   (and the inverse)."""

    def __init__(self, s, theta, t):
        self.s = float(s)
        self.theta = float(theta)
        self.t = np.asarray(t, dtype=float)

    @property
    def R(self):
        c, si = math.cos(self.theta), math.sin(self.theta)
        return np.array([[c, -si], [si, c]])

    def slam_to_plan(self, xy):
        return self.s * self.R @ np.asarray(xy, dtype=float) + self.t

    def plan_to_slam(self, p):
        return self.R.T @ ((np.asarray(p, dtype=float) - self.t) / self.s)

    def __repr__(self):
        return (f"Transform(scale={self.s:.4f} plan/m, rot={math.degrees(self.theta):.1f} deg, "
                f"t=({self.t[0]:.3f}, {self.t[1]:.3f}))")


def fit_similarity(src, dst):
    """Umeyama: least-squares s, R, t with  dst ~ s R src + t.  src, dst: (N, 2)."""
    src = np.asarray(src, dtype=float)
    dst = np.asarray(dst, dtype=float)
    if len(src) < 2 or src.shape != dst.shape:
        raise ValueError("need at least two matching point pairs")
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    var_s = (xs ** 2).sum() / len(src)
    if var_s < 1e-12:
        raise ValueError("anchors are at the same spot; drive further apart")
    cov = xd.T @ xs / len(src)
    U, D, Vt = np.linalg.svd(cov)
    S = np.eye(2)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[1, 1] = -1                    # no reflections: a map can't be mirrored
    R = U @ S @ Vt
    s = (D * np.diag(S)).sum() / var_s
    t = mu_d - s * R @ mu_s
    return Transform(s, math.atan2(R[1, 0], R[0, 0]), t)


def _pairs(plan, anchors, floor):
    """(slam xy, plan y-up xy) arrays for a floor's anchors."""
    aspect = aspect_of(plan, floor)
    rows = anchors.get(int(floor), [])
    src = np.array([[a["x"], a["y"]] for a in rows], dtype=float).reshape(-1, 2)
    dst = np.array([_yup((a["u"], a["v"]), aspect) for a in rows], dtype=float).reshape(-1, 2)
    return src, dst


def transform_for(floor, plan=None, anchors=None):
    """Transform for a floor, or None if it has fewer than MIN_ANCHORS anchors."""
    plan = plan or load_plan()
    anchors = anchors if anchors is not None else load_anchors()
    src, dst = _pairs(plan, anchors, floor)
    if len(src) < MIN_ANCHORS:
        return None
    return fit_similarity(src, dst)


def residuals(floor, plan=None, anchors=None):
    """[(landmark, error in metres)] per anchor: how well the fit explains each one."""
    plan = plan or load_plan()
    anchors = anchors if anchors is not None else load_anchors()
    T = transform_for(floor, plan, anchors)
    if T is None:
        return []
    out = []
    for a in anchors.get(int(floor), []):
        pred = T.plan_to_slam(_yup((a["u"], a["v"]), aspect_of(plan, floor)))
        out.append((a["landmark"], float(math.hypot(pred[0] - a["x"], pred[1] - a["y"]))))
    return out


def registered_floors(plan=None, anchors=None):
    """Floors with enough anchors to be driven on."""
    plan = plan or load_plan()
    anchors = anchors if anchors is not None else load_anchors()
    return sorted(f for f in anchors if len(anchors[f]) >= MIN_ANCHORS)


# -- queries voice.py uses ---------------------------------------------------------

def goal_for_room(floor, room, plan=None, anchors=None):
    """SLAM (x, y) for a room drawn on the plan, or None if the floor isn't fitted.
    Raises KeyError if the room isn't drawn on that floor."""
    plan = plan or load_plan()
    rooms = rooms_on(plan, floor)
    key = _key(room)
    if key not in rooms:
        raise KeyError(f"'{room}' is not drawn on floor {floor}. Drawn: {', '.join(rooms) or 'none'}")
    T = transform_for(floor, plan, anchors)
    if T is None:
        return None
    xy = T.plan_to_slam(_yup(rooms[key], aspect_of(plan, floor)))
    return float(xy[0]), float(xy[1])


def locate(x, y, floor, plan=None, anchors=None, near_m=6.0):
    """Where on floor `floor` is SLAM point (x, y)?

    Returns {"u", "v", "nearest": name, "distance_m", "inside": bool} or None if the
    floor isn't fitted. `nearest` is the closest room or landmark; `inside` is a
    coarse "close enough to say you're there" test."""
    plan = plan or load_plan()
    T = transform_for(floor, plan, anchors)
    if T is None:
        return None
    aspect = aspect_of(plan, floor)
    p = T.slam_to_plan((x, y))
    u, v = _ydown(p, aspect)

    candidates = dict(rooms_on(plan, floor))
    for name, lm in plan.get("landmarks", {}).items():
        candidates.setdefault(name, (float(lm["u"]), float(lm["v"])))

    best, best_d = None, float("inf")
    for name, uv in candidates.items():
        q = T.plan_to_slam(_yup(uv, aspect))
        d = math.hypot(q[0] - x, q[1] - y)
        if d < best_d:
            best, best_d = name, d
    return {"u": round(u, 4), "v": round(v, 4), "nearest": best,
            "distance_m": round(best_d, 2), "inside": best_d <= near_m}


# -- live robot --------------------------------------------------------------------

def _read_pose():
    import places
    return places.read_pose()


def record_anchor(floor, landmark, plan=None):
    plan = plan or load_plan()
    u, v = landmark_uv(plan, landmark)
    x, y, yaw = _read_pose()
    anchors = load_anchors()
    rows = [a for a in anchors.get(int(floor), []) if _key(a["landmark"]) != _key(landmark)]
    rows.append({"landmark": _key(landmark), "u": u, "v": v,
                 "x": round(x, 3), "y": round(y, 3), "yaw": round(yaw, 4),
                 "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    anchors[int(floor)] = rows
    save_anchors(anchors)
    return rows[-1]


RENDER_MAX_W = 2000


def _plan_image(plan, floor, max_w=RENDER_MAX_W):
    """The floor drawing at a sane size. The originals are 15657x10131 (630 MB
    decoded), so the first call reduces one and caches it under .cache/."""
    from PIL import Image
    img_name = plan.get("images", {}).get(int(floor))
    if not img_name:
        raise KeyError(f"no image for floor {floor}")
    cache = HERE / ".cache" / f"{Path(img_name).stem}_{max_w}.png"
    if not cache.exists():
        cache.parent.mkdir(exist_ok=True)
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(HERE / img_name) as full:
            factor = max(1, math.ceil(full.width / max_w))
            small = full.reduce(factor) if factor > 1 else full.copy()
        small.save(cache)
        del small
    return Image.open(cache).convert("RGBA")


def render_overlay(floor, out_path, plan=None, anchors=None, grid_timeout=3.0):
    """Draw the SLAM free-floor cells, anchors, rooms and the robot onto the plan image."""
    from PIL import Image, ImageDraw
    plan = plan or load_plan()
    anchors = anchors if anchors is not None else load_anchors()
    T = transform_for(floor, plan, anchors)
    img = _plan_image(plan, floor)
    W, H = img.size
    aspect = W / H
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    def to_px(uv):
        return uv[0] * W, uv[1] * H

    def slam_px(xy):
        return to_px(_ydown(T.slam_to_plan(xy), aspect))

    # rooms and landmarks from the drawing
    for name, uv in rooms_on(plan, floor).items():
        px, py = to_px(uv)
        draw.ellipse((px - 6, py - 6, px + 6, py + 6), outline=(0, 90, 200, 255), width=2)
        draw.text((px + 8, py - 6), name, fill=(0, 90, 200, 255))
    for name, lm in plan.get("landmarks", {}).items():
        px, py = to_px((lm["u"], lm["v"]))
        draw.rectangle((px - 4, py - 4, px + 4, py + 4), outline=(120, 120, 120, 255))

    if T is not None:
        # live free-floor cells from the mapping daemon
        try:
            from bbos import Config, Reader
            cell = float(Config("mapping").voxel_size_m)
            with Reader("mapping.grid2d", keeptime=False) as r:
                deadline = time.time() + grid_timeout
                grid = None
                while time.time() < deadline:
                    if r.ready():
                        grid = r.data
                        break
                    time.sleep(0.05)
            if grid is not None:
                fi, fj = np.where(grid["grid"] == 1)
                if len(fi) > 60000:
                    idx = np.random.choice(len(fi), 60000, replace=False)
                    fi, fj = fi[idx], fj[idx]
                ox, oy = grid["origin"]
                xs = ox + (fi + 0.5) * cell
                ys = oy + (fj + 0.5) * cell
                pts = (T.s * (T.R @ np.vstack([xs, ys])).T + T.t)
                px = pts[:, 0] / aspect * W
                py = (1.0 - pts[:, 1]) * H
                for a, b in zip(px, py):
                    draw.point((a, b), fill=(0, 200, 80, 160))
        except Exception as e:      # no daemon running is not an error for a render
            print(f"[floorplan] no live grid: {e}", file=sys.stderr)

        for a in anchors.get(int(floor), []):
            px, py = to_px((a["u"], a["v"]))
            qx, qy = slam_px((a["x"], a["y"]))
            draw.line((px, py, qx, qy), fill=(220, 60, 60, 255), width=2)
            draw.ellipse((qx - 5, qy - 5, qx + 5, qy + 5), fill=(220, 60, 60, 255))

        try:
            x, y, yaw = _read_pose()
            rx, ry = slam_px((x, y))
            hx, hy = slam_px((x + 0.5 * math.cos(yaw), y + 0.5 * math.sin(yaw)))
            draw.ellipse((rx - 9, ry - 9, rx + 9, ry + 9), fill=(255, 140, 0, 255))
            draw.line((rx, ry, hx, hy), fill=(255, 140, 0, 255), width=4)
        except Exception as e:
            print(f"[floorplan] no live pose: {e}", file=sys.stderr)
    else:
        draw.text((10, 10), f"floor {floor}: not fitted ({MIN_ANCHORS} anchors needed)",
                  fill=(220, 60, 60, 255))

    Image.alpha_composite(img, layer).convert("RGB").save(out_path)
    return out_path


# -- CLI ---------------------------------------------------------------------------

def main(argv):
    cmd = argv[1] if len(argv) > 1 else "help"
    plan = load_plan()
    anchors = load_anchors()

    if cmd == "landmarks":
        for name, lm in plan.get("landmarks", {}).items():
            hint = f"  - {lm['hint']}" if lm.get("hint") else ""
            print(f"{name:24s} u={lm['u']:.3f} v={lm['v']:.3f}{hint}")

    elif cmd == "rooms" and len(argv) == 3:
        for name, (u, v) in rooms_on(plan, argv[2]).items():
            print(f"{name:24s} u={u:.3f} v={v:.3f}")

    elif cmd == "anchor" and len(argv) == 4:
        a = record_anchor(argv[2], argv[3], plan)
        print(f"anchored floor {argv[2]} '{a['landmark']}' at slam x={a['x']} y={a['y']}")
        n = len(load_anchors().get(int(argv[2]), []))
        if n < MIN_ANCHORS:
            print(f"{MIN_ANCHORS - n} more anchor(s) needed before floor {argv[2]} can be used")
        else:
            for name, err in residuals(argv[2], plan):
                print(f"   residual {name:24s} {err:.2f} m")

    elif cmd == "forget" and len(argv) == 4:
        rows = [a for a in anchors.get(int(argv[2]), []) if _key(a["landmark"]) != _key(argv[3])]
        anchors[int(argv[2])] = rows
        save_anchors(anchors)
        print(f"floor {argv[2]}: {len(rows)} anchor(s) left")

    elif cmd == "anchors":
        if not anchors:
            print("no anchors yet: drive to a landmark and run  floorplan.py anchor <floor> <landmark>")
        for floor in sorted(anchors):
            res = dict(residuals(floor, plan, anchors))
            print(f"floor {floor}:" + ("" if res else f"  (need {MIN_ANCHORS}, have {len(anchors[floor])})"))
            for a in anchors[floor]:
                err = f"  residual {res[a['landmark']]:.2f} m" if a["landmark"] in res else ""
                print(f"   {a['landmark']:24s} slam=({a['x']:.2f}, {a['y']:.2f}){err}")

    elif cmd == "fit" and len(argv) == 3:
        T = transform_for(argv[2], plan, anchors)
        if T is None:
            raise SystemExit(f"floor {argv[2]} needs {MIN_ANCHORS} anchors")
        print(T)
        for name, err in residuals(argv[2], plan, anchors):
            print(f"   {name:24s} {err:.2f} m")

    elif cmd == "where" and len(argv) == 3:
        x, y, yaw = _read_pose()
        loc = locate(x, y, argv[2], plan, anchors)
        if loc is None:
            raise SystemExit(f"floor {argv[2]} is not fitted yet")
        print(f"slam ({x:.2f}, {y:.2f}) -> plan u={loc['u']:.3f} v={loc['v']:.3f}; "
              f"nearest '{loc['nearest']}' {loc['distance_m']} m away"
              + (" (there)" if loc["inside"] else ""))

    elif cmd in ("goal", "go") and len(argv) == 4:
        try:
            g = goal_for_room(argv[2], argv[3], plan, anchors)
        except KeyError as e:
            raise SystemExit(str(e))
        if g is None:
            raise SystemExit(f"floor {argv[2]} is not fitted yet")
        print(f"'{argv[3]}' on floor {argv[2]} -> slam x={g[0]:.2f} y={g[1]:.2f}")
        if cmd == "go":
            import places
            from bbos import Type, Writer
            try:
                writer = Writer("nav.command", Type("nav_command"), keeptime=False)
            except RuntimeError as e:
                raise SystemExit(f"{e} Stop navigation in the nav web UI and retry.")
            try:
                places.write_goal(writer, (g[0], g[1], None), True)
                print("   sent; watch nav.state in the nav UI or Ctrl-C to cancel")
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                places.write_goal(writer, None, False)
                writer.__exit__(None, None, None)

    elif cmd == "render" and len(argv) == 4:
        print(render_overlay(argv[2], argv[3], plan, anchors))

    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
