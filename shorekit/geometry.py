"""Where an object's pixels land, what it stands on, and its footprint.

Placement (SCHEMA.md, "Placement"): with scale s and anchor (ac, ar), the bitmap's top-left
pixel is (ox, oy) = (x - s//2 - ac*s, y - ar*s - (s-1)), and cell (c, r) covers pixels
ox + c*s .. ox + c*s + s-1 by oy + r*s .. oy + r*s + s-1. So the anchor cell's bottom row of
pixels is row y, and its columns are x - s//2 .. x - s//2 + s-1.

A footprint is the solid pixels (the bitmap's opaque cells and the label plaque) plus the contact
shadow. Everything here is integer arithmetic on frame pixels.

Kit 1.3.0: an object also throws a cast shadow, the silhouette of its solid pixels sheared along the
ground away from the sun or the moon (cast_pixels). It is drawn and never judged: it is no part of the
footprint, of any rule, or of the draw plan.

Look B: every opaque cell also gets a face, read off the bitmap's own silhouette, so the scene's
light can model it: TOP where nothing is drawn above the cell (it catches the sky and the sun as
the beach does), else EAST or WEST where it is open on the left or the right only (it catches a
low morning or evening sun; the viewer looks south, so east is on the left), else FRONT. Cells of
the manifest's `glow` key are lit from within at night.
"""
from . import CAST_MAX_DX, CAST_MAX_DY
from .errors import ShoreError
from .font import GAP, PLAQUE_H, plaque_cells

SURFACE_SHINGLE = "shingle"
SURFACE_PIER = "pier"
FACE_FRONT, FACE_TOP, FACE_EAST, FACE_WEST = 0, 1, 2, 3


def cell_face(rows, c, r):
    """The face of opaque cell (c, r): TOP if the cell above is empty (or r is 0), else EAST or WEST
    if exactly one of its left and right neighbours is empty (or off the grid), else FRONT."""
    if r == 0 or rows[r - 1][c] == ".":
        return FACE_TOP
    left = c == 0 or rows[r][c - 1] == "."
    right = c == len(rows[r]) - 1 or rows[r][c + 1] == "."
    if left and not right:
        return FACE_EAST
    if right and not left:
        return FACE_WEST
    return FACE_FRONT


class Placed:
    """An object as drawn: its solid pixels with albedo, label pixels, shadow, draw key."""

    __slots__ = ("id", "seq", "maker", "on", "surface", "manifest", "ox", "oy", "foot_y", "ground_y",
                 "left", "right", "top", "plaque", "solid", "label", "shadow", "bbox", "region_errors",
                 "foot_cells", "plaque_foot", "face", "glow", "rows")

    def key(self):
        return (self.ground_y, self.seq)


def _first(pts):
    return min(pts, key=lambda p: (p[1], p[0]))


def place(m, ref, support=None, seq=0):
    """Lay out manifest m against reference ref. `support` is the Placed it is built onto, if any.

    Returns a Placed; placement itself never fails. Rule 3 problems are kept in .region_errors."""
    p = Placed()
    p.id, p.seq, p.maker, p.on, p.manifest = m.id, seq, m.maker, m.on, m
    p.rows = None       # the silhouette by row, made when a cast shadow is first asked for (solid_rows)
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
    face = {}
    glow = set()
    outside = []
    on_keep = []
    cw, ch, cx0, cy0 = ref.cw, ref.ch, ref.cx, ref.cy
    rx0, ry0, rx1, ry1 = ref.rx0, ref.ry0, ref.rx1, ref.ry1
    keep = ref.keepout

    def put(X, Y, rgb, tag, f=FACE_FRONT, lit=False):
        if not (rx0 <= X <= rx1 and ry0 <= Y <= ry1):
            outside.append((X, Y, tag))
        else:
            i = (Y - cy0) * cw + (X - cx0)
            if keep[i]:
                on_keep.append((X, Y, tag))
        if cx0 <= X < cx0 + cw and cy0 <= Y < cy0 + ch:
            i = (Y - cy0) * cw + (X - cx0)
            solid[i] = rgb
            face[i] = f
            if lit:
                glow.add(i)
            else:
                glow.discard(i)

    pal = m.palette
    for r, row in enumerate(m.rows):
        for c, k in enumerate(row):
            if k == ".":
                continue
            rgb = pal[k]
            f = cell_face(m.rows, c, r)
            lit = k == m.glow
            bx, by = p.ox + c * s, p.oy + r * s
            for dy in range(s):
                for dx in range(s):
                    put(bx + dx, by + dy, rgb, ("cell", c, r), f, lit)

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
                    put(px0 + c, py0 + r, colours[k], ("plaque", c, r), FACE_TOP)   # look B: it leans back
                    if r == PLAQUE_H - 1:
                        p.plaque_foot.append(px0 + c)
        p.label = frozenset(i for i in solid if i not in before)
    p.solid = solid
    p.face = face
    p.glow = frozenset(glow)

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


