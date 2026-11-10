"""The shore: small things that makers far away leave on the beach and the pier, and the lamp in
the deckhouse window of the boat moored at the end of the pier, where the listener lives.

The shore kit (shorekit/, see shorekit/SCHEMA.md) judges every object and lays it out in whole
pixels of the 2880x1800 frame. This module replays the kit's record from a local cache, lights the
pixels the kit placed and draws them in front of the scenery, so the wallpaper shows exactly what
the kit agreed to: the same pixels, the same order, the same contact shadows.

Each object also throws a cast shadow that follows the sun through the day, and a bright moon at night
(kit 1.3.0): the scene's own shadow projection (land.shadow_masks), handed to the kit as whole numbers,
and the kit says which pixels are in shadow (shorekit.compose.cast_shown). So an upright thing on the
shore is a sundial, and the Mac and the kit's preview draw the same shadow pixels.

Objects are drawn in the front layer, so the fog veils them, and creatures and rare events are
drawn after them. Things that rest on the ground (the heron, a thing washed up) are hidden by any
object standing nearer than they do (`shore_allow`); everything airborne passes in front.

Without a cache (or with an empty record) nothing here draws, and the frame is the same, byte for
byte, as it would be without this module. The lamp only shows from dusk on a day it was lit.
"""
import datetime as dt
import json
import os
import sys

import numpy as np
from PIL import Image

from core import *  # noqa: F401,F403

# Every object pixel is lit with the normal of its face (east, north, up), which the kit reads off the
# bitmap's silhouette (shorekit.geometry.cell_face): FRONT faces the viewer and is tipped up, like the
# bench, the sheep and the cat; TOP faces up and a little south, as the beach under it does, so it
# catches the sky and the sun like the shingle; EAST and WEST are a cell's open left or right side (the
# viewer looks south), lit by a low morning or evening sun. The reference set's lights use the same ones.
UPRIGHT = (0.0, 0.8, 0.6)
FACES = (UPRIGHT, (0.0, -0.2, 0.98), (0.75, 0.35, 0.55), (-0.75, 0.35, 0.55))
# A pixel of an object's glow key emits this many times its albedo when the lamps are lit (the kit's
# compose.EMIT / 256), and the lit area throws a small halo, a pool on the ground and, on the pier, a
# streak on the water: one key per object and at most shorekit.GLOW_MAX_PX pixels, so it stays a lamp.
EMIT = 410 / 256
GLOW_CORE = np.array([255, 214, 150], np.float32)
GLOW_HALO = np.array([255, 176, 96], np.float32)
# The contact shadow takes this much of the light from the ground under an object's foot.
SHADOW = 0.45
# The cast shadow takes this much of the ground's light under a full sun (as the animals' do, fauna.life_shadow),
# scaled by how much sun gets through; under a full moon high in a clear sky it takes CAST_MOON, less under less.
# Direct light weaker than the first of CAST_FROM throws no shadow at all, and it is whole from the second: the
# sun's first degrees, cloud, and fog (the reference fog leaves 0.35 of the sun). The moon's light is counted as a
# share of MOON_FULL, core's moon_str for a full moon high in a clear, dark sky: only a bright moon throws one.
# And a shadow never takes more than the direct light puts on the beach (shore_direct): under a low sun, when most
# of the light there is the sky's, it is fainter than CAST.
CAST = 0.34
CAST_MOON = 0.30
CAST_FROM = (0.35, 0.6)
CAST_MOON_FROM = (0.55, 0.8)
MOON_FULL = 0.30
# The listener's window: two panes in the side of the boat's deckhouse, in boat units (see PropsMixin.boat)
PANES = ((-0.155, -0.098), (-0.072, -0.015))
PANE_Y = (-0.116, -0.080)
WINDOW = np.array([200, 120, 50], np.float32)     # lamplight through glass: warm, dimmer than the pier's lantern
KIT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def kit():
    """The shorekit package from this source tree; an installed copy needs shorekit/ beside renderers/."""
    if KIT_ROOT not in sys.path:
        sys.path.append(KIT_ROOT)
    import shorekit.cli
    import shorekit.compose
    import shorekit.errors
    import shorekit.ledger
    import shorekit.manifest
    import shorekit.reference
    return shorekit


