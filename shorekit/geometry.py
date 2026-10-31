"""Where an object's pixels land, what it stands on, and its footprint.

Placement (SCHEMA.md, "Placement"): with scale s and anchor (ac, ar), the bitmap's top-left
pixel is (ox, oy) = (x - s//2 - ac*s, y - ar*s - (s-1)), and cell (c, r) covers pixels
ox + c*s .. ox + c*s + s-1 by oy + r*s .. oy + r*s + s-1. So the anchor cell's bottom row of
pixels is row y, and its columns are x - s//2 .. x - s//2 + s-1.

A footprint is the solid pixels (the bitmap's opaque cells and the label plaque) plus the contact
shadow. Everything here is integer arithmetic on frame pixels.
"""
from .errors import ShoreError
from .font import GAP, PLAQUE_H, plaque_cells

SURFACE_SHINGLE = "shingle"
SURFACE_PIER = "pier"


class Placed:
    """An object as drawn: its solid pixels with albedo, label pixels, shadow, draw key."""

    __slots__ = ("id", "seq", "maker", "on", "surface", "manifest", "ox", "oy", "foot_y", "ground_y",
                 "left", "right", "top", "plaque", "solid", "label", "shadow", "bbox", "region_errors",
                 "foot_cells", "plaque_foot")

    def key(self):
        return (self.ground_y, self.seq)


def _first(pts):
    return min(pts, key=lambda p: (p[1], p[0]))


