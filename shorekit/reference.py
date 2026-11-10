"""The reference set a verdict is reached against: integer geometry, palette, grading, crops.

A reference set is a directory (reference/<id>/) written by the Mac's reference builder. Its
schema is in SCHEMA.md; this module loads it and refuses anything out of shape.
"""
import hashlib
import os
import re

from . import CAST_MAX_DX, CAST_MAX_DY
from .errors import ShoreError
from .manifest import REF_RE
from .png import REF_H, REF_W, read_reference_png
from .strictjson import is_int, is_str, loads

ERR = "E_REFDATA"
CELL = 16
NAME_RE = re.compile(r"[a-z][a-z0-9-]{0,31}", re.ASCII)
COND_RE = re.compile(r"[a-z]{1,16}", re.ASCII)
JSON_FILES = ("conditions.json", "palette.json", "surfaces.json")
LIMITS = {"surfaces.json": 262144, "palette.json": 65536, "conditions.json": 524288}


def _fail(what, text):
    raise ShoreError(ERR, "%s: %s" % (what, text))


def _keys(obj, keys, what):
    if type(obj) is not dict or sorted(obj) != sorted(keys):
        _fail(what, "keys must be exactly %s" % ", ".join(sorted(keys)))


def _is_one(v):
    return is_int(v) and v == 1


def _int(v, lo, hi, what):
    if not is_int(v) or not lo <= v <= hi:
        _fail(what, "must be an integer %d-%d" % (lo, hi))
    return v


def _ints(v, n, lo, hi, what):
    if type(v) is not list or len(v) != n:
        _fail(what, "must be a list of %d integers" % n)
    for x in v:
        if not is_int(x) or not lo <= x <= hi:
            _fail(what, "values must be integers %d-%d" % (lo, hi))
    return list(v)


def _rgb(v, what):
    return tuple(_ints(v, 3, 0, 255, what))


def point_in_polygon(x, y, poly):
    """True if the integer point (x, y) is inside the polygon or on its boundary. Integers only."""
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1) == 0
                and min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2)):
            return True
        if (y1 > y) != (y2 > y):
            lhs = (x - x1) * (y2 - y1)
            rhs = (y - y1) * (x2 - x1)
            if (y2 > y1 and lhs < rhs) or (y2 < y1 and lhs > rhs):
                inside = not inside
    return inside


class Condition:
    __slots__ = ("name", "light", "lights", "lamps", "lut", "veil_rgb", "veil_alpha", "shadow_rgb", "shadow_alpha",
                 "cast_dx", "cast_dy", "cast_alpha")


def _signed(v, lim, what):
    if not is_int(v) or not -lim <= v <= lim:
        _fail(what, "must be an integer from -%d to %d" % (lim, lim))
    return v