def cast_vector(alt, az):
    """Which way a shadow falls from a light `alt` degrees up at azimuth `az`, as the kit takes it: (dx, dy), x256
    px of shadow per px of height, to the right and down the frame. It is the scene's own projection for the
    tower, the tree and the bench (land.shadow_masks), no longer than three times the height, rounded half up."""
    cot = min(1 / math.tan(math.radians(alt)), 3.0)
    q = lambda v: int(math.floor(256 * v + 0.5))
    return q(math.sin(math.radians(az)) * cot), q(-math.cos(math.radians(az)) * cot * KF)


def utc_stamp(t):
    """An aware datetime as the kit writes times: YYYY-MM-DDTHH:MM:SSZ."""
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def warn(text):
    sys.stderr.write("shore: %s\n" % text)


class ShoreDay:
    """What the shore shows over one local day, as plain arrays (cheap to hand to the workers).

    `sets` holds one entry per distinct set of objects on show during the day: the pixels to draw,
    in frame pixels of the reference frame size. `index[m]` is the entry for clock minute m, or -1."""

    def __init__(self, frame, reference, digest):
        self.frame = frame
        self.reference, self.digest = reference, digest
        self.ref = None         # the kit's reference set, for the cast shadows (the kit lays them out each minute)
        self.sets = []
        self.index = np.full(1441, -1, np.int32)
        self.live, self.misfits = [], []
        self.history = None     # the ledger's events as the story's echoes read them (History), with times

    def at(self, m):
        k = int(self.index[min(max(int(m), 0), 1440)])
        return None if k < 0 else self.sets[k]


class History:
    """The shore's history as the story's echoes read it (story.py), in plain numbers: no ids, names or pixels.

    adds: one (lands, seq, colour, gone) per object ever added, in seq order: when it landed and when the sea took it
    (None while it is still there), as UTC seconds, and its main colour (main_colour); seas: the time of each sea
    event, in order. The ledger never says why the sea took something, and neither does this."""

    def __init__(self, adds=(), seas=()):
        self.adds, self.seas = tuple(adds), tuple(seas)

    def upto(self, t):
        """The history as it stood at UTC second t: only the events at or before t."""
        return History(((lands, seq, c, gone if gone is not None and gone <= t else None)
                        for lands, seq, c, gone in self.adds if lands <= t), (at for at in self.seas if at <= t))


def seconds(stamp):
    """A kit time (YYYY-MM-DDTHH:MM:SSZ) as UTC seconds."""
    return dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()


def main_colour(p):
    """The paint an object is mostly made of (an albedo), from its own pixels, not its label board: the commonest,
    leaning toward a saturated one, so that a pennant of it shows against the sea."""
    counts = {}
    for i, rgb in p.solid.items():
        if i not in p.label:
            k = tuple(int(v) for v in rgb)
            counts[k] = counts.get(k, 0) + 1
    if not counts:
        return (128, 128, 128)

    def score(kv):
        c, n = kv
        hi, lo = max(c), min(c)
        return (n * (0.25 + ((hi - lo) / hi if hi else 0.0)), c)
    return max(counts.items(), key=score)[0]


def history(adds, gone):
    """The History of a replayed shore (replay's adds and gone)."""
    out = [(seconds(lands), p.seq, main_colour(p), seconds(gone[oid]) if oid in gone else None)
           for oid, (lands, p) in adds.items()]
    return History(sorted(out, key=lambda a: a[1]), sorted({seconds(t) for t in gone.values()}))


def reference_dir(path):
    """The reference set a shore cache is judged against: the one kit.lock names, else the newest there (ids
    only go up: r3 follows r2), so the set an earlier version built may stay beside the one in use."""
    sk = kit()
    lock = sk.cli.read_lock(path)
    base = os.path.join(path, "reference")
    if lock is not None:
        return os.path.join(base, lock["reference"])
    subs = [d for d in os.listdir(base) if sk.manifest.REF_RE.fullmatch(d)] if os.path.isdir(base) else []
    if not subs:
        raise ValueError("no reference set in %s" % base)
    return os.path.join(base, max(subs, key=lambda d: int(d[1:])))