def place(m, ref, support=None, seq=0):
    """Lay out manifest m against reference ref. `support` is the Placed it is built onto, if any.

    Returns a Placed; placement itself never fails. Rule 3 problems are kept in .region_errors."""
    p = Placed()
    p.id, p.seq, p.maker, p.on, p.manifest = m.id, seq, m.maker, m.on, m
    s = m.scale
    ac, ar = m.anchor
    p.ox = m.x - s // 2 - ac * s
    p.oy = m.y - ar * s - (s - 1)
    p.left, p.right, p.top = p.ox, p.ox + m.w * s - 1, p.oy
    p.foot_y = p.oy + m.h * s - 1
    if m.on in (SURFACE_SHINGLE, SURFACE_PIER):
        p.surface = m.on
        p.ground_y = p.foot_y
    else:
        p.surface = support.surface if support is not None else None
        p.ground_y = support.ground_y if support is not None else p.foot_y

    solid = {}
    outside = []
    on_keep = []
    cw, ch, cx0, cy0 = ref.cw, ref.ch, ref.cx, ref.cy
    rx0, ry0, rx1, ry1 = ref.rx0, ref.ry0, ref.rx1, ref.ry1
    keep = ref.keepout

    def put(X, Y, rgb, tag):
        if not (rx0 <= X <= rx1 and ry0 <= Y <= ry1):
            outside.append((X, Y, tag))
        else:
            i = (Y - cy0) * cw + (X - cx0)
            if keep[i]:
                on_keep.append((X, Y, tag))
        if cx0 <= X < cx0 + cw and cy0 <= Y < cy0 + ch:
            solid[(Y - cy0) * cw + (X - cx0)] = rgb

    pal = m.palette
    for r, row in enumerate(m.rows):
        for c, k in enumerate(row):
            if k == ".":
                continue
            rgb = pal[k]
            bx, by = p.ox + c * s, p.oy + r * s
            for dy in range(s):
                for dx in range(s):
                    put(bx + dx, by + dy, rgb, ("cell", c, r))

    p.plaque = None
    p.label = frozenset()
    p.plaque_foot = []
    if m.label is not None:
        rows = plaque_cells(m.label)
        pw = len(rows[0])
        px0 = p.right + 1 + GAP if m.side == "right" else p.left - GAP - pw
        py0 = p.foot_y - PLAQUE_H + 1
        p.plaque = (px0, py0, pw, PLAQUE_H)
        colours = {"w": ref.plaque["wood"], "g": ref.plaque["grain"], "i": ref.plaque["ink"]}
        before = set(solid)
        for r, line in enumerate(rows):
            for c, k in enumerate(line):
                if k != ".":
                    put(px0 + c, py0 + r, colours[k], ("plaque", c, r))
                    if r == PLAQUE_H - 1:
                        p.plaque_foot.append(px0 + c)
        p.label = frozenset(i for i in solid if i not in before)
    p.solid = solid

    # foot cells: the opaque cells of the bottom row, whose bottom pixel row is foot_y
    last = m.rows[-1]
    p.foot_cells = [(c, m.h - 1, [p.ox + c * s + dx for dx in range(s)]) for c, k in enumerate(last) if k != "."]

    p.region_errors = []
    for pts, how in ((outside, "is outside the shore (x %d-%d, y %d-%d)" % (rx0, rx1, ry0, ry1)),
                     (on_keep, "is on keep-out")):
        for kind in ("cell", "plaque"):
            sel = [q for q in pts if q[2][0] == kind]
            if sel:
                X, Y, tag = _first(sel)
                what = "cell (%d,%d)" % (tag[1], tag[2]) if kind == "cell" else "label plaque"
                more = " (and %d more px)" % (len(sel) - 1) if len(sel) > 1 else ""
                p.region_errors.append(ShoreError("E_REGION", "%s at (%d,%d) %s%s" % (what, X, Y, how, more)))

    # the contact shadow: under each run of the foot row, two pixels deep, one wider on the first row
    shadow = set()
    if p.surface in (SURFACE_SHINGLE, SURFACE_PIER) and m.on in (SURFACE_SHINGLE, SURFACE_PIER):
        feet = sorted(set(X for _, _, xs in p.foot_cells for X in xs) | set(p.plaque_foot))
        runs = []
        for X in feet:
            if runs and X == runs[-1][1] + 1:
                runs[-1][1] = X
            else:
                runs.append([X, X])
        cand = []
        for a, b in runs:
            cand += [(X, p.foot_y + 1) for X in range(a - 1, b + 2)]
            cand += [(X, p.foot_y + 2) for X in range(a, b + 1)]
        for X, Y in cand:
            if not (rx0 <= X <= rx1 and ry0 <= Y <= ry1):
                continue
            i = (Y - cy0) * cw + (X - cx0)
            if keep[i] or i in solid:
                continue
            if p.surface == SURFACE_SHINGLE:
                band = ref.dry(X)
                if band is None or Y < band[0]:
                    continue
            elif not ref.deck_mask[i]:
                continue
            shadow.add(i)
    p.shadow = tuple(sorted(shadow))

    idx = list(solid) + list(p.shadow)
    if idx:
        ys = [i // cw for i in idx]
        xs = [i % cw for i in idx]
        p.bbox = (min(xs), min(ys), max(xs), max(ys))
    else:
        p.bbox = None
    return p


def body_pixel(p, i):
    """True if crop index i is one of p's opaque bitmap pixels (not its plaque)."""
    return i in p.solid and i not in p.label


def check_height(p, ref):
    m = p.manifest
    cap = ref.height_cap(p.ground_y)
    if cap is None:
        return []
    h = m.h * m.scale
    if h > cap:
        return [ShoreError("E_SIZE", "%d px tall standing at y=%d, max %d there" % (h, p.ground_y, cap))]
    return []


def _band_fault(ref, X, Y):
    band = ref.dry(X)
    if band is None:
        return "has no dry band under it at x=%d" % X
    if Y < band[0]:
        return "%d px above dry band at x=%d" % (band[0] - Y, X)
    if Y > band[1]:
        return "%d px below dry band at x=%d" % (Y - band[1], X)
    return None


def check_resting(p, ref, support):
    """Rule 4. Nothing floats: the foot row sits on the dry band, the deck, or half on the support."""
    errs = []
    Y = p.foot_y
    if p.on == SURFACE_SHINGLE:
        bad = []
        for c, r, xs in p.foot_cells:
            for X in xs:
                f = _band_fault(ref, X, Y)
                if f:
                    bad.append((c, r, f))
                    break
        if bad:
            c, r, f = bad[0]
            more = " (and %d more foot cells)" % (len(bad) - 1) if len(bad) > 1 else ""
            errs.append(ShoreError("E_REST", "foot cell (%d,%d) %s%s" % (c, r, f, more)))
        if p.plaque_foot:
            pbad = [(X, _band_fault(ref, X, Y)) for X in p.plaque_foot]
            pbad = [q for q in pbad if q[1]]
            if pbad:
                errs.append(ShoreError("E_REST", "label plaque foot %s" % pbad[0][1]))
    elif p.on == SURFACE_PIER:
        def off(X):
            return not (ref.rx0 <= X <= ref.rx1 and ref.ry0 <= Y <= ref.ry1) or not ref.deck_mask[ref.index(X, Y)]
        bad = [(c, r, X) for c, r, xs in p.foot_cells for X in xs if off(X)]
        if bad:
            c, r, X = bad[0]
            cells = len(set((q[0], q[1]) for q in bad))
            more = " (and %d more foot cells)" % (cells - 1) if cells > 1 else ""
            errs.append(ShoreError("E_REST", "foot cell (%d,%d) at (%d,%d) is off the deck%s" % (c, r, X, Y, more)))
        pb = [X for X in p.plaque_foot if off(X)]
        if pb:
            errs.append(ShoreError("E_REST", "label plaque foot at (%d,%d) is off the deck" % (pb[0], Y)))
    else:
        def rests(xs):
            n = 0
            for X in xs:
                if ref.cx <= X < ref.cx + ref.cw and ref.cy <= Y + 1 < ref.cy + ref.ch and body_pixel(support, ref.index(X, Y + 1)):
                    n += 1
            return n
        feet = [X for _, _, xs in p.foot_cells for X in xs]
        n = rests(feet)
        if 2 * n < len(feet):
            errs.append(ShoreError("E_REST", "only %d of %d foot px rest on %s, need half" % (n, len(feet), support.id)))
        if p.plaque_foot:
            n = rests(p.plaque_foot)
            if 2 * n < len(p.plaque_foot):
                errs.append(ShoreError("E_REST", "only %d of %d label plaque foot px rest on %s, need half"
                                       % (n, len(p.plaque_foot), support.id)))
    return errs
