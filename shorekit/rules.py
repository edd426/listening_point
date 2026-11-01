"""Validator rules 1-6 (BUILD section 2). Rule 7, the quotas, needs the ledger: see ledger.py.

Every comparison is between integers; a percentage threshold t is tested as 100*part >= t*whole.
"""
from array import array

from . import FAINT_CONDITIONS, FAINT_D, FAINT_RING, GLOW_MAX_PX, MAX_CHANNEL, MAX_OPAQUE, MIN_OPAQUE
from .errors import ShoreError
from .font import check_label
from .geometry import SURFACE_PIER, SURFACE_SHINGLE, check_height, check_resting, place

OLDER_KEEPS = 60       # each older object keeps at least this % of its footprint visible
NEWCOMER_TAKES = 25    # the newcomer takes at most this % of any one object
NEWCOMER_SHOWS = 50    # the newcomer itself is at least this % visible


def isqrt(n):
    """Floor square root of a non-negative integer."""
    if n < 2:
        return n
    x = 1 << ((n.bit_length() + 1) >> 1)
    while True:
        y = (x + n // x) >> 1
        if y >= x:
            return x
        x = y


def redmean512(c1, c2):
    """512 x the squared redmean distance, exactly: (1024+R1+R2)dR^2 + 2048 dG^2 + (1534-R1-R2)dB^2."""
    rs = c1[0] + c2[0]
    dr, dg, db = c1[0] - c2[0], c1[1] - c2[1], c1[2] - c2[2]
    return (1024 + rs) * dr * dr + 2048 * dg * dg + (1534 - rs) * db * db


def _nearest(c, entries):
    best = None
    for name, rgb in entries:
        d = redmean512(c, rgb)
        if best is None or d < best[0]:
            best = (d, name, rgb)
    return best


def check_local(m, ref):
    """Rules 1 (cell count), 2 (palette, and look B's glow) and 6 (label text): the ones that need no
    placement."""
    errs = []
    n = m.opaque_cells()
    if not MIN_OPAQUE <= n <= MAX_OPAQUE:
        errs.append(ShoreError("E_SIZE", "%d opaque cells, need %d-%d" % (n, MIN_OPAQUE, MAX_OPAQUE)))
    lim = 512 * ref.d * ref.d
    for k in sorted(m.palette):
        c = m.palette[k]
        hi = max(c)
        if hi > MAX_CHANNEL:
            errs.append(ShoreError("E_PALETTE", "'%s' (%d,%d,%d) has a channel of %d, max %d" % (k, c[0], c[1], c[2], hi, MAX_CHANNEL)))
            continue
        if k == m.glow:
            # the lit key is judged against the reference's light colours only
            best = _nearest(c, ref.glow)
            if best is None or best[0] > lim:
                if best is None:
                    errs.append(ShoreError("E_GLOW", "this reference set has no light colours: nothing may glow"))
                else:
                    d, name, rgb = best
                    errs.append(ShoreError("E_GLOW", "glow '%s' (%d,%d,%d) is %d from the nearest light colour %s (%d,%d,%d), max %d"
                                           % (k, c[0], c[1], c[2], isqrt(d // 512), name, rgb[0], rgb[1], rgb[2], ref.d)))
            px = sum(row.count(k) for row in m.rows) * m.scale * m.scale
            if px > GLOW_MAX_PX:
                errs.append(ShoreError("E_GLOW", "glow '%s' lights %d px, max %d" % (k, px, GLOW_MAX_PX)))
            continue
        best = None
        for name, rgb in ref.palette:
            d = redmean512(c, rgb)
            if best is None or d < best[0]:
                best = (d, name, rgb)
        if best[0] > lim:
            d, name, rgb = best
            errs.append(ShoreError("E_PALETTE", "'%s' (%d,%d,%d) is %d from the nearest reference colour %s (%d,%d,%d), max %d"
                                   % (k, c[0], c[1], c[2], isqrt(d // 512), name, rgb[0], rgb[1], rgb[2], ref.d)))
    if m.label is not None:
        try:
            check_label(m.label)
        except ShoreError as e:
            errs.append(e)
    return errs


def paint(objs, n):
    """Painter's algorithm over objects already in draw order.

    Returns (owner, drawn): owner[i] is 1 + the index of the object whose solid pixel shows at crop
    index i (0 for ground); drawn[k] lists the shadow pixels object k actually casts, which are
    those not already covered by an object drawn before it (shadows never fall on objects)."""
    owner = array("H", bytes(2 * n))
    drawn = []
    for k, o in enumerate(objs, 1):
        drawn.append([i for i in o.shadow if owner[i] == 0])
        for i in o.solid:
            owner[i] = k
    return owner, drawn


def _overlaps(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def draw_order(objs):
    return sorted(objs, key=lambda o: (o.ground_y, o.seq))


def occlusion(new, live, ref):
    """Rule 5, add never erase. `live` are the objects already on the shore."""
    if new.bbox is None:
        return []
    near = [a for a in live if a.bbox is not None and _overlaps(a.bbox, new.bbox)]
    if not near:
        return []
    box = _union([new.bbox] + [a.bbox for a in near])
    group = [b for b in live if b.bbox is not None and _overlaps(b.bbox, box)]
    before = draw_order(group)
    after = draw_order(group + [new])
    n = ref.cw * ref.ch
    ob, sb = paint(before, n)
    oa, sa = paint(after, n)
    kb = {id(o): k for k, o in enumerate(before, 1)}
    ka = {id(o): k for k, o in enumerate(after, 1)}
    cw = ref.cw

    def at(i):
        return "(%d,%d)" % (i % cw + ref.cx, i // cw + ref.cy)

    errs = []
    for a in sorted(near, key=lambda o: o.seq):
        b, k = kb[id(a)], ka[id(a)]
        shadow = sb[b - 1]
        whole = len(a.solid) + len(shadow)
        if whole == 0:
            continue
        shown = [i for i in a.solid if ob[i] == b] + [i for i in shadow if ob[i] == 0]
        lost = [i for i in a.solid if ob[i] == b and oa[i] != k] + [i for i in shadow if ob[i] == 0 and oa[i] != 0]
        if not lost:
            continue
        keeps = len(shown) - len(lost)
        first = at(min(lost))
        if 100 * keeps < OLDER_KEEPS * whole:
            errs.append(ShoreError("E_COVER", "would leave %s %d%% visible (needs %d%%); first covered px at %s"
                                   % (a.id, keeps * 100 // whole, OLDER_KEEPS, first)))
        if 100 * len(lost) > NEWCOMER_TAKES * whole:
            errs.append(ShoreError("E_COVER", "takes %d%% of %s (max %d%%); first covered px at %s"
                                   % (-((-len(lost) * 100) // whole), a.id, NEWCOMER_TAKES, first)))
        lab = [i for i in a.label if oa[i] != k]
        if lab:
            errs.append(ShoreError("E_LABEL_COVER", "covers the label of %s at %s" % (a.id, at(min(lab)))))
    k = ka[id(new)]
    shadow = sa[k - 1]
    whole = len(new.solid) + len(shadow)
    hidden = [i for i in new.solid if oa[i] != k] + [i for i in shadow if oa[i] != 0]
    if hidden and 100 * (whole - len(hidden)) < NEWCOMER_SHOWS * whole:
        by = sorted(set(after[oa[i] - 1].id for i in hidden))
        errs.append(ShoreError("E_HIDDEN", "only %d%% visible (needs %d%%); hidden by %s, first at %s"
                               % ((whole - len(hidden)) * 100 // whole, NEWCOMER_SHOWS, ", ".join(by), at(min(hidden)))))
    lab = [i for i in new.label if oa[i] != k]
    if lab:
        i = min(lab)
        errs.append(ShoreError("E_LABEL_COVER", "its label would be hidden by %s at %s" % (after[oa[i] - 1].id, at(i))))
    return errs


def check_stand_out(p, ref):
    """Look C, rule 7 (E_FAINT): a thing must be noticeable against the ground it stands on. Its body
    (not its label), lit as the kit lights it, averages a colour; the reference crop around it (its box
    grown by FAINT_RING px, less its own pixels and its shadow) averages another; at each of
    FAINT_CONDITIONS the two must be at least FAINT_D apart (redmean). A grey cairn on grey shingle fails;
    the same cairn whitewashed, or on the grass, passes."""
    from .compose import shade      # compose imports this module, so not at the top
    body = sorted(i for i in p.solid if i not in p.label)
    if not body or p.bbox is None:
        return []
    cw, ch = ref.cw, ref.ch
    x0, y0, x1, y1 = p.bbox
    x0, y0 = max(0, x0 - FAINT_RING), max(0, y0 - FAINT_RING)
    x1, y1 = min(cw - 1, x1 + FAINT_RING), min(ch - 1, y1 + FAINT_RING)
    skip = set(p.solid)
    skip.update(p.shadow)
    conds = {c.name: c for c in ref.conditions}
    n = len(body)
    for name in FAINT_CONDITIONS:
        cond = conds.get(name)
        if cond is None:
            continue
        crop = ref.crop(name)
        o = [0, 0, 0]
        for i in body:
            y = i // cw
            x = i - y * cw
            rgb, L = p.solid[i], cond.lights[p.face.get(i, 0)]
            for c in range(3):
                o[c] += shade(rgb[c], L[c], cond.lut[c], cond.veil_alpha[y], cond.veil_rgb[c], ref.vignette[y >> 4][x >> 4])
        g = [0, 0, 0]
        m = 0
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                i = y * cw + x
                if i in skip:
                    continue
                for c in range(3):
                    g[c] += crop[3 * i + c]
                m += 1
        if m == 0:
            continue
        om = tuple(v // n for v in o)
        gm = tuple(v // m for v in g)
        d = redmean512(om, gm)
        if d < 512 * FAINT_D * FAINT_D:
            y = body[0] // cw
            x = body[0] - y * cw
            return [ShoreError("E_FAINT", "at %s it averages (%d,%d,%d) against (%d,%d,%d) around it, %d apart, min %d:"
                               " too like the ground to notice (first px at (%d,%d))"
                               % (name, om[0], om[1], om[2], gm[0], gm[1], gm[2], isqrt(d // 512), FAINT_D,
                                  x + ref.cx, y + ref.cy))]
    return []


def evaluate(m, ref, live, seq, taken=()):
    """Rules 1-6 for manifest m as the next object (sequence number seq) on a shore holding `live`
    (Placed objects, any order). Returns (errors, placed); placed is None if it could not be laid out."""
    errs = check_local(m, ref)
    if errs:
        return errs, None
    support = None
    if m.on not in (SURFACE_SHINGLE, SURFACE_PIER):
        for a in live:
            if a.id == m.on:
                support = a
        if support is None:
            if m.on in taken:
                return [ShoreError("E_ON", "%s is no longer on the shore (the sea took it)" % m.on)], None
            return [ShoreError("E_ON", "there is no object %s on the shore to build onto" % m.on)], None
    p = place(m, ref, support, seq)
    errs = list(p.region_errors)
    errs += check_height(p, ref)
    errs += check_resting(p, ref, support)
    if errs:
        return errs, p
    errs = check_stand_out(p, ref)
    if errs:
        return errs, p
    return occlusion(p, live, ref), p