def solid_rows(p, ref):
    """p's solid pixels as rows of runs: [(Y, [(x0, x1), ...]), ...] in frame pixels, rows from the top
    down, each row's maximal runs of consecutive columns from the left. Kept on p."""
    if p.rows is None:
        cw, cx, cy = ref.cw, ref.cx, ref.cy
        rows = []
        row = runs = None
        last = -2
        for i in sorted(p.solid):
            y = i // cw
            x = i - y * cw + cx
            if y != row:
                row, runs, last = y, [], -2
                rows.append((y + cy, runs))
            if x == last + 1:
                runs[-1][1] = x
            else:
                runs.append([x, x])
            last = x
        p.rows = [(Y, [(a, b) for a, b in runs]) for Y, runs in rows]
    return p.rows


def cast_pixels(p, ref, dx, dy):
    """The cast shadow of p under a light that lays dx/256 px of shadow to the right and dy/256 px down
    the frame for each px of height (either may be negative): a sorted tuple of crop indices.

    Write off(k, d) = (d*k + 128) >> 8 (to the nearest pixel, halves up). A solid pixel (X, Y), which is
    h = foot_y - Y px above the foot row, shades row foot_y + 1 + off(h, dy) from column
    X + min(off(h, dx), off(h+1, dx)) to column X + max(off(h, dx), off(h+1, dx)): the ground its own
    height sweeps over, so the shadow of each row runs on into the next row's and nothing is skipped
    (|dy| <= 256 keeps consecutive rows on the same ground row or on neighbouring ones). Kept where the
    contact shadow would be (SCHEMA.md 4.4): inside the region, off keep-out, not one of p's own solid
    pixels, and on ground (shingle: the column has a dry band and the row is at or below its top; pier:
    on the deck). An object built onto another casts none. Never part of p.shadow or of any rule."""
    if not (-CAST_MAX_DX <= dx <= CAST_MAX_DX and -CAST_MAX_DY <= dy <= CAST_MAX_DY):
        raise ValueError("cast direction (%d,%d) is outside +-%d, +-%d" % (dx, dy, CAST_MAX_DX, CAST_MAX_DY))
    if p.surface not in (SURFACE_SHINGLE, SURFACE_PIER) or p.on not in (SURFACE_SHINGLE, SURFACE_PIER):
        return ()
    rx0, ry0, rx1, ry1 = ref.rx0, ref.ry0, ref.rx1, ref.ry1
    foot = p.foot_y
    spans = {}
    for Y, runs in solid_rows(p, ref):
        h = foot - Y
        if h < 0:
            continue
        R = foot + 1 + ((dy * h + 128) >> 8)
        if not ry0 <= R <= ry1:
            continue
        a, b = (dx * h + 128) >> 8, (dx * (h + 1) + 128) >> 8
        if a > b:
            a, b = b, a
        row = spans.get(R)
        if row is None:
            row = spans[R] = []
        for x0, x1 in runs:
            row.append((x0 + a, x1 + b))
    cw, cx, cy = ref.cw, ref.cx, ref.cy
    keep, solid, deck, top = ref.keepout, p.solid, ref.deck_mask, ref.dry_top
    shingle = p.surface == SURFACE_SHINGLE
    out = []
    for R in sorted(spans):
        base = (R - cy) * cw - cx
        end = rx0 - 1               # the last column already looked at on this row
        for a, b in sorted(spans[R]):
            for X in range(max(a, end + 1), min(b, rx1) + 1):
                i = base + X
                if keep[i] or i in solid:
                    continue
                if shingle:
                    t = top[X - rx0]
                    if t == -1 or R < t:
                        continue
                elif not deck[i]:
                    continue
                out.append(i)
            if b > end:
                end = b
    return tuple(out)


def body_pixel(p, i):
    """True if crop index i is one of p's opaque bitmap pixels (not its plaque)."""
    return i in p.solid and i not in p.label


def check_height(p, ref):
    """Rule 1's height. Look B adds a floor: a thing standing on the shingle or the pier must be big
    enough to notice at desktop size, its width and height averaging at least min_h (so a long low log
    may stand where a sliver may not); a thing built onto another may be as small as it likes."""
    m = p.manifest
    cap = ref.height_cap(p.ground_y)
    if cap is None:
        return []
    h = m.h * m.scale
    if h > cap:
        return [ShoreError("E_SIZE", "%d px tall standing at y=%d, max %d there" % (h, p.ground_y, cap))]
    if m.on in (SURFACE_SHINGLE, SURFACE_PIER):
        low = ref.height_min(p.ground_y)
        w = m.w * m.scale
        if w + h < 2 * low:
            return [ShoreError("E_SIZE", "%dx%d px standing at y=%d: its sides average %d px, min %d there (too small"
                               " to notice)" % (w, h, p.ground_y, (w + h) // 2, low))]
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
