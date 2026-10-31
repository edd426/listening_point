"""`shorekit import`: turn an author's own small PNG into a manifest.

The picture never leaves the author's sandbox: what is sent is the indexed bitmap JSON.
"""
import json

from . import KIT_VERSION, MAX_KEYS
from .errors import ShoreError
from .manifest import manifest_from_obj
from .png import read_import_png

KEYS = "abcdefghijklmnopqrstuvwxyz"


def png_to_manifest(data, oid, maker, on, x, y, reference, anchor=None, scale=1, label=None, side="right"):
    """Returns (manifest object, notes). Raises ShoreError (E_IMPORT, or the manifest's own codes)."""
    w, h, px = read_import_png(data)
    for i, (r, g, b, a) in enumerate(px):
        if 0 < a < 255:
            raise ShoreError("E_IMPORT", "pixel (%d,%d) is partly transparent (alpha %d); use 0 or 255" % (i % w, i // w, a))
    opaque = [[px[yy * w + xx][3] == 255 for xx in range(w)] for yy in range(h)]
    rows_on = [yy for yy in range(h) if any(opaque[yy])]
    cols_on = [xx for xx in range(w) if any(opaque[yy][xx] for yy in range(h))]
    if not rows_on:
        raise ShoreError("E_IMPORT", "the picture is fully transparent")
    y0, y1, x0, x1 = rows_on[0], rows_on[-1], cols_on[0], cols_on[-1]
    keys = {}
    rows = []
    for yy in range(y0, y1 + 1):
        line = []
        for xx in range(x0, x1 + 1):
            r, g, b, a = px[yy * w + xx]
            if a == 0:
                line.append(".")
                continue
            if (r, g, b) not in keys:
                if len(keys) == MAX_KEYS:
                    raise ShoreError("E_IMPORT", "more than %d colours (the %dth is at (%d,%d))" % (MAX_KEYS, MAX_KEYS + 1, xx, yy))
                keys[(r, g, b)] = KEYS[len(keys)]
            line.append(keys[(r, g, b)])
        rows.append("".join(line))
    if anchor is None:
        last = rows[-1]
        on_cells = [c for c, k in enumerate(last) if k != "."]
        anchor = ((on_cells[0] + on_cells[-1]) >> 1, len(rows) - 1)
    obj = {"shore": 1, "id": oid, "maker": maker, "kit": KIT_VERSION, "reference": reference,
           "palette": {k: list(rgb) for rgb, k in keys.items()}, "rows": rows, "scale": scale,
           "anchor": [anchor[0], anchor[1]], "place": {"on": on, "x": x, "y": y}}
    if label is not None:
        obj["label"] = {"text": label, "side": side}
    manifest_from_obj(obj)
    notes = []
    if (x0, y0, x1, y1) != (0, 0, w - 1, h - 1):
        notes.append("trimmed to %dx%d cells from %dx%d (offset %d,%d)" % (x1 - x0 + 1, y1 - y0 + 1, w, h, x0, y0))
    return obj, notes


def pretty(obj):
    """A readable manifest: sorted keys, one bitmap row per line. Parses to the same object."""
    keys = sorted(obj)
    lines = ["{"]
    for n, k in enumerate(keys):
        v = obj[k]
        if k == "rows":
            body = '"rows": [\n' + ",\n".join('    "%s"' % r for r in v) + "\n  ]"
        elif k == "palette":
            body = '"palette": {' + ", ".join('"%s": [%d, %d, %d]' % (p, v[p][0], v[p][1], v[p][2]) for p in sorted(v)) + "}"
        else:
            body = '"%s": %s' % (k, json.dumps(v, sort_keys=True, separators=(", ", ": ")))
        lines.append("  " + body + ("," if n < len(keys) - 1 else ""))
    lines.append("}")
    return ("\n".join(lines) + "\n").encode("ascii")