def replay(path):
    """Replay a shore cache event by event. Returns (ref, shore, adds, gone): adds maps id -> (lands,
    Placed) in seq order; gone maps id -> the time the sea took it (a storm or the owner's veto: the
    ledger never says which)."""
    sk = kit()
    ref = sk.reference.load_reference(reference_dir(path))
    shore = sk.ledger.Shore(ref, os.path.join(path, "objects"))
    adds, gone = {}, {}
    lp = os.path.join(path, "ledger.json")
    if os.path.exists(lp):
        data = sk.ledger.read_bounded(lp, sk.ledger.LEDGER_MAX_BYTES, "E_LEDGER", "ledger.json")
        for ev in sk.ledger.parse_ledger(data):
            shore.apply(ev)
            if ev["event"] == "add":
                adds[ev["id"]] = (ev["lands"], shore.byid[ev["id"]])
            else:
                for oid in ev["takes"]:
                    gone[oid] = ev["at"]
    shore.finish()
    return ref, shore, adds, gone


def on_show(adds, gone, when):
    """The objects on show at UTC time `when`: landed, not yet taken, and standing on something."""
    out, ids = [], set()
    for oid, (lands, p) in adds.items():
        if lands > when or (oid in gone and gone[oid] <= when):
            continue
        if p.on not in ("shingle", "pier") and p.on not in ids:
            continue            # what it was built onto is not there (yet, or any more): nothing floats
        out.append(p)
        ids.add(oid)
    return out


def draw_set(ref, objs):
    """The kit's draw plan for these objects as arrays: the solid pixels on show (x, y, albedo, face,
    whether it glows, and the ground y of the object they belong to), the contact-shadow pixels on show,
    and, per object whose glow shows, where its lit area is. `objs` are the kit's own placed objects, which
    it lays the cast shadows out from, minute by minute."""
    sk = kit()
    sx, sy, rgb, gy, face, glow = [], [], [], [], [], []
    lamps = []          # per object whose glow shows: (x, y) of the lit area's middle, its pixels, ground y, on the pier
    shadow = set()
    surface = {o.id: o.surface for o in objs}
    for o in sk.compose.plan(ref, objs):
        gx = []
        for x, y, c, _, shown, f, g in o["solid"]:
            if shown:
                sx.append(x)
                sy.append(y)
                rgb.append(c)
                gy.append(o["ground_y"])
                face.append(f)
                glow.append(g)
                if g:
                    gx.append((x, y))
        if gx:
            lamps.append((sum(p[0] for p in gx) / len(gx) + 0.5, sum(p[1] for p in gx) / len(gx) + 0.5, len(gx),
                          o["ground_y"], surface.get(o["id"]) == "pier"))
        shadow.update((x, y) for x, y, shown in o["shadow"] if shown)
    hx = sorted(shadow)
    return dict(ids=tuple(o.id for o in objs), objs=tuple(objs),
                sx=np.array(sx, np.int32), sy=np.array(sy, np.int32), gy=np.array(gy, np.int32),
                rgb=np.array(rgb, np.uint8).reshape(-1, 3), face=np.array(face, np.int8),
                glow=np.array(glow, bool), lamps=lamps,
                hx=np.array([p[0] for p in hx], np.int32), hy=np.array([p[1] for p in hx], np.int32))


def load_shore(path, day):
    """The shore cache at `path` as it shows over `day`, or None when there is no cache. A cache the
    kit refuses draws nothing, with a warning, so the wallpaper keeps rendering."""
    if not path or not os.path.isdir(path):
        return None
    sk = kit()
    try:
        ref, shore, adds, gone = replay(path)
    except (sk.errors.ShoreError, ValueError, OSError) as e:
        warn("not drawing the shore: %s" % (e.line() if hasattr(e, "line") else e))
        return None
    sd = ShoreDay((ref.frame_w, ref.frame_h), ref.id, ref.digest)
    sd.ref = ref
    sd.live = [a.id for a in shore.live]
    sd.misfits = list(shore.misfits)
    sd.history = history(adds, gone)
    keys = {}
    for m in range(1441):
        objs = on_show(adds, gone, utc_stamp(day.utc[m]))
        if not objs:
            continue
        key = tuple(o.id for o in objs)
        if key not in keys:
            keys[key] = len(sd.sets)
            sd.sets.append(draw_set(ref, objs))
        sd.index[m] = keys[key]
    return sd


