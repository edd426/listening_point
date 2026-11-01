"""The object manifest: an indexed bitmap in JSON, its placement and an optional label.

parse_manifest() checks the schema only. The rules that need no reference data (size by cell
count, the channel cap, the label) live in rules.py beside the others.
"""
import hashlib
import re

from . import KIT_VERSION, MAX_CELLS_SIDE, MAX_KEYS, MAX_SCALE
from .errors import ShoreError
from .strictjson import canonical, is_int, is_str, loads

MAX_BYTES = 16384
MAX_DEPTH = 4

ID_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]{1,40}", re.ASCII)
MAKER_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}", re.ASCII)
WORLD_RE = MAKER_RE
KIT_RE = re.compile(r"([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})", re.ASCII)
REF_RE = re.compile(r"r[1-9][0-9]{0,3}", re.ASCII)
KEY_RE = re.compile(r"[a-z]", re.ASCII)

REQUIRED = ("anchor", "id", "kit", "maker", "palette", "place", "reference", "rows", "scale", "shore")
OPTIONAL = ("glow", "label")
SURFACES = ("shingle", "pier")


def days_in_month(y, m):
    if m == 2:
        leap = (y % 4 == 0 and y % 100 != 0) or y % 400 == 0
        return 29 if leap else 28
    return 30 if m in (4, 6, 9, 11) else 31


def valid_date(y, m, d):
    return 2000 <= y <= 2999 and 1 <= m <= 12 and 1 <= d <= days_in_month(y, m)


def check_id(v, what="id"):
    if not is_str(v) or not ID_RE.fullmatch(v):
        raise ShoreError("E_ID", '%s must match YYYY-MM-DD-slug (slug: 1-40 of a-z 0-9 -), got %s'
                         % (what, _show(v)))
    y, m, d = int(v[0:4]), int(v[5:7]), int(v[8:10])
    if not valid_date(y, m, d):
        raise ShoreError("E_ID", "%s %s does not start with a real date" % (what, v))
    return v


def id_date(v):
    return v[:10]


def kit_major(v):
    return int(KIT_RE.fullmatch(v).group(1))


def _show(v):
    if is_str(v):
        return '"%s"' % v[:48]
    if v is True or v is False:
        return "a boolean"
    if v is None:
        return "null"
    if is_int(v):
        return str(v)
    return "a " + {list: "list", dict: "object"}.get(type(v), type(v).__name__)


def _int_in(obj, key, lo, hi, where):
    v = obj[key]
    if not is_int(v) or not lo <= v <= hi:
        raise ShoreError("E_SCHEMA", '%s"%s" must be an integer %d-%d, got %s' % (where, key, lo, hi, _show(v)))
    return v


def _exact_keys(obj, required, optional, where):
    for k in sorted(obj):
        if k not in required and k not in optional:
            raise ShoreError("E_SCHEMA", '%sunknown key "%s"' % (where, k[:40]))
    for k in required:
        if k not in obj:
            raise ShoreError("E_SCHEMA", '%smissing key "%s"' % (where, k))


class Manifest:
    """A parsed, schema-checked object. Coordinates are frame pixels (2880 x 1800)."""

    __slots__ = ("id", "maker", "kit", "reference", "palette", "rows", "w", "h", "scale", "anchor",
                 "on", "x", "y", "label", "side", "glow", "obj", "canonical", "sha256")

    def opaque_cells(self):
        return sum(len(r) - r.count(".") for r in self.rows)


