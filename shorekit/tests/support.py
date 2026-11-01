"""Test support: a synthetic reference set, made with integers only so it is the same everywhere.

Its geometry follows renderers/procedural (2880x1800 frame): the hill edge is core.HILL's
breakpoints, the beach band rises from nothing near x=1640 to about 83 px at the right edge, the
pier deck runs (2016,1544)-(2471,1420), the moored boat sits at core.MOORED, and the albedos are
the renderer's own constants. None of it is real shore data.

    python3 -m shorekit.tests.support OUTDIR      # write the set for a look (from the repo root)
"""
import atexit
import hashlib
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from shorekit import KIT_VERSION  # noqa: E402
from shorekit.ledger import ledger_bytes  # noqa: E402
from shorekit.png import write_png  # noqa: E402
from shorekit.rules import isqrt  # noqa: E402
from shorekit.strictjson import canonical  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")
W, H = 2880, 1800
CX, CY, CW, CH = 1600, 1150, 1280, 640
RX0, RY0, RX1, RY1 = 1640, 1150, 2879, 1789

# core.HILL in thousandths of the frame
HILL = [(-10, 600), (100, 602), (200, 607), (300, 617), (380, 630), (460, 648), (530, 668), (575, 690),
        (610, 725), (640, 775), (670, 815), (710, 845), (770, 868), (840, 884), (920, 896), (1020, 905)]