class Reference:
    """Loaded reference data. Frame coordinates throughout; crop-local index = (y-cy)*cw + (x-cx)."""

    def __init__(self, path):
        self.path = path
        blobs = {}
        for name in JSON_FILES:
            blobs[name] = self._read(name, LIMITS[name])
        surf, pal, cond = (self._json(n, blobs) for n in ("surfaces.json", "palette.json", "conditions.json"))
        self._surfaces(surf)
        self._palette(pal)
        self._conditions(cond)
        ids = {surf["reference"], pal["reference"], cond["reference"]}
        if len(ids) != 1:
            _fail("reference", "surfaces.json, palette.json and conditions.json name different references")
        self.id = surf["reference"]
        blobs["keepout.png"] = self._read("keepout.png", 2 * 1024 * 1024)
        ko = read_reference_png(blobs["keepout.png"], 0, "keepout.png")
        self.keepout = ko                       # 255 = keep-out, per crop pixel
        for c in self.conditions:
            blobs[c.name + ".png"] = self._read(c.name + ".png", 8 * 1024 * 1024)
        self._crop_blobs = {c.name: blobs[c.name + ".png"] for c in self.conditions}
        self._crops = {}
        h = hashlib.sha256(b"shorekit-reference-1\n")
        for name in sorted(blobs):
            h.update(("%s %s\n" % (name, hashlib.sha256(blobs[name]).hexdigest())).encode("ascii"))
        self.digest = h.hexdigest()
        self._deck_mask()

    def _json(self, name, blobs):
        try:
            return loads(blobs[name], LIMITS[name], 5, name)
        except ShoreError as e:
            raise ShoreError(ERR, e.text)

    def _read(self, name, limit):
        p = os.path.join(self.path, name)
        try:
            size = os.path.getsize(p)
            if size > limit:
                _fail(name, "is %d bytes, max %d" % (size, limit))
            with open(p, "rb") as f:
                return f.read(limit + 1)
        except OSError:
            raise ShoreError(ERR, "%s: cannot read %s" % (name, p))

    # ---------------------------------------------------------------- surfaces --
    def _surfaces(self, s):
        what = "surfaces.json"
        _keys(s, ("shore_surfaces", "reference", "frame", "crop", "region", "dry", "deck", "max_h", "min_h"), what)
        if not _is_one(s["shore_surfaces"]) or not is_str(s["reference"]) or not REF_RE.fullmatch(s["reference"]):
            _fail(what, "shore_surfaces must be 1 and reference like r1")
        _keys(s["frame"], ("w", "h"), what + " frame")
        self.frame_w = _int(s["frame"]["w"], 1, 20000, what + " frame.w")
        self.frame_h = _int(s["frame"]["h"], 1, 20000, what + " frame.h")
        _keys(s["crop"], ("x", "y", "w", "h"), what + " crop")
        c = s["crop"]
        self.cx = _int(c["x"], 0, self.frame_w, what + " crop.x")
        self.cy = _int(c["y"], 0, self.frame_h, what + " crop.y")
        if (c["w"], c["h"]) != (REF_W, REF_H) or self.cx + REF_W > self.frame_w or self.cy + REF_H > self.frame_h:
            _fail(what, "crop must be %dx%d and inside the frame" % (REF_W, REF_H))
        self.cw, self.ch = REF_W, REF_H
        _keys(s["region"], ("x0", "y0", "x1", "y1"), what + " region")
        r = s["region"]
        self.rx0 = _int(r["x0"], self.cx, self.cx + REF_W - 1, what + " region.x0")
        self.ry0 = _int(r["y0"], self.cy, self.cy + REF_H - 1, what + " region.y0")
        self.rx1 = _int(r["x1"], self.rx0, self.cx + REF_W - 1, what + " region.x1")
        self.ry1 = _int(r["y1"], self.ry0, self.cy + REF_H - 1, what + " region.y1")
        nx = self.rx1 - self.rx0 + 1
        ny = self.ry1 - self.ry0 + 1
        d = s["dry"]
        _keys(d, ("x0", "top", "bottom"), what + " dry")
        if not is_int(d["x0"]) or d["x0"] != self.rx0:
            _fail(what, "dry.x0 must equal region.x0")
        top = _ints(d["top"], nx, -1, self.ry1, what + " dry.top")
        bot = _ints(d["bottom"], nx, -1, self.ry1, what + " dry.bottom")
        for i in range(nx):
            if (top[i] == -1) != (bot[i] == -1) or (top[i] != -1 and not self.ry0 <= top[i] <= bot[i]):
                _fail(what, "dry band at x=%d must be -1,-1 or region.y0 <= top <= bottom" % (self.rx0 + i))
        self.dry_top, self.dry_bottom = top, bot
        deck = s["deck"]
        if type(deck) is not list or not 3 <= len(deck) <= 64:
            _fail(what, "deck must be a polygon of 3-64 [x, y] vertices")
        self.deck = []
        for v in deck:
            x, y = _ints(v, 2, 0, 20000, what + " deck vertex")
            if not (self.rx0 <= x <= self.rx1 and self.ry0 <= y <= self.ry1):
                _fail(what, "deck vertex (%d,%d) is outside the region" % (x, y))
            self.deck.append((x, y))
        m = s["max_h"]
        _keys(m, ("y0", "h"), what + " max_h")
        if not is_int(m["y0"]) or m["y0"] != self.ry0:
            _fail(what, "max_h.y0 must equal region.y0")
        self.max_h = _ints(m["h"], ny, 1, 1000, what + " max_h.h")
        m = s["min_h"]
        _keys(m, ("y0", "h"), what + " min_h")
        if not is_int(m["y0"]) or m["y0"] != self.ry0:
            _fail(what, "min_h.y0 must equal region.y0")
        self.min_h = _ints(m["h"], ny, 1, 1000, what + " min_h.h")
        if any(lo > hi for lo, hi in zip(self.min_h, self.max_h)):
            _fail(what, "min_h must not exceed max_h on any row")

    def _deck_mask(self):
        mask = bytearray(self.cw * self.ch)
        xs = [v[0] for v in self.deck]
        ys = [v[1] for v in self.deck]
        for y in range(min(ys), max(ys) + 1):
            base = (y - self.cy) * self.cw - self.cx
            for x in range(min(xs), max(xs) + 1):
                if point_in_polygon(x, y, self.deck):
                    mask[base + x] = 1
        self.deck_mask = mask

    # ----------------------------------------------------------------- palette --
    def _palette(self, p):
        what = "palette.json"
        _keys(p, ("shore_palette", "reference", "d", "entries", "glow", "plaque"), what)
        if not _is_one(p["shore_palette"]) or not is_str(p["reference"]) or not REF_RE.fullmatch(p["reference"]):
            _fail(what, "shore_palette must be 1 and reference like r1")
        self.d = _int(p["d"], 1, 765, what + " d")
        ents = p["entries"]
        if type(ents) is not list or not 1 <= len(ents) <= 256:
            _fail(what, "entries must be a list of 1-256 colours")
        self.palette = []
        names = set()
        for e in ents:
            _keys(e, ("name", "rgb"), what + " entry")
            if not is_str(e["name"]) or not NAME_RE.fullmatch(e["name"]) or e["name"] in names:
                _fail(what, "entry names must be unique and match [a-z][a-z0-9-]{0,31}")
            names.add(e["name"])
            self.palette.append((e["name"], _rgb(e["rgb"], what + " " + e["name"])))
        lights = p["glow"]
        if type(lights) is not list or len(lights) > 16:
            _fail(what, "glow must be a list of 0-16 light colours")
        self.glow = []
        for e in lights:
            _keys(e, ("name", "rgb"), what + " glow entry")
            if not is_str(e["name"]) or not NAME_RE.fullmatch(e["name"]) or e["name"] in names:
                _fail(what, "entry names must be unique and match [a-z][a-z0-9-]{0,31}")
            names.add(e["name"])
            self.glow.append((e["name"], _rgb(e["rgb"], what + " " + e["name"])))
        _keys(p["plaque"], ("wood", "grain", "ink"), what + " plaque")
        self.plaque = {k: _rgb(p["plaque"][k], what + " plaque." + k) for k in ("wood", "grain", "ink")}

    # -------------------------------------------------------------- conditions --
    def _conditions(self, c):
        what = "conditions.json"
        _keys(c, ("shore_conditions", "reference", "cell", "vignette", "conditions"), what)
        ver = c["shore_conditions"]
        if not is_int(ver) or ver not in (1, 2) or not is_str(c["reference"]) or not REF_RE.fullmatch(c["reference"]):
            _fail(what, "shore_conditions must be 1 or 2 and reference like r1")
        # 2 (kit 1.3.0): every condition also says which way its cast shadows fall and how dark they are;
        # a set written as 1 has none, and is drawn exactly as kit 1.2.0 drew it
        self.conditions_version = ver
        fields = ("name", "light", "top", "east", "west", "lamps", "lut", "veil", "shadow") + (("cast",) if ver == 2 else ())
        if not is_int(c["cell"]) or c["cell"] != CELL:
            _fail(what, "cell must be %d" % CELL)
        vig = c["vignette"]
        rows, cols = REF_H // CELL, REF_W // CELL
        if type(vig) is not list or len(vig) != rows:
            _fail(what, "vignette must be %d rows of %d" % (rows, cols))
        self.vignette = [_ints(r, cols, 0, 256, what + " vignette") for r in vig]
        conds = c["conditions"]
        if type(conds) is not list or len(conds) != 4:
            _fail(what, "conditions must list exactly 4 conditions")
        self.conditions = []
        seen = set()
        for k in conds:
            _keys(k, fields, what + " condition")
            if not is_str(k["name"]) or not COND_RE.fullmatch(k["name"]) or k["name"] in seen:
                _fail(what, "condition names must be unique and match [a-z]{1,16}")
            seen.add(k["name"])
            q = Condition()
            q.name = k["name"]
            w = what + " " + q.name
            q.light = tuple(_ints(k["light"], 3, 0, 4096, w + ".light"))
            # look B: the light on each face (geometry.FACE_*: front, top, east, west), and how far the
            # lamps are lit (x256): a glow key's cells emit then
            q.lights = (q.light,) + tuple(tuple(_ints(k[f], 3, 0, 4096, w + "." + f)) for f in ("top", "east", "west"))
            q.lamps = _int(k["lamps"], 0, 256, w + ".lamps")
            lut = k["lut"]
            if type(lut) is not list or len(lut) != 3:
                _fail(w, "lut must be 3 lists of 512")
            q.lut = tuple(tuple(_ints(t, 512, 0, 255, w + ".lut")) for t in lut)
            _keys(k["veil"], ("rgb", "alpha"), w + ".veil")
            q.veil_rgb = tuple(_ints(k["veil"]["rgb"], 3, 0, 511, w + ".veil.rgb"))   # linear, like the lut's index
            q.veil_alpha = tuple(_ints(k["veil"]["alpha"], REF_H, 0, 256, w + ".veil.alpha"))
            _keys(k["shadow"], ("rgb", "alpha"), w + ".shadow")
            q.shadow_rgb = _rgb(k["shadow"]["rgb"], w + ".shadow.rgb")
            q.shadow_alpha = _int(k["shadow"]["alpha"], 0, 256, w + ".shadow.alpha")
            q.cast_dx = q.cast_dy = q.cast_alpha = 0
            if ver == 2:
                _keys(k["cast"], ("dx", "dy", "alpha"), w + ".cast")
                q.cast_dx = _signed(k["cast"]["dx"], CAST_MAX_DX, w + ".cast.dx")
                q.cast_dy = _signed(k["cast"]["dy"], CAST_MAX_DY, w + ".cast.dy")
                q.cast_alpha = _int(k["cast"]["alpha"], 0, 256, w + ".cast.alpha")
            self.conditions.append(q)

    # ------------------------------------------------------------------- crops --
    def crop(self, name):
        """The crop for a condition: bytes of 1280*640 RGB."""
        if name not in self._crops:
            self._crops[name] = read_reference_png(self._crop_blobs[name], 2, name + ".png")
        return self._crops[name]

    # ------------------------------------------------------------------ lookup --
    def in_region(self, x, y):
        return self.rx0 <= x <= self.rx1 and self.ry0 <= y <= self.ry1

    def index(self, x, y):
        return (y - self.cy) * self.cw + (x - self.cx)

    def dry(self, x):
        """(top, bottom) of the always-dry band at column x, or None."""
        if not self.rx0 <= x <= self.rx1:
            return None
        t = self.dry_top[x - self.rx0]
        return None if t == -1 else (t, self.dry_bottom[x - self.rx0])

    def height_cap(self, y):
        if not self.ry0 <= y <= self.ry1:
            return None
        return self.max_h[y - self.ry0]

    def height_min(self, y):
        if not self.ry0 <= y <= self.ry1:
            return None
        return self.min_h[y - self.ry0]


def load_reference(path):
    if not os.path.isdir(path):
        raise ShoreError(ERR, "no reference set at %s" % path)
    return Reference(path)