def manifest_from_obj(obj):
    if type(obj) is not dict:
        raise ShoreError("E_SCHEMA", "a manifest must be a JSON object")
    _exact_keys(obj, REQUIRED, OPTIONAL, "")
    m = Manifest()
    if not is_int(obj["shore"]) or obj["shore"] != 1:
        raise ShoreError("E_SCHEMA", '"shore" must be 1, got %s' % _show(obj["shore"]))
    m.id = check_id(obj["id"])
    v = obj["maker"]
    if not is_str(v) or not MAKER_RE.fullmatch(v):
        raise ShoreError("E_SCHEMA", '"maker" must match [a-z0-9][a-z0-9-]{0,31}, got %s' % _show(v))
    m.maker = v
    v = obj["kit"]
    if not is_str(v) or not KIT_RE.fullmatch(v):
        raise ShoreError("E_SCHEMA", '"kit" must be a version like "%s", got %s' % (KIT_VERSION, _show(v)))
    m.kit = v
    v = obj["reference"]
    if not is_str(v) or not REF_RE.fullmatch(v):
        raise ShoreError("E_SCHEMA", '"reference" must be like "r1", got %s' % _show(v))
    m.reference = v

    pal = obj["palette"]
    if type(pal) is not dict or not 1 <= len(pal) <= MAX_KEYS:
        raise ShoreError("E_SCHEMA", '"palette" must be an object with 1-%d keys' % MAX_KEYS)
    palette = {}
    for k in sorted(pal):
        if not KEY_RE.fullmatch(k):
            raise ShoreError("E_SCHEMA", 'palette key "%s" must be one letter a-z' % k[:8])
        c = pal[k]
        if type(c) is not list or len(c) != 3 or not all(is_int(x) and 0 <= x <= 255 for x in c):
            raise ShoreError("E_SCHEMA", 'palette "%s" must be [r, g, b] with integers 0-255' % k)
        palette[k] = (c[0], c[1], c[2])
    m.palette = palette

    rows = obj["rows"]
    if type(rows) is not list or not 1 <= len(rows) <= MAX_CELLS_SIDE:
        raise ShoreError("E_SCHEMA", '"rows" must be a list of 1-%d strings' % MAX_CELLS_SIDE)
    allowed = set(palette) | {"."}
    w = None
    used = set()
    for r, row in enumerate(rows):
        if not is_str(row) or not 1 <= len(row) <= MAX_CELLS_SIDE:
            raise ShoreError("E_SCHEMA", "row %d must be a string of 1-%d cells" % (r, MAX_CELLS_SIDE))
        if w is None:
            w = len(row)
        elif len(row) != w:
            raise ShoreError("E_SCHEMA", "row %d is %d cells wide, row 0 is %d" % (r, len(row), w))
        for c, ch in enumerate(row):
            if ch not in allowed:
                raise ShoreError("E_SCHEMA", 'cell (%d,%d) is "%s", not a palette key or "."' % (c, r, ch))
        used.update(row)
    for k in sorted(palette):
        if k not in used:
            raise ShoreError("E_SCHEMA", 'palette key "%s" is never used' % k)
    if rows[0].count(".") == w or rows[-1].count(".") == w:
        raise ShoreError("E_SCHEMA", "row %d is empty: trim transparent rows" % (0 if rows[0].count(".") == w else len(rows) - 1))
    if all(row[0] == "." for row in rows) or all(row[-1] == "." for row in rows):
        raise ShoreError("E_SCHEMA", "column %d is empty: trim transparent columns"
                         % (0 if all(row[0] == "." for row in rows) else w - 1))
    m.rows = tuple(rows)
    m.w, m.h = w, len(rows)

    v = obj["scale"]
    if not is_int(v) or not 1 <= v <= MAX_SCALE:
        raise ShoreError("E_SCHEMA", '"scale" must be 1-%d, got %s' % (MAX_SCALE, _show(v)))
    m.scale = v
    a = obj["anchor"]
    if type(a) is not list or len(a) != 2 or not all(is_int(x) for x in a):
        raise ShoreError("E_SCHEMA", '"anchor" must be [column, row]')
    if not (0 <= a[0] < m.w and 0 <= a[1] < m.h):
        raise ShoreError("E_SCHEMA", "anchor (%d,%d) is outside the %dx%d grid" % (a[0], a[1], m.w, m.h))
    m.anchor = (a[0], a[1])

    p = obj["place"]
    if type(p) is not dict:
        raise ShoreError("E_SCHEMA", '"place" must be an object')
    _exact_keys(p, ("on", "x", "y"), (), "place: ")
    on = p["on"]
    if not is_str(on):
        raise ShoreError("E_SCHEMA", 'place "on" must be "shingle", "pier" or an object id')
    if on not in SURFACES:
        if not ID_RE.fullmatch(on):
            raise ShoreError("E_SCHEMA", 'place "on" must be "shingle", "pier" or an object id, got %s' % _show(on))
        check_id(on, 'place "on"')
        if on == m.id:
            raise ShoreError("E_SCHEMA", "an object cannot be built onto itself")
    m.on = on
    m.x = _int_in(p, "x", 0, 9999, "place ")
    m.y = _int_in(p, "y", 0, 9999, "place ")

    m.label = None
    m.side = None
    if "label" in obj:
        lab = obj["label"]
        if type(lab) is not dict:
            raise ShoreError("E_SCHEMA", '"label" must be an object')
        _exact_keys(lab, ("side", "text"), (), "label: ")
        if not is_str(lab["text"]) or not 1 <= len(lab["text"]) <= 64:
            raise ShoreError("E_SCHEMA", 'label "text" must be a string')
        if lab["side"] not in ("left", "right"):
            raise ShoreError("E_SCHEMA", 'label "side" must be "left" or "right", got %s' % _show(lab["side"]))
        m.label = lab["text"]
        m.side = lab["side"]

    m.glow = None
    if "glow" in obj:
        g = obj["glow"]
        if not is_str(g) or not KEY_RE.fullmatch(g) or g not in palette:
            raise ShoreError("E_SCHEMA", '"glow" must name one palette key, got %s' % _show(g))
        m.glow = g

    m.obj = obj
    m.canonical = canonical(obj)
    m.sha256 = hashlib.sha256(m.canonical).hexdigest()
    return m


def parse_manifest(data):
    """bytes -> Manifest. Raises ShoreError (E_PARSE, E_SCHEMA, E_ID)."""
    return manifest_from_obj(loads(data, MAX_BYTES, MAX_DEPTH, "manifest"))