HILL_PX = [(x * 288 // 100, y * 9 // 5) for x, y in HILL]
BAND = [(1600, 0), (1650, 6), (1700, 26), (1728, 44), (2000, 45), (2304, 47), (2600, 64), (2880, 83)]
DECK = [(2016, 1544), (2471, 1420), (2465, 1408), (2008, 1532)]

PALETTE = [
    ("rock", (134, 130, 122)), ("stone", (122, 118, 110)), ("shingle", (124, 116, 102)),
    ("wrack", (58, 54, 40)), ("weed", (48, 52, 26)), ("lichen", (196, 132, 46)),
    ("timber", (96, 80, 64)), ("old-timber", (118, 112, 102)), ("bench-wood", (128, 86, 54)),
    ("brass", (196, 156, 70)), ("iron", (34, 34, 38)), ("sail", (240, 236, 222)),
    ("hull", (228, 226, 220)), ("hull-stripe", (40, 52, 84)), ("glass", (170, 180, 190)),
    ("life-ring", (210, 60, 48)), ("path", (150, 128, 98)), ("grass", (58, 80, 40)),
    ("grass-lush", (52, 94, 36)), ("grass-dry", (156, 142, 92)), ("grass-winter", (66, 82, 45)),
]
D = 40
GLOW = [("lamplight", (236, 186, 104)), ("lit-window", (220, 150, 80))]
PLAQUE = {"wood": [142, 135, 120], "grain": [128, 121, 108], "ink": [102, 95, 84]}

# class codes for the synthetic crops
SEA, WET, DRY, GRASS, DECKC, SCENERY = 0, 1, 2, 3, 4, 5
COLOURS = {
    "noon": [(40, 92, 120), (98, 96, 86), (150, 140, 122), (70, 96, 48), (110, 92, 72), (60, 50, 42)],
    "golden": [(70, 80, 96), (120, 96, 70), (176, 140, 100), (90, 92, 44), (130, 98, 66), (70, 52, 40)],
    "night": [(12, 20, 34), (26, 28, 34), (40, 42, 50), (20, 30, 24), (30, 28, 30), (14, 14, 18)],
    "fog": [(150, 158, 166), (140, 140, 138), (160, 158, 152), (120, 128, 112), (140, 134, 126), (110, 110, 112)],
}
CONDITIONS = ("noon", "golden", "night", "fog")


def interp(pts, x):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) // (x1 - x0)
    return pts[-1][1]


def low_water(x):
    return interp(HILL_PX, x)


def band(x):
    return interp(BAND, x)


def dry(x):
    b = band(x)
    if b < 8:
        return None
    lo = low_water(x)
    top, bot = lo + (b + 1) // 2, min(lo + b - 1, RY1)
    return (top, bot) if RY0 <= top <= bot else None


def max_h(y):
    num = 224 * 720 + 832 * max(0, min(720, y - 1080))
    return (2 * num + 7200) // 14400


def min_h(y):
    """Look B's floor. Kept low (a 24th of max_h, 2-4 px) so the old scale-1 fixtures still stand;
    test_rules holds the rule itself."""
    return max(1, max_h(y) // 24)


def in_poly(x, y, poly):
    from shorekit.reference import point_in_polygon
    return point_in_polygon(x, y, poly)


def scenery():
    """Keep-out shapes: (kind, params). Pier side and piles, bollards, the end post and lantern,
    gull perches, the moored boat and its line, two big rocks, and a heron's fishing lane."""
    shapes = [("poly", [(2016, 1544), (2471, 1420), (2471, 1428), (2016, 1553)])]
    for j in range(9):
        x = 2016 + j * 455 // 8
        y = 1544 - j * 124 // 8
        shapes.append(("rect", (x - 3, y, x + 3, y + 40 - 2 * j)))
    for u in (985, 620, 250):
        x = 2008 + u * 457 // 1000
        y = 1532 - u * 124 // 1000
        shapes.append(("rect", (x - 3, y - 12, x + 3, y)))
    shapes.append(("rect", (2463, 1330, 2471, 1420)))
    for u in (350, 550, 720, 880):
        x = 2012 + u * 456 // 1000
        y = 1538 - u * 124 // 1000
        shapes.append(("rect", (x - 8, y - 22, x + 8, y - 4)))
    shapes += [("rect", (2478, 1405, 2614, 1444)), ("rect", (2543, 1262, 2549, 1411)),
               ("rect", (2502, 1396, 2550, 1404)), ("rect", (2471, 1412, 2490, 1420))]
    shapes += [("ellipse", (1900, 1470, 18, 11)), ("ellipse", (2790, 1688, 14, 9))]
    shapes.append(("rect", (2700, 1590, 2729, 1700)))
    return shapes


def _fill(mask, shape, value):
    kind, p = shape
    if kind == "rect":
        x0, y0, x1, y1 = p
        for y in range(max(y0, CY), min(y1, CY + CH - 1) + 1):
            a, b = max(x0, CX), min(x1, CX + CW - 1)
            if a <= b:
                mask[(y - CY) * CW + a - CX:(y - CY) * CW + b - CX + 1] = bytes([value]) * (b - a + 1)
    elif kind == "ellipse":
        cx, cy, rx, ry = p
        for y in range(cy - ry, cy + ry + 1):
            for x in range(cx - rx, cx + rx + 1):
                if ((x - cx) * ry) ** 2 + ((y - cy) * rx) ** 2 <= (rx * ry) ** 2:
                    mask[(y - CY) * CW + x - CX] = value
    else:
        xs = [v[0] for v in p]
        ys = [v[1] for v in p]
        for y in range(min(ys), max(ys) + 1):
            for x in range(min(xs), max(xs) + 1):
                if in_poly(x, y, p):
                    mask[(y - CY) * CW + x - CX] = value


def make_reference(path, rid="r1"):
    """Write a complete synthetic reference set into `path` (created). Returns path."""
    os.makedirs(path, exist_ok=True)
    nx = RX1 - RX0 + 1
    tops, bots = [], []
    for x in range(RX0, RX1 + 1):
        d = dry(x)
        tops.append(d[0] if d else -1)
        bots.append(d[1] if d else -1)
    surfaces = {"shore_surfaces": 1, "reference": rid, "frame": {"w": W, "h": H},
                "crop": {"x": CX, "y": CY, "w": CW, "h": CH},
                "region": {"x0": RX0, "y0": RY0, "x1": RX1, "y1": RY1},
                "dry": {"x0": RX0, "top": tops, "bottom": bots},
                "deck": [list(v) for v in DECK],
                "max_h": {"y0": RY0, "h": [max_h(y) for y in range(RY0, RY1 + 1)]},
                "min_h": {"y0": RY0, "h": [min_h(y) for y in range(RY0, RY1 + 1)]}}
    assert len(tops) == nx
    palette = {"shore_palette": 1, "reference": rid, "d": D,
               "entries": [{"name": n, "rgb": list(c)} for n, c in PALETTE],
               "glow": [{"name": n, "rgb": list(c)} for n, c in GLOW], "plaque": PLAQUE}

    def lut(kind, ch):
        out = []
        for i in range(512):
            v = i
            if kind == "night":
                v = (isqrt(i * 255) * 28 + i * 72) // 100
            if v > 200:
                k = v - 200
                v = 200 + 55 * k // (k + 55)
            if kind == "night":
                v = v * (240, 250, 266)[ch] >> 8
            out.append(min(255, v))
        return out

    vig = []
    for j in range(CH // 16):
        row = []
        for i in range(CW // 16):
            fx, fy = CX + 16 * i + 8, CY + 16 * j + 8
            an, ad = (2 * fx - W) ** 2 * 121, 400 * W * W
            bn, bd = (100 * fy - 52 * H) ** 2 * 169, 1000000 * H * H
            row.append(256 - 9728 * (an * bd + bn * ad) // (100 * ad * bd))
        vig.append(row)
    lights = {"noon": [300, 296, 288], "golden": [330, 250, 180], "night": [60, 66, 96], "fog": [210, 212, 216]}
    # look B: the light on the top, east and west faces, and the lamps (x256)
    faces = {"noon": ([360, 354, 340], [250, 252, 256], [250, 252, 256]),
             "golden": ([300, 240, 190], [200, 180, 170], [420, 300, 200]),
             "night": ([70, 76, 108], [56, 62, 92], [56, 62, 92]),
             "fog": ([230, 232, 236], [200, 202, 206], [200, 202, 206])}
    lamps = {"noon": 0, "golden": 0, "night": 256, "fog": 0}
    shadows = {"noon": ([22, 24, 30], 110), "golden": ([40, 26, 20], 100), "night": ([6, 8, 14], 50),
               "fog": ([90, 94, 100], 40)}
    conds = []
    for name in CONDITIONS:
        alpha = [120 + (CH - r) * 80 // CH for r in range(CH)] if name == "fog" else [0] * CH
        veil = [172, 178, 186] if name == "fog" else [0, 0, 0]
        top, east, west = faces[name]
        conds.append({"name": name, "light": lights[name], "top": top, "east": east, "west": west,
                      "lamps": lamps[name], "lut": [lut(name, c) for c in range(3)],
                      "veil": {"rgb": veil, "alpha": alpha},
                      "shadow": {"rgb": shadows[name][0], "alpha": shadows[name][1]}})
    conditions = {"shore_conditions": 1, "reference": rid, "cell": 16, "vignette": vig, "conditions": conds}
    for name, obj in (("surfaces.json", surfaces), ("palette.json", palette), ("conditions.json", conditions)):
        with open(os.path.join(path, name), "wb") as f:
            f.write(canonical(obj) + b"\n")

    keep = bytearray(CW * CH)
    _fill(keep, ("rect", (CX, CY, RX0 - 1, CY + CH - 1)), 255)
    for s in scenery():
        _fill(keep, s, 255)
    with open(os.path.join(path, "keepout.png"), "wb") as f:
        f.write(write_png(CW, CH, bytes(keep), 0))

    cls = bytearray(CW * CH)
    for x in range(CX, CX + CW):
        xi = x - CX
        lo = low_water(x)
        d = dry(x)
        b = band(x)
        top = d[0] if d else lo + (b + 1) // 2
        grass = lo + b
        for a, z, k in ((CY, lo - 1, SEA), (lo, top - 1, WET), (top, grass - 1, DRY), (grass, CY + CH - 1, GRASS)):
            a, z = max(a, CY), min(z, CY + CH - 1)
            if a <= z:
                cls[(a - CY) * CW + xi:(z - CY) * CW + xi + 1:CW] = bytes([k]) * (z - a + 1)
    _fill(cls, ("poly", DECK), DECKC)
    for s in scenery():
        _fill(cls, s, SCENERY)
    for name in CONDITIONS:
        planes = [cls.translate(bytes(COLOURS[name][k][c] if k < 6 else 0 for k in range(256))) for c in range(3)]
        rgb = bytearray(3 * CW * CH)
        for c in range(3):
            rgb[c::3] = planes[c]
        with open(os.path.join(path, name + ".png"), "wb") as f:
            f.write(write_png(CW, CH, bytes(rgb), 2))
    return path


_CACHE = {}


def reference_dir():
    """A synthetic r1, made once per test process."""
    if "r1" not in _CACHE:
        d = tempfile.mkdtemp(prefix="shorekit-ref-")
        atexit.register(shutil.rmtree, d, True)
        _CACHE["r1"] = make_reference(os.path.join(d, "r1"))
    return _CACHE["r1"]


def reference():
    from shorekit.reference import load_reference
    if "ref" not in _CACHE:
        _CACHE["ref"] = load_reference(reference_dir())
    return _CACHE["ref"]


def fixture(name):
    with open(os.path.join(FIXTURES, "objects", name + ".json"), "rb") as f:
        return f.read()


def fixture_obj(name):
    return json.loads(fixture(name).decode("ascii"))


def manifest_bytes(obj):
    return canonical(obj)


def make_object(oid, maker, rows, palette, on, x, y, anchor=None, scale=1, label=None, side="right", rid="r1"):
    obj = {"shore": 1, "id": oid, "maker": maker, "kit": KIT_VERSION, "reference": rid,
           "palette": {k: list(v) for k, v in palette.items()}, "rows": list(rows), "scale": scale,
           "anchor": list(anchor if anchor else ((len(rows[0]) - 1) // 2, len(rows) - 1)),
           "place": {"on": on, "x": x, "y": y}}
    if label:
        obj["label"] = {"text": label, "side": side}
    return obj


def block(w, h, key="a"):
    return [key * w for _ in range(h)]


STONE = {"a": (34, 34, 38)}       # look C: a tarred stone, so it stands out from the shingle (rule 7)
TIMBER = {"a": (96, 80, 64), "b": (118, 112, 102)}


def new_shore(tmp, rid_dir=None):
    """A shore directory with a reference set, an empty ledger and no objects."""
    root = os.path.join(tmp, "shore")
    os.makedirs(os.path.join(root, "objects"), exist_ok=True)
    os.makedirs(os.path.join(root, "reference"), exist_ok=True)
    shutil.copytree(rid_dir or reference_dir(), os.path.join(root, "reference", "r1"))
    with open(os.path.join(root, "ledger.json"), "wb") as f:
        f.write(ledger_bytes([]))
    return root


def crowd(shore, n, day="2026-11-02", at="2026-11-02T04:30:00Z", world="world-1"):
    """Accept n small stones along the dry band onto `shore` (a Shore), one maker each, all at `at`, the
    way a carrier pass would. Returns their objects in seq order."""
    from shorekit.manifest import manifest_from_obj
    ref = shore.ref
    objs = []
    x = 1700
    while len(objs) < n:
        d = ref.dry(x)
        if d:
            obj = make_object("%s-s%02d" % (day, len(objs)), "maker-%02d" % len(objs), block(4, 4), STONE, "shingle",
                              x, (d[0] + d[1]) >> 1)
            m = manifest_from_obj(obj)
            if not shore.judge(m, day)[0]:
                shore.accept(m, at, at, world, "0" * 40)
                objs.append(obj)
        x += 9
    return objs


def write_queue(qdir, at, cands, lands=None):
    """cands: [(world, obj)]. Writes qdir/<world>/<id>.json and qdir/queue.json."""
    os.makedirs(qdir, exist_ok=True)
    entries = []
    for n, (world, obj) in enumerate(cands):
        os.makedirs(os.path.join(qdir, world), exist_ok=True)
        with open(os.path.join(qdir, world, obj["id"] + ".json"), "wb") as f:
            f.write(canonical(obj))
        entries.append({"world": world, "id": obj["id"], "commit": hashlib.sha1(obj["id"].encode()).hexdigest()})
    q = {"shore_queue": 1, "at": at, "lands": lands or at, "candidates": entries}
    p = os.path.join(qdir, "queue.json")
    with open(p, "wb") as f:
        f.write(canonical(q))
    return p


if __name__ == "__main__":
    print(make_reference(os.path.join(sys.argv[1], "r1") if len(sys.argv) > 1 else tempfile.mkdtemp()))
