#!/usr/bin/env python3
"""Build a reference set for the shore kit (shorekit/SCHEMA.md, section 5) from the renderer itself.

usage: tools/shore_reference.py OUT_DIR [--reference r1]

Renders four fixed minutes of one fixed day in the renderer's reference mode (no creatures, no rare
events, no grain, the tide at high water, the same weather all day) and writes into OUT_DIR:

  noon.png golden.png night.png fog.png   1280x640 crops of the shore (the graded frame, no JPEG)
  keepout.png      where nothing may stand: the pier's posts and rails, its bollards and lantern, the
                   gulls' perches, the moored boat and its line, the big stones on the dry shingle,
                   and every column left of the shore
  surfaces.json    the always-dry band per column, the pier deck, the tallest thing each row allows
  palette.json     the renderer's own albedos, the distance D a colour may stray from them, the plaque
  conditions.json  per minute: the light on an upright object, the tone curve, the vignette, the fog
  context.jpg      the noon frame, small, for people (the kit ignores it)

Two runs write the same bytes. Reference sets are shore data: write them outside this repository
(or under its ignored out/), never commit them.
"""
import argparse
import datetime as dt
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "renderers", "procedural"))
sys.path.insert(1, ROOT)

import listening_point as lp  # noqa: E402
from core import AZ_SPAN, PIER3, hill_edge_y, normalize, shore_band  # noqa: E402
from day import Day  # noqa: E402
from shore import SHADOW, UPRIGHT  # noqa: E402
from shorekit.png import write_png  # noqa: E402
from shorekit.reference import load_reference, point_in_polygon  # noqa: E402

DATE = dt.date(2027, 3, 21)       # the March equinox: a middling sun, a full moon high at night
SCALE = 0.75                      # the 2880 x 1800 frame
# (name, local clock time, weather): times are on the 10-minute keyframes, so a day's own render of that
# minute is the very same frame
CONDITIONS = (("noon", "11:50", "clear"), ("golden", "17:20", "clear"), ("night", "22:30", "clear"),
              ("fog", "10:00", "fog"))
CROP = dict(x=1600, y=1150, w=1280, h=640)
REGION = dict(x0=1640, y0=1150, x1=2879, y1=1789)
CELL = 16
DRY_V = (0.53, 1.0)      # the dry band, as fractions of the beach from low water (0) to the grass (1):
                         # high water reaches 0.5; the last rows are the grass's edge, where a sign may stand too
STONE_H = 12             # stones on the dry band at least this tall (px) are kept out; smaller ones are
                         # pebbles an object may stand over (keeping them out leaves no room for a label)
DRY_MIN = 4              # columns with a thinner dry band have none
MAX_H = 64               # the tallest object, in pixels, at the nearest rows' perspective of 1
D = 40                   # how far (redmean) a maker's colour may stray from the nearest albedo below
# The albedos the renderer paints the shore and its neighbours with (land.py, props.py, tower.py,
# life.py): what an object's colours must stay close to. Flowers are left out on purpose: in the
# scene they are specks, and as areas they would shout.
PALETTE = [
    ("rock", (134, 130, 122)), ("stone", (122, 118, 110)), ("shingle", (124, 116, 102)),
    ("wet-shingle", (62, 58, 51)), ("wrack", (58, 54, 40)), ("weed", (48, 52, 26)), ("lichen", (196, 132, 46)),
    ("wall-stone", (128, 124, 114)), ("capstone", (150, 146, 136)), ("set-stone", (116, 112, 104)),
    ("timber", (96, 80, 64)), ("old-timber", (118, 112, 102)), ("plank", (126, 96, 75)),
    ("bench-wood", (128, 86, 54)), ("door-wood", (96, 58, 36)), ("bark", (78, 64, 52)), ("twig", (70, 56, 40)),
    ("brass", (196, 156, 70)), ("dial-brass", (176, 136, 64)), ("iron", (34, 34, 38)), ("rail", (70, 70, 72)),
    ("lamp-glass", (170, 180, 190)), ("window", (42, 50, 62)), ("rope", (150, 140, 116)),
    ("sail", (240, 236, 222)), ("hull", (228, 226, 220)), ("hull-stripe", (40, 52, 84)),
    ("deckhouse", (214, 208, 196)), ("mast", (70, 62, 55)), ("life-ring", (210, 60, 48)),
    ("terracotta", (168, 86, 52)), ("tower-stone", (150, 140, 124)), ("tower-stone-light", (186, 176, 156)),
    ("mortar", (112, 104, 92)), ("moss", (78, 98, 54)), ("path", (150, 128, 98)),
    ("fleece", (228, 224, 212)), ("heron-grey", (150, 154, 162)),
    ("grass", (58, 80, 40)), ("grass-lush", (52, 94, 36)), ("grass-winter", (66, 82, 45)),
    ("grass-dry", (156, 142, 92)), ("tuft", (84, 112, 48)), ("tuft-light", (108, 124, 60)),
    ("straw", (176, 160, 104)), ("leaf-gold", (196, 150, 58)), ("leaf-rust", (170, 90, 40)),
    ("leaf-brown", (120, 84, 46)),
]
# The driftwood plaque a label is carved on: weathered grey-brown wood, the letters a shade darker, carved
# rather than inked, so a label reads up close and does not shout across the desktop
PLAQUE = {"wood": (136, 127, 110), "grain": (112, 104, 90), "ink": (74, 66, 56)}


