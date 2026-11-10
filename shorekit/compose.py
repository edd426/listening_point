"""The integer compositor: the preview sheet, the zoom, and the draw plan the Mac follows.

An object pixel of albedo A (per channel c) at crop pixel (x, y) under a condition is

    t = A_c * L_c                         light L is x256
    u = t * (256 - a_y) + V_c * 256 * a_y  the fog veil: colour V, alpha a_y (x256) for the row
    w = (u * vig) >> 24                    vig is the vignette (x256) of the 16-px cell
    out_c = LUT_c[min(w, 511)]

and a contact-shadow pixel over the crop's own colour G is (G_c * (256 - s) + S_c * s) >> 8.

Kit 1.3.0: before the contact shadows, every ground pixel some object's cast shadow falls on
(geometry.cast_pixels, for the condition's cast.dx and cast.dy) is darkened once, however many shadows
meet there: (G_c * (256 - cast.alpha)) >> 8. No object's pixel is ever touched. A condition without
`cast` (a reference set written before 1.3.0) has no cast shadows at all.

Look B: L is the light on the pixel's face (front, top, east or west, see geometry.cell_face), and a
pixel of the manifest's glow key also emits t += (A_c * EMIT * lamps) >> 8, with the condition's
lamps (x256) and EMIT = 410 (1.6 x256): lamplight that comes on with the scene's own lamps.
"""
import hashlib

from .geometry import cast_pixels
from .png import write_png
from .rules import draw_order, paint

EMIT = 410          # look B: a glow pixel emits 1.6 x its albedo when the lamps are fully lit
ZOOM = 4
ZOOM_MARGIN = 24
ZOOM_MAX_W, ZOOM_MAX_H = 400, 250


def shade(alb, light, lut, a, veil, vig, lamps=0):
    t = alb * light + ((alb * EMIT * lamps) >> 8)
    u = t * (256 - a) + veil * 256 * a
    w = (u * vig) >> 24
    return lut[w if w < 512 else 511]


def cast_shown(ref, objs, dx, dy):
    """The ground the cast shadows of `objs` darken under a light of direction (dx, dy), x256 px of shadow
    per px of height (geometry.cast_pixels): every pixel some object's shadow falls on and no object
    covers, as sorted crop indices. This one set is what the preview and the Mac both draw; it is in no
    footprint, no rule and no plan."""
    cast = set()
    for o in objs:
        cast.update(cast_pixels(o, ref, dx, dy))
    if cast:
        for o in objs:
            cast.difference_update(o.solid)
    return sorted(cast)


def compose(ref, objs, cond):
    """The crop for `cond` with `objs` drawn on it: bytearray of cw*ch RGB."""
    order = draw_order(objs)
    owner, drawn = paint(order, ref.cw * ref.ch)
    out = bytearray(ref.crop(cond.name))
    if cond.cast_alpha:
        keep = 256 - cond.cast_alpha
        for i in cast_shown(ref, order, cond.cast_dx, cond.cast_dy):
            j = 3 * i
            for c in range(3):
                out[j + c] = (out[j + c] * keep) >> 8
    sa, sr = cond.shadow_alpha, cond.shadow_rgb
    done = set()
    for ds in drawn:
        for i in ds:
            if owner[i] == 0 and i not in done:
                done.add(i)
                j = 3 * i
                for c in range(3):
                    out[j + c] = (out[j + c] * (256 - sa) + sr[c] * sa) >> 8
    cw = ref.cw
    Ls, lut, V = cond.lights, cond.lut, cond.veil_rgb
    va, vig = cond.veil_alpha, ref.vignette
    cache = {}
    for k, o in enumerate(order, 1):
        face, glow = o.face, o.glow
        for i, rgb in o.solid.items():
            if owner[i] != k:
                continue
            y = i // cw
            x = i - y * cw
            f = face.get(i, 0)
            e = cond.lamps if i in glow else 0
            key = (rgb, f, e, va[y], vig[y >> 4][x >> 4])
            px = cache.get(key)
            if px is None:
                L = Ls[f]
                px = bytes(shade(rgb[c], L[c], lut[c], key[3], V[c], key[4], e) for c in range(3))
                cache[key] = px
            out[3 * i:3 * i + 3] = px
    return out


def sheet(ref, objs):
    """The four conditions in a 2x2 grid. Returns (width, height, pixel bytes)."""
    panels = [compose(ref, objs, c) for c in ref.conditions]
    stride = 3 * ref.cw
    raw = bytearray()
    for top in (0, 2):
        a, b = panels[top], panels[top + 1]
        for y in range(ref.ch):
            raw += a[y * stride:(y + 1) * stride]
            raw += b[y * stride:(y + 1) * stride]
    return 2 * ref.cw, 2 * ref.ch, bytes(raw), panels