def lamp_lit(path, date, tz):
    """When the listener lit the lamp on local `date`, as an aware datetime, or None if it was not.

    The lamp-state file is {"version": 1, "lit": {"YYYY-MM-DD": "<ISO time with offset>"}}: a date is
    lit if and only if it is a key. A missing or unreadable file means nothing is lit."""
    try:
        with open(path, "rb") as f:
            obj = json.loads(f.read(1 << 20).decode("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(obj, dict) or obj.get("version") != 1 or not isinstance(obj.get("lit"), dict):
        return None
    when = obj["lit"].get(date.isoformat(), False)
    if when is False:
        return None
    start = dt.datetime.combine(date, dt.time(0, 0), tz)
    try:
        t = dt.datetime.fromisoformat(when)
        return t.replace(tzinfo=tz) if t.tzinfo is None else t
    except (TypeError, ValueError):
        return start             # lit, at a time we cannot read: from dusk


class ShoreMixin:
    # --------------------------------------------------------------- objects --
    def shore_now(self):
        sd = getattr(self.day, "shore", None)
        return None if sd is None else sd.at(self.m)

    def shore_direct(self):
        """The share of the light on the beach (a TOP face) that comes straight from the sun and the moon: what a
        shadow there could take at most."""
        n = normalize(FACES[1])
        full, sky = float(self.light(n).mean()), float(self.light(n, shade=1.0).mean())
        return max(0.0, 1 - sky / full) if full > 0 else 0.0

    def shore_cast(self):
        """Which way the objects' cast shadows fall this minute, and how much of the ground's light they take:
        (dx, dy, strength), or None when nothing casts one. The light is the one the scene's own shadows use
        (land.shadow_masks): the sun while it is up, else the moon in the dark. The strength follows the light that
        gets through (as fauna.life_shadow's follows the sun), with none at all in weak light (CAST_FROM): under
        cloud, in fog, at the sun's first degrees, or under any moon but a bright one. It is never more than the
        direct light's share of the light on the beach."""
        if self.sun_alt > 1:
            alt, az, lit = self.sun_alt, self.sun_az, self.sun_str
            k = CAST * lit * sm(*CAST_FROM, lit)
        elif self.moon_alt > 4 and self.sun_alt < -6:
            alt, az, lit = self.moon_alt, self.moon_az, min(1.0, self.moon_str / MOON_FULL)
            k = CAST_MOON * lit * sm(*CAST_MOON_FROM, lit)
        else:
            return None
        k = min(k, self.shore_direct())
        if k < 1 / 256:
            return None
        return cast_vector(alt, az) + (float(k),)

    def shore_cast_pixels(self, st):
        """The ground in the objects' cast shadows this minute, as the kit lays it out for this light: (x, y) in
        frame pixels of the reference frame and the strength, or None. A reference set written before cast shadows
        (shore_conditions 1) has none in the kit's preview, so none are drawn here either: they come with the set."""
        cast = self.shore_cast()
        ref = getattr(self.day.shore, "ref", None)
        if cast is None or ref is None or ref.conditions_version < 2 or not st.get("objs"):
            return None
        idx = np.asarray(kit().compose.cast_shown(ref, st["objs"], cast[0], cast[1]), np.int64)
        if not idx.size:
            return None
        return (idx % ref.cw + ref.cx).astype(np.int32), (idx // ref.cw + ref.cy).astype(np.int32), cast[2]

    def shore(self):
        """Draw the objects on show into the front layer: lit, with their cast and contact shadows."""
        st = self.shore_now()
        if st is None:
            return
        fw, fh = self.day.shore.frame
        k = self.W / fw
        native = self.W == fw and self.H == fh
        sx, sy, gy = st["sx"], st["sy"], st["gy"]
        alb = st["rgb"].astype(np.float32)
        # sun or moon shadows of the tower, the tree, the bench and the lamp, where each object stands
        shade = sh = None
        if self.sun_alt > 1 or (self.moon_alt > 4 and self.sun_alt < -6):
            sh, _ = self.shadow_masks()
            shade = sh[np.clip((gy * k).astype(np.int32), 0, self.H - 1), np.clip((sx * k).astype(np.int32), 0, self.W - 1)]
        col = self.lit(alb, np.asarray(FACES, np.float32)[st["face"]], (sx + 0.5) * k, (sy + 0.5) * k, shade=shade)
        if self.lights_on > 0 and st["glow"].any():
            col[st["glow"]] += alb[st["glow"]] * (EMIT * self.lights_on)
        # the cast shadows: where the kit says, and only as dark as the light the scenery's own shadows leave there
        cast = self.shore_cast_pixels(st)
        if cast is not None:
            tx, ty, tk = cast
            tk = tk * (1 - sh[np.clip((ty * k).astype(np.int32), 0, self.H - 1), np.clip((tx * k).astype(np.int32), 0, self.W - 1)])
        if native:
            c, a = self.c, self.a
            hx, hy = st["hx"], st["hy"]
            if cast is not None:
                c[ty, tx] = c[ty, tx] * (1 - tk)[:, None]
                a[ty, tx] = a[ty, tx] * (1 - tk) + tk
            c[hy, hx] = c[hy, hx] * (1 - SHADOW)
            a[hy, hx] = a[hy, hx] * (1 - SHADOW) + SHADOW
            c[sy, sx] = col
            a[sy, sx] = 1.0
            return
        # another frame size (a preview): lay the native pixels out on a patch and resample it
        xs = np.concatenate([sx, st["hx"]] + ([tx] if cast is not None else []))
        ys = np.concatenate([sy, st["hy"]] + ([ty] if cast is not None else []))
        x0, y0 = int(xs.min()), int(ys.min())
        w, h = int(xs.max()) - x0 + 1, int(ys.max()) - y0 + 1
        pc = np.zeros((h, w, 3), np.float32)
        pa = np.zeros((h, w), np.float32)
        if cast is None:
            pa[st["hy"] - y0, st["hx"] - x0] = SHADOW
        else:
            pa[ty - y0, tx - x0] = tk
            pa[st["hy"] - y0, st["hx"] - x0] = pa[st["hy"] - y0, st["hx"] - x0] * (1 - SHADOW) + SHADOW
        pc[sy - y0, sx - x0] = col
        pa[sy - y0, sx - x0] = 1.0
        X0, Y0 = int(math.floor(x0 * k)), int(math.floor(y0 * k))
        X1, Y1 = min(self.W, int(math.ceil((x0 + w) * k))), min(self.H, int(math.ceil((y0 + h) * k)))
        if X1 <= X0 or Y1 <= Y0:
            return
        size = (X1 - X0, Y1 - Y0)
        rs = lambda p: np.asarray(Image.fromarray(np.ascontiguousarray(p), "F").resize(size, Image.BOX), np.float32)
        al = rs(pa)
        # premultiplied, a shadow is black: it only takes light away from what is under it
        rgb = np.stack([rs(pc[..., i]) for i in range(3)], -1) / np.maximum(al, 1e-6)[..., None]
        self.over(Y0, Y1, X0, X1, rgb, al[..., None])

    def shore_allow(self, L, ground_y):
        """For a layer of something resting on the ground at frame row ground_y (the heron, a thing
        washed up): 1 where it may show, 0 where an object standing nearer hides it. None if nothing does."""
        st = self.shore_now()
        if st is None or not L.ok:
            return None
        k = self.W / self.day.shore.frame[0]
        near = st["gy"] * k > ground_y
        x = (st["sx"][near] * k).astype(np.int32) - L.x0
        y = (st["sy"][near] * k).astype(np.int32) - L.y0
        inside = (x >= 0) & (x < L.x1 - L.x0) & (y >= 0) & (y < L.y1 - L.y0)
        if not inside.any():
            return None
        allow = np.ones((L.y1 - L.y0, L.x1 - L.x0), np.float32)
        allow[y[inside], x[inside]] = 0.0
        return allow

    def shore_lamps(self):
        """The lit areas of the objects on show, in this frame's pixels: (x, y, size, ground y, on the pier),
        with size the side of a square of the same area. Empty unless the lamps are on."""
        st = self.shore_now()
        if st is None or self.lights_on <= 0 or not st["lamps"]:
            return []
        k = self.W / self.day.shore.frame[0]
        return [(x * k, y * k, math.sqrt(n) * k, g * k, pier) for x, y, n, g, pier in st["lamps"]]

    def shore_pools(self):
        """Lamplight on the ground and on things near an object's lit area (FrameBase's pools)."""
        for x, y, a, g, _ in self.shore_lamps():
            self.pools.append((x, y, g, WARM, 5.0 * a, 0.35 * self.lights_on))

    def shore_emitters(self):
        """A lit thing on the pier shows on the water under it, like the pier's lantern."""
        dy = self.pier_water_y() - float(self.pproj(*self.pier_pt(1.0, -0.1, PIER3["deck"]))[1])
        for x, y, a, g, pier in self.shore_lamps():
            if pier:
                self.emitters.append((x, y, GLOW_HALO, 0.06 * a * self.lights_on, g + dy))

    def shore_glow(self):
        """The halo of each lit area in the night air, after the fog, with the scene's other lamps."""
        on = self.lights_on
        for x, y, a, _, _ in self.shore_lamps():
            self.glow(x, y, 0.55 * a, GLOW_CORE, 0.45 * on)
            self.glow(x, y, 3.5 * a, GLOW_HALO, 0.14 * on, tail=0.3)

    # -------------------------------------------------------------- the lamp --
    def listener_lamp(self):
        """How brightly the listener's window shows: 0 unless the lamp was lit today and that moment
        has passed, then the scene's own dusk ramp (it comes on with the other lamps)."""
        lit = getattr(self.day, "lamp_lit", None)
        if lit is None or self.day.local[min(self.m, 1440)] < lit:
            return 0.0
        return float(self.lights_on)

    def window_xy(self, cx, cy, size):
        """Frame position of each pane's middle (the boat is moored facing left)."""
        ym = cy + 0.5 * (PANE_Y[0] + PANE_Y[1]) * size
        return [(cx - 0.5 * (a + b) * size, ym) for a, b in PANES]

    def listener_window(self, cx, cy, size):
        """The lit panes in the side of the deckhouse; drawn with the boat, so whatever stands in front hides them."""
        k = self.listener_lamp()
        if k <= 0:
            return
        L = Layer(self, cx - 0.3 * size, cy - 0.2 * size, cx + 0.3 * size, cy)
        for a, b in PANES:
            pts = [(cx - a * size, cy + PANE_Y[0] * size), (cx - b * size, cy + PANE_Y[0] * size),
                   (cx - b * size, cy + PANE_Y[1] * size), (cx - a * size, cy + PANE_Y[1] * size)]
            L.poly(pts, WINDOW, a=k)
        L.composite()

    def listener_emitter(self):
        """The window's reflection on the water (the sea is drawn before the boat)."""
        k = self.listener_lamp()
        if k <= 0:
            return
        size = 170 * self.s
        cx, cy = MOORED[0] * self.W, MOORED[1] * self.H
        pts = self.window_xy(cx, cy, size)
        self.emitters.append((float(np.mean([p[0] for p in pts])), pts[0][1], WINDOW, 0.45 * k, cy + 0.1 * size))

    def listener_glow(self):
        """The window's glow in the night air, with the scene's other lamps."""
        k = self.listener_lamp()
        if k <= 0 or self.day.events.boat(self.t):
            return
        s, size = self.s, 170 * self.s
        pts = self.window_xy(MOORED[0] * self.W, MOORED[1] * self.H, size)
        x, y = float(np.mean([p[0] for p in pts])), pts[0][1]
        self.glow(x, y, 22 * s, (255, 170, 90), 0.18 * k, tail=0.3)