def minute(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def rint(v):
    """Round half up, the same on every machine (no banker's rounding)."""
    return int(math.floor(float(v) + 0.5))


# ------------------------------------------------------------------ frames --
def render(day, m):
    """The frame for minute m as the day's own render would make it: uint8 (H, W, 3)."""
    lp.init_worker(day, SCALE, 10, None)
    return np.asarray(lp.frame_image(m), np.uint8)


def crop(img):
    return img[CROP["y"]:CROP["y"] + CROP["h"], CROP["x"]:CROP["x"] + CROP["w"]]


def tone_lut(night):
    """grade()'s tone curve without vignette or grain, for linear values 0..511: (3, 512) ints. Index w
    stands for the values w..w+1 the kit's integer arithmetic floors to it, so it is taken at w + 0.5."""
    c = np.repeat((np.arange(512, dtype=np.float32) + 0.5)[:, None], 3, 1)
    lp.tone(c, night)
    c += 0.5
    np.clip(c, 0, 255, out=c)
    return c.astype(np.uint8).T.astype(int)


def vignette_cells():
    vig, _ = lp.grade_maps(round(3840 * SCALE), round(2400 * SCALE))
    v = crop(vig).astype(np.float64).reshape(CROP["h"] // CELL, CELL, CROP["w"] // CELL, CELL).mean((1, 3))
    return [[rint(256 * x) for x in row] for row in v], crop(vig)


def veil(fr):
    """The fog over the front layer, per crop row: (alpha 0-1 per row, colour)."""
    H = fr.H
    probe = fr.fog_near(np.zeros((H, 1, 3), np.float32), np.ones((H, 1), np.float32))
    F = fr.fog_colour().astype(np.float64)
    c = int(np.argmax(F))
    a = probe[:, 0, c].astype(np.float64) / max(F[c], 1e-9)
    return a[CROP["y"]:CROP["y"] + CROP["h"]], F


def shadow_alpha(img, lut, vig, alpha, F, where):
    """The kit's contact shadow is one alpha over the crop's own colour; the renderer's takes SHADOW of
    the light from the ground under the fog. The alpha that fits best (least squares) where shadows fall."""
    ys, xs = np.nonzero(where)
    num = den = 0.0
    for ch in range(3):
        Dv = img[ys, xs, ch].astype(np.float64)
        t = np.asarray(lut[ch])
        lo = np.searchsorted(t, Dv, "left")
        hi = np.searchsorted(t, Dv, "right")
        w = (lo + np.maximum(hi - 1, lo)) / 2.0 + 0.5          # the linear value the display value came from
        v = vig[ys, xs].astype(np.float64)
        Lg = w / v
        ff = F[ch] * alpha[ys]
        dark = ((Lg - ff) * (1 - SHADOW) + ff) * v
        Ds = t[np.clip(np.floor(dark).astype(int), 0, 511)]
        num += float((Dv * Ds).sum())
        den += float((Dv * Dv).sum())
    return min(256, max(0, rint(256 * (1 - num / max(den, 1.0)))))


# ---------------------------------------------------------------- geometry --
def dry_band():
    """Per region column: the rows that stay dry at high water and are still shingle, or (-1, -1)."""
    W, H = round(3840 * SCALE), round(2400 * SCALE)
    top, bot = [], []
    for x in range(REGION["x0"], REGION["x1"] + 1):
        xn = np.array([(x + 0.5) / W], np.float32)
        e = float(hill_edge_y(xn)[0]) * H
        b = float(shore_band(xn)[0]) * H + 1e-3
        t = math.ceil(e + DRY_V[0] * b - 0.5)
        u = math.floor(e + DRY_V[1] * b - 0.5)
        t, u = max(t, REGION["y0"]), min(u, REGION["y1"])
        if u - t + 1 < DRY_MIN:
            t = u = -1
        top.append(t)
        bot.append(u)
    return top, bot


def deck_polygon(fr):
    """The deck's top as integer vertices: pixel (x, y) is on it when its centre is, one pixel in from each edge."""
    pts = []
    for u, v in ((0, 0), (1, 0), (1, 1), (0, 1)):
        x, y = fr.pproj(*fr.pier_pt(u, v, PIER3["deck"]))
        pts.append((float(x) - 0.5, float(y) - 0.5))
    cx, cy = np.mean([p[0] for p in pts]), np.mean([p[1] for p in pts])
    return [[rint(x + (1 if x < cx else -1)), rint(y + (1 if y < cy else -1))] for x, y in pts]


def max_heights():
    H = round(2400 * SCALE)
    out = []
    for y in range(REGION["y0"], REGION["y1"] + 1):
        persp = 0.35 + 1.3 * min(1.0, max(0.0, ((y + 0.5) / H - 0.6) / 0.4))
        out.append(max(1, rint(MAX_H * persp)))
    return out


def drawn(fr, method, *args, last=False):
    """Coverage of what one drawing method puts on an empty frame: (H, W) float."""
    calls = []
    real = fr.over

    def spy(y0, y1, x0, x1, rgb, al):
        calls.append((y0, y1, x0, x1, al[..., 0].copy()))
        real(y0, y1, x0, x1, rgb, al)
    fr.c = np.zeros((fr.H, fr.W, 3), np.float32)
    fr.a = np.zeros((fr.H, fr.W), np.float32)
    fr.over = spy
    try:
        getattr(fr, method)(*args)
    finally:
        del fr.over
    cov = np.zeros((fr.H, fr.W), np.float32)
    for y0, y1, x0, x1, al in (calls[-1:] if last else calls):
        np.maximum(cov[y0:y1, x0:x1], al, out=cov[y0:y1, x0:x1])
    return cov


def stones(fr):
    """The outlines of the stones the hill draws, in drawing order, each a list of frame points."""
    out = []
    real = fr.rock

    class Outline:
        def __init__(self, layer):
            self.layer, self.first = layer, None

        def poly(self, pts, *a, **k):
            if self.first is None:
                self.first = [tuple(map(float, p)) for p in pts]
            return self.layer.poly(pts, *a, **k)

        def __getattr__(self, name):
            return getattr(self.layer, name)

    def spy(A, N, *a, **k):
        o = Outline(A)
        real(o, N, *a, **k)
        out.append(o.first)
    fr.c = np.zeros((fr.H, fr.W, 3), np.float32)
    fr.a = np.zeros((fr.H, fr.W), np.float32)
    fr.shade, fr.ao = fr.shadow_masks()
    fr.rock = spy
    try:
        fr.hill()
    finally:
        del fr.rock
    return out


def rect(mask, x0, y0, x1, y1):
    """Mark frame pixels x0..x1, y0..y1 (inclusive, rounded outward) in a crop-sized mask."""
    a, b = max(0, math.floor(x0) - CROP["x"]), min(CROP["w"] - 1, math.ceil(x1) - CROP["x"])
    c, d = max(0, math.floor(y0) - CROP["y"]), min(CROP["h"] - 1, math.ceil(y1) - CROP["y"])
    if a <= b and c <= d:
        mask[c:d + 1, a:b + 1] = True


def keepout(fr, deck, top, bot):
    """The keep-out mask (crop-sized bool) and the deck mask (crop-sized bool)."""
    s, W, H = fr.s, fr.W, fr.H
    deck_mask = np.zeros((CROP["h"], CROP["w"]), bool)
    xs, ys = [v[0] for v in deck], [v[1] for v in deck]
    for y in range(min(ys), max(ys) + 1):
        for x in range(min(xs), max(xs) + 1):
            if point_in_polygon(x, y, deck):
                deck_mask[y - CROP["y"], x - CROP["x"]] = True
    keep = np.zeros_like(deck_mask)
    keep[:, :REGION["x0"] - CROP["x"]] = True
    # the pier: posts, rails, stringer and set stones (its deck is open ground), then what stands on the deck
    pier = crop(drawn(fr, "pier", last=True)) > 0.05
    keep |= ndi.binary_dilation(pier, iterations=1) & ~deck_mask
    deck_h = PIER3["deck"]
    things = [(u, v, deck_h, deck_h + h, 0.0075) for u, v, h in ((0.985, 0.92, 0.022), (0.62, 0.92, 0.018),
                                                                    (0.25, 0.92, 0.018))]
    things.append((1.0, 0.06, deck_h, deck_h + 0.105, 0.007))
    for u, v, y0, y1, r in things:
        X, _, Z = fr.pier_pt(u, v, 0)
        cx, ya = fr.pproj(float(X), y0, float(Z))
        _, yb = fr.pproj(float(X), y1, float(Z))
        half = r / math.hypot(float(X), float(Z)) * W / math.radians(AZ_SPAN)
        rect(keep, cx - half - 1, yb - 1, cx + half + 1, ya + 1)
    lx, ly = fr.pier_lantern()
    rect(keep, lx - 7 * s, ly - 11 * s, lx + 7 * s, ly + 6 * s)
    # where the gulls perch on the deck (life.pier_gulls): a gull and its standing room
    for u in (0.35, 0.55, 0.72, 0.88):
        gx, gy = fr.pproj(*fr.pier_pt(u, 0.55, deck_h))
        gs = 7 * s * (1 - 0.3 * u)
        rect(keep, float(gx) - 1.8 * gs - 1, float(gy) - 2.1 * gs - 1, float(gx) + 1.8 * gs + 1, float(gy) + 1)
    # the moored boat, its mast and its line to the pier
    boat = crop(drawn(fr, "moored_boat")) > 0.02
    keep |= ndi.binary_dilation(boat, iterations=2)
    # big stones that stand on the dry shingle: anything behind one would be drawn in front of it
    for pts in stones(fr):
        if pts is None:
            continue
        sx = [p[0] for p in pts]
        sy = [p[1] for p in pts]
        if max(sy) - min(sy) < STONE_H or max(sx) < CROP["x"] or min(sx) >= CROP["x"] + CROP["w"] or max(sy) < CROP["y"] or min(sy) >= CROP["y"] + CROP["h"]:
            continue
        on_dry = False
        for x in range(max(REGION["x0"], math.floor(min(sx))), min(REGION["x1"], math.ceil(max(sx))) + 1):
            t = top[x - REGION["x0"]]
            if t != -1 and max(sy) >= t:
                on_dry = True
                break
        if not on_dry:
            continue
        im = Image.new("L", (CROP["w"], CROP["h"]), 0)
        ImageDraw.Draw(im).polygon([(x - CROP["x"], y - CROP["y"]) for x, y in pts], fill=255)
        keep |= ndi.binary_dilation(np.asarray(im) > 0, iterations=1)
    return keep, deck_mask


# -------------------------------------------------------------------- build --
def build(out, rid="r1", log=print):
    os.makedirs(out, exist_ok=True)
    days = {}

    def day_for(kind):
        if kind not in days:
            days[kind] = Day(DATE, weather=kind, reference=True)
        return days[kind]

    vig_cells, vig = vignette_cells()
    files = {}
    conds, crops = [], {}
    for name, hhmm, kind in CONDITIONS:
        day, m = day_for(kind), minute(hhmm)
        img = render(day, m)
        if name == "noon":
            files["context.jpg"] = img
        c = np.ascontiguousarray(crop(img))
        crops[name] = c
        fr = lp.Frame(day, m, SCALE)
        light = fr.light(normalize(UPRIGHT))
        alpha, F = veil(fr)
        lut = tone_lut(fr.night)
        conds.append(dict(name=name, m=m, fr=fr, light=[rint(256 * v) for v in light], lut=lut, alpha=alpha, F=F))
        log("%s %s: sun %.1f deg, light x256 %s" % (name, hhmm, fr.sun_alt, conds[-1]["light"]))
    gday, gm = day_for("clear"), minute(CONDITIONS[0][1])
    fr = lp.Frame(gday, gm, SCALE)
    top, bot = dry_band()
    deck = deck_polygon(fr)
    keep, deck_mask = keepout(fr, deck, top, bot)
    # where a contact shadow can fall: the dry band and two rows under it, and the deck
    fall = np.zeros_like(keep)
    for i, (t, b) in enumerate(zip(top, bot)):
        if t != -1:
            x = REGION["x0"] + i - CROP["x"]
            fall[t - CROP["y"]:min(CROP["h"], b + 3 - CROP["y"]), x] = True
    fall = (fall | deck_mask) & ~keep
    cond_json = []
    for k in conds:
        has_veil = bool(k["alpha"].max() > 0)
        s_alpha = shadow_alpha(crops[k["name"]], k["lut"], vig, k["alpha"], k["F"], fall)
        cond_json.append({
            "name": k["name"], "light": k["light"], "lut": [list(map(int, t)) for t in k["lut"]],
            "veil": {"rgb": [rint(v) for v in k["F"]] if has_veil else [0, 0, 0],
                     "alpha": [rint(256 * a) for a in k["alpha"]] if has_veil else [0] * CROP["h"]},
            "shadow": {"rgb": [0, 0, 0], "alpha": s_alpha}})
        log("%s: shadow alpha %d/256%s" % (k["name"], s_alpha, ", fog veil %s" % cond_json[-1]["veil"]["rgb"] if has_veil else ""))
    surfaces = {"shore_surfaces": 1, "reference": rid, "frame": {"w": fr.W, "h": fr.H}, "crop": CROP,
                "region": REGION, "dry": {"x0": REGION["x0"], "top": top, "bottom": bot}, "deck": deck,
                "max_h": {"y0": REGION["y0"], "h": max_heights()}}
    palette = {"shore_palette": 1, "reference": rid, "d": D,
               "entries": [{"name": n, "rgb": list(c)} for n, c in PALETTE],
               "plaque": {k: list(v) for k, v in PLAQUE.items()}}
    conditions = {"shore_conditions": 1, "reference": rid, "cell": CELL, "vignette": vig_cells, "conditions": cond_json}
    blobs = {"surfaces.json": canonical(surfaces), "palette.json": canonical(palette),
             "conditions.json": canonical(conditions),
             "keepout.png": write_png(CROP["w"], CROP["h"], (keep.astype(np.uint8) * 255).tobytes(), 0)}
    for name, c in crops.items():
        blobs[name + ".png"] = write_png(CROP["w"], CROP["h"], c.tobytes(), 2)
    for name, data in sorted(blobs.items()):
        tmp = os.path.join(out, name + ".tmp")
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, os.path.join(out, name))
    ctx = Image.fromarray(files["context.jpg"]).resize((1440, 900), Image.LANCZOS)
    ctx.save(os.path.join(out, "context.jpg"), quality=85)
    ref = load_reference(out)           # the kit must accept what was written
    log("reference %s written to %s: digest %s" % (ref.id, out, ref.digest))
    return ref


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out")
    ap.add_argument("--reference", default="r1", help="the reference id (r1, r2, ...)")
    a = ap.parse_args()
    out = os.path.realpath(a.out)
    inside = out == ROOT or out.startswith(ROOT + os.sep)
    if inside and not out.startswith(os.path.join(ROOT, "out") + os.sep):
        sys.exit("refusing to write a reference set inside the repository (use a folder outside it, or out/)")
    build(out, a.reference)


if __name__ == "__main__":
    main()