def zoom_window(ref, focus):
    if focus is None or focus.bbox is None:
        return None
    x0, y0, x1, y1 = focus.bbox
    x0, y0 = max(0, x0 - ZOOM_MARGIN), max(0, y0 - ZOOM_MARGIN)
    x1, y1 = min(ref.cw - 1, x1 + ZOOM_MARGIN), min(ref.ch - 1, y1 + ZOOM_MARGIN)
    if x1 - x0 + 1 > ZOOM_MAX_W:
        mid = (x0 + x1) >> 1
        x0 = max(0, min(ref.cw - ZOOM_MAX_W, mid - (ZOOM_MAX_W >> 1)))
        x1 = x0 + ZOOM_MAX_W - 1
    if y1 - y0 + 1 > ZOOM_MAX_H:
        y1 = min(ref.ch - 1, focus.bbox[3] + ZOOM_MARGIN)
        y0 = max(0, y1 - ZOOM_MAX_H + 1)
    return x0, y0, x1, y1


def zoom(ref, panel, focus, objs=()):
    """x4 of the first condition around `focus`: keep-out tinted red (over objects too, so a
    conflict shows), and on open ground the dry band's edges in green and the deck's edge in cyan.
    Returns (width, height, pixel bytes) or None."""
    win = zoom_window(ref, focus)
    if win is None:
        return None
    solid = set()
    for o in objs:
        solid.update(o.solid)
    x0, y0, x1, y1 = win
    cw, ch = ref.cw, ref.ch
    keep, deck = ref.keepout, ref.deck_mask
    rows = []
    for y in range(y0, y1 + 1):
        Y = y + ref.cy
        line = bytearray()
        for x in range(x0, x1 + 1):
            i = y * cw + x
            r, g, b = panel[3 * i], panel[3 * i + 1], panel[3 * i + 2]
            X = x + ref.cx
            band = ref.dry(X)
            if keep[i]:
                r, g, b = (r + 255) >> 1, g >> 1, b >> 1
            elif i in solid:
                pass
            elif band is not None and (Y == band[0] or Y == band[1]):
                r, g, b = r >> 1, (g + 255) >> 1, b >> 1
            elif deck[i] and (x == 0 or x == cw - 1 or y == 0 or y == ch - 1 or not deck[i - 1] or not deck[i + 1]
                              or not deck[i - cw] or not deck[i + cw]):
                r, g, b = r >> 1, (g + 255) >> 1, (b + 255) >> 1
            line += bytes((r, g, b)) * ZOOM
        rows.append(bytes(line) * ZOOM)
    return (x1 - x0 + 1) * ZOOM, (y1 - y0 + 1) * ZOOM, b"".join(rows)


def pixels_sha256(pixels):
    return hashlib.sha256(pixels).hexdigest()


def write(path, width, height, pixels):
    with open(path, "wb") as f:
        f.write(write_png(width, height, pixels, 2))


def plan(ref, objs):
    """What the Mac draws, in order: for each live object its solid pixels (frame x, y, albedo,
    is_label, shown, face, glows) and the shadow pixels it casts (frame x, y, shown)."""
    order = draw_order(objs)
    owner, drawn = paint(order, ref.cw * ref.ch)
    cw = ref.cw
    out = []
    for k, o in enumerate(order, 1):
        solid = [(i % cw + ref.cx, i // cw + ref.cy, o.solid[i], i in o.label, owner[i] == k, o.face.get(i, 0), i in o.glow)
                 for i in sorted(o.solid)]
        shadow = [(i % cw + ref.cx, i // cw + ref.cy, owner[i] == 0) for i in drawn[k - 1]]
        out.append({"id": o.id, "seq": o.seq, "ground_y": o.ground_y, "solid": solid, "shadow": shadow})
    return out


def plan_sha256(ref, objs):
    """A digest of every footprint pixel, the draw order and who covers whom."""
    h = hashlib.sha256()
    for o in plan(ref, objs):
        h.update(("%s %d %d\n" % (o["id"], o["seq"], o["ground_y"])).encode("ascii"))
        for x, y, rgb, lab, shown, face, glow in o["solid"]:
            h.update(("%d %d %d %d %d %d %d %d %d\n" % (x, y, rgb[0], rgb[1], rgb[2], lab, shown, face, glow)).encode("ascii"))
        for x, y, shown in o["shadow"]:
            h.update(("s %d %d %d\n" % (x, y, shown)).encode("ascii"))
    return h.hexdigest()
