"""The hillside's animals (v3 phase 3, part 2): the sheep, a fox, hares and crows, and what hides them.

The animals are drawn in front(), over the near scenery, every minute. What can stand in front of them is
recorded while the hill is drawn (land.py, hillside.py): a mask of each field wall, garden wall stretch,
gatepost, the open gate's leaf, the wicket, the shed, the hives, the rocks and the gorse, with the frame
row of its foot in every column. An animal whose feet stand higher in the frame than a thing's foot in a
column (so farther away) is hidden there by it. Animals already drawn in a frame hide the ones behind
them in the same way, whatever order they are drawn in. Perched animals stand on top of what they perch
on, so it never hides them; their feet are put on the topmost stone or rail of the mask itself.

Where each animal is, and what it is doing, comes from the day's schedule (events.py): from the date and
the minute alone, so a given minute always renders the same. Each is lit by the frame's own sun, moon, sky
and lamps (lit()) and drawn as a small sprite: one dark edge round its silhouette, a lit top and a darker
underside, in the manner of a hand-drawn game background.
"""
import math
from collections import OrderedDict
from contextlib import contextmanager

import numpy as np
from PIL import Image, ImageDraw

from core import KF, SS, Layer, hull, normalize
from events import WALL_LINES, vnoise

LIFE_M = 76.0        # pixels per metre for the animals at a perspective of 1 on a 3840-wide frame
OCC = OrderedDict()  # (W, H, date, wall stages) -> the standing things recorded while the hill was drawn


# ------------------------------------------------------------- occlusion --
class Occluders:
    """Records the masks of the near scenery that stands up from the ground, group by group, while it is
    drawn: each group a coverage mask and, for every column of it, the frame row of its foot."""

    def __init__(self, W, H):
        self.x0, self.y0 = 0, int(0.55 * H)
        self.x1, self.y1 = int(math.ceil(0.5 * W)), H
        self.groups = []      # (name, x0, y0, mask (h, w) float32 0..1, foot row per column (w,) float32)
        self.cur = None

    def begin(self, name, foot):
        self.end()
        img = Image.new("L", ((self.x1 - self.x0) * SS, (self.y1 - self.y0) * SS), 0)
        self.cur = (name, [(float(p[0]), float(p[1])) for p in foot], img, ImageDraw.Draw(img))

    def end(self):
        if self.cur is None:
            return
        name, foot, img, _ = self.cur
        self.cur = None
        bb = img.getbbox()
        if not bb:
            return
        c0, r0 = bb[0] // SS, bb[1] // SS
        c1, r1 = -(-bb[2] // SS), -(-bb[3] // SS)
        crop = img.crop((c0 * SS, r0 * SS, c1 * SS, r1 * SS)).resize((c1 - c0, r1 - r0), Image.BOX)
        mask = np.asarray(crop, np.float32) / 255
        fx, fy = zip(*sorted(foot))
        xs = np.arange(c0, c1, dtype=np.float64) + self.x0 + 0.5
        self.groups.append((name, c0 + self.x0, r0 + self.y0, mask, np.interp(xs, fx, fy).astype(np.float32)))

    def P(self, x, y):
        return ((x - self.x0) * SS, (y - self.y0) * SS)

    def poly(self, pts, a=1.0):
        if self.cur and a >= 0.9 and len(pts) >= 3:
            self.cur[3].polygon([self.P(*p) for p in pts], fill=255)

    def ellipse(self, cx, cy, rx, ry, a=1.0):
        if self.cur and a >= 0.9:
            (x0, y0), (x1, y1) = self.P(cx - rx, cy - ry), self.P(cx + rx, cy + ry)
            if x1 > x0 and y1 > y0:
                self.cur[3].ellipse([x0, y0, x1, y1], fill=255)

    def line(self, pts, w, a=1.0):
        if self.cur and a >= 0.9:
            self.cur[3].line([self.P(*p) for p in pts], fill=255, width=max(1, int(round(w * SS))), joint="curve")


class Tee:
    """A drawing layer that also hands what is drawn on it to an Occluders recorder (its current group).
    The layer itself gets exactly the calls it would have had."""

    def __init__(self, base, rec):
        self.base, self.rec = base, rec

    def poly(self, pts, col, a=1.0):
        pts = list(pts)
        self.base.poly(pts, col, a)
        self.rec.poly(pts, a)

    def ellipse(self, cx, cy, rx, ry, col, a=1.0):
        self.base.ellipse(cx, cy, rx, ry, col, a)
        self.rec.ellipse(cx, cy, rx, ry, a)

    def line(self, pts, col, w, a=1.0):
        pts = list(pts)
        self.base.line(pts, col, w, a)
        self.rec.line(pts, w, a)

    def __getattr__(self, k):
        return getattr(self.base, k)


class Null:
    """A layer that draws nothing."""

    def poly(self, *a, **k):
        pass

    ellipse = line = text = blit = poly


def stages_key(day):
    st = getattr(day, "wall_stages", None) or {}
    return tuple(sorted((k, float(getattr(v, "courses", 4.0))) for k, v in st.items()))


# ---------------------------------------------------------------- sprites --
class Sprite:
    """A small drawing in metres (forward of the feet, up from the ground) for an animal standing at frame
    point (x, y) and facing f (+1 right, -1 left), M pixels to the metre. Shapes can be turned about a point
    while they are added; drawn as one silhouette: a dark edge round the whole, then the fills in order."""

    def __init__(self, x, y, M, f):
        self.x, self.y, self.M, self.f = float(x), float(y), float(M), 1 if f >= 0 else -1
        self.ops = []
        self.turns = []

    @contextmanager
    def turn(self, deg, px, py):
        self.turns.append((math.radians(deg), px, py))
        try:
            yield
        finally:
            self.turns.pop()

    def pt(self, dx, dy):
        for a, px, py in reversed(self.turns):
            c, s = math.cos(a), math.sin(a)
            dx, dy = px + (dx - px) * c - (dy - py) * s, py + (dx - px) * s + (dy - py) * c
        return (self.x + self.f * dx * self.M, self.y - dy * self.M)

    def poly(self, pts, col, edge=True):
        self.ops.append(("p", [self.pt(*p) for p in pts], None, np.asarray(col, np.float32), edge))

    def ell(self, cx, cy, rx, ry, col, edge=True, n=20):
        t = np.linspace(0, 2 * math.pi, n, endpoint=False)
        self.poly(list(zip(cx + rx * np.cos(t), cy + ry * np.sin(t))), col, edge)

    def blob(self, cx, cy, a, b, col, edge=True, p=2.5, n=28):
        """A rounded box: the superellipse |x/a|^p + |y/b|^p = 1 (p = 2 is an ellipse)."""
        t = np.linspace(0, 2 * math.pi, n, endpoint=False)
        c, s = np.cos(t), np.sin(t)
        self.poly(list(zip(cx + a * np.sign(c) * np.abs(c) ** (2 / p), cy + b * np.sign(s) * np.abs(s) ** (2 / p))), col, edge)

    def limb(self, pts, w, col, edge=True):
        """A stroke w metres wide through pts."""
        self.ops.append(("l", [self.pt(*p) for p in pts], w * self.M, np.asarray(col, np.float32), edge))

    def bushy(self, pts, widths, col, edge=True):
        """A tapering shape (a tail, an ear) along pts, half as wide as widths (metres) at each."""
        P = np.array([self.pt(*p) for p in pts], np.float64)
        d = np.gradient(P, axis=0)
        d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-9
        nrm = np.stack([-d[:, 1], d[:, 0]], 1) * (np.asarray(widths, np.float64) * self.M)[:, None]
        outline = [tuple(p) for p in P + nrm] + [tuple(p) for p in (P - nrm)[::-1]]
        self.ops.append(("p", outline, None, np.asarray(col, np.float32), edge))

    def draw(self, L, ink_w):
        for kind, pts, w, col, edge in self.ops:      # the edge round the whole silhouette
            if edge is False:
                continue
            ink = col * 0.42 if edge is True else np.asarray(edge, np.float32)
            if kind == "l":
                L.line(pts, ink, w + 2 * ink_w)
            else:
                L.poly(pts, ink)
                L.line(pts + [pts[0]], ink, 2 * ink_w)
        for kind, pts, w, col, edge in self.ops:
            if kind == "l":
                L.line(pts, col, w)
            else:
                L.poly(pts, col)


def ring(cx, cy, rx, ry, a0, a1, n=12):
    """Points on an ellipse from angle a0 to a1 (degrees, counterclockwise, 0 = forward)."""
    t = np.radians(np.linspace(a0, a1, n))
    return list(zip(cx + rx * np.cos(t), cy + ry * np.sin(t)))


# a sheep's, a fox's and a hare's head in profile, about its pivot at the top of the neck, facing forward
SHEEP_HEAD = [(-0.05, 0.07), (0.06, 0.095), (0.15, 0.065), (0.27, -0.035), (0.255, -0.085), (0.21, -0.1),
              (0.07, -0.08), (-0.06, -0.04)]
SHEEP_EAR = [(0.0, 0.055), (-0.15, 0.04), (-0.16, 0.005), (-0.01, 0.015)]
FOX_HEAD = [(-0.05, 0.045), (0.05, 0.075), (0.12, 0.05), (0.23, -0.012), (0.228, -0.03), (0.15, -0.046),
            (0.03, -0.052), (-0.05, -0.03)]
FOX_CHEEK = [(0.05, -0.012), (0.22, -0.026), (0.14, -0.044), (0.03, -0.05)]
FOX_EARS = ([(0.0, 0.05), (0.055, 0.068), (0.022, 0.16)], [(-0.03, 0.045), (0.01, 0.058), (-0.022, 0.145)])


class FaunaMixin:
    # ----------------------------------------------------------- occlusion --
    def occl_key(self):
        return (self.W, self.H, self.day.date.toordinal(), stages_key(self.day))

    def occl_recorder(self):
        """A recorder for hill() to fill as it draws, or None when this day and frame size are recorded
        already (or the frame is a shore reference frame, which draws no animals)."""
        if self.reference or self.occl_key() in OCC:
            return None
        return Occluders(self.W, self.H)

    def occl_store(self, rec):
        rec.end()
        OCC[self.occl_key()] = rec.groups
        while len(OCC) > 2:
            OCC.popitem(last=False)
        return rec.groups

    def occluders(self):
        """The standing things of the near scenery as recorded when the hill was drawn in this process. If
        it was not (a test, or a frame drawn without its near scenery), they are drawn again on their own:
        the hillside's exactly, the field walls with the same outline but stones of their own."""
        groups = OCC.get(self.occl_key())
        if groups is not None:
            return groups
        rec, null = Occluders(self.W, self.H), Null()
        H = self.H
        persp = lambda y: 0.35 + 1.3 * np.clip((np.asarray(y) / H - 0.6) / 0.4, 0, 1)
        r2 = np.random.default_rng(32)
        for name, seg in zip(("wall-upper", "wall-lower"), self.field_walls()):
            rec.begin(name, seg)
            self.wall_body(Tee(null, rec), null, seg, persp, r2, null)
        self.hillside(Tee(null, rec), null, null, null, persp)
        return self.occl_store(rec)

    def occl_top(self, name, x, half=1.5):
        """The frame row of the top of standing thing `name` round column x (its topmost stone or rail
        there), or None where there is nothing."""
        for nm, gx0, gy0, mask, _ in self.occluders():
            if nm != name:
                continue
            c0 = max(0, int(math.floor(x - half)) - gx0)
            c1 = min(mask.shape[1], int(math.ceil(x + half)) - gx0 + 1)
            if c1 <= c0:
                continue
            rows = np.nonzero((mask[:, c0:c1] > 0.5).any(1))[0]
            if len(rows):
                return gy0 + float(rows[0])
        return None

    def life_allow(self, L, depth, xc=None):
        """1 where an animal whose feet stand at frame row `depth` may show in layer L, 0 where something
        nearer (standing scenery, or an animal already drawn) hides it; None if nothing does. Each thing is
        nearer or farther as a whole, by its foot under the animal's own column xc (the middle of L if not
        given), so a wall that slopes across the screen never cuts an animal in two."""
        allow = None
        xc = (L.x0 + L.x1) / 2 if xc is None else xc
        for _, gx0, gy0, mask, foot in list(self.occluders()) + self.life_drawn():
            h, w = mask.shape
            x0, x1 = max(L.x0, gx0), min(L.x1, gx0 + w)
            y0, y1 = max(L.y0, gy0), min(L.y1, gy0 + h)
            if x0 >= x1 or y0 >= y1:
                continue
            if not foot[min(w - 1, max(0, int(xc) - gx0))] > depth + 0.5:
                continue
            if allow is None:
                allow = np.ones((L.y1 - L.y0, L.x1 - L.x0), np.float32)
            allow[y0 - L.y0:y1 - L.y0, x0 - L.x0:x1 - L.x0] *= 1 - mask[y0 - gy0:y1 - gy0, x0 - gx0:x1 - gx0]
        return allow

    def life_drawn(self):
        if getattr(self, "_life", None) is None:
            self._life = []
        return self._life

    def life_put(self, L, depth, solid=True, xc=None):
        """Composite an animal's layer (standing at column xc, row depth), hidden where something nearer
        stands; a solid one then hides the animals behind it in turn."""
        if not L.ok:
            return
        rgb, al = L.arrays()
        allow = self.life_allow(L, depth, xc)
        if allow is not None:
            al = al * allow[..., None]
        self.over(L.y0, L.y1, L.x0, L.x1, rgb, al)
        if solid:
            self.life_drawn().append(("life", L.x0, L.y0, al[..., 0], np.full(L.x1 - L.x0, depth, np.float32)))

    def life_crowded(self, L, frac):
        """Whether animals already drawn this frame cover more than frac of layer L's box."""
        if not L.ok:
            return False
        cov = 0.0
        for _, gx0, gy0, mask, _ in self.life_drawn():
            h, w = mask.shape
            x0, x1 = max(L.x0, gx0), min(L.x1, gx0 + w)
            y0, y1 = max(L.y0, gy0), min(L.y1, gy0 + h)
            if x0 < x1 and y0 < y1:
                cov += float(mask[y0 - gy0:y1 - gy0, x0 - gx0:x1 - gx0].sum())
        return cov > frac * (L.x1 - L.x0) * (L.y1 - L.y0)

    def life_shadow(self, x, y, w, h, depth, k=1.0):
        """The soft shadow under an animal standing at (x, y), w px long and h tall, and the shadow the sun
        casts from it across the grass."""
        S = Layer(self, x - w - 3 * h, y - 2 * h, x + w + 3 * h, y + 2 * h)
        col = np.array((18, 24, 20), np.float32) * (self.amb + 0.25)
        if self.sun_alt > 1 and self.sun_str > 0.05:
            cot = min(1 / math.tan(math.radians(self.sun_alt)), 3.0)
            sx, sy = math.sin(math.radians(self.sun_az)) * cot * h * 0.85, -math.cos(math.radians(self.sun_az)) * cot * KF * h * 0.85
            t = np.linspace(0, 2 * math.pi, 16, endpoint=False)
            foot = [(x + 0.45 * w * math.cos(a), y + 0.11 * w * math.sin(a)) for a in t]
            pts = foot + [(px + sx, py + sy) for px, py in foot]
            S.poly(hull(pts), col, a=0.34 * self.sun_str * k)
        S.ellipse(x, y + 0.02 * w, 0.52 * w, 0.12 * w, col, a=0.42 * k)
        self.life_put(S, depth, solid=False, xc=x)

    # -------------------------------------------------------------- light --
    def tones(self, alb, x, y):
        """An albedo lit four ways for a sprite: its body (facing you, a little up), its top (the sky's and
        a high sun's side), its underside, and its rim on the side the sun (or moon) is."""
        lv = self.sunv if self.sun_alt > -3 else self.moonv
        rim = normalize([lv[0] * 0.8, lv[1] * 0.8 + 0.25, 0.45])
        return (self.lit(alb, (0, 0.8, 0.55), x, y), self.lit(alb, (0, 0.25, 0.97), x, y),
                self.lit(alb, (0, 0.55, -0.6), x, y), self.lit(alb, rim, x, y))

    def ink_w(self):
        return max(0.5, 0.85 * self.s)

    def sun_side(self, f):
        """Which way (in a sprite's own forward metres) the sun or moon side is: -1 behind, +1 ahead."""
        lv = self.sunv if self.sun_alt > -3 else self.moonv
        screen = -1 if lv[0] > 0 else 1          # east is to the left of the frame
        return screen * f

    def rim_off(self, f, k):
        """An offset k metres long toward the sun or moon as a sprite facing f sees it: (forward, up). The
        light is beyond the scene (the view faces south), so the rim it puts on things is mostly on top."""
        lv = self.sunv if self.sun_alt > -3 else self.moonv
        dx, dy = -float(lv[0]) * f, max(0.0, float(lv[2])) + 0.6 * max(0.0, -float(lv[1]))
        n = math.hypot(dx, dy) + 1e-6
        return k * dx / n, k * dy / n

    # ---------------------------------------------------------------- sheep --
    def sheep(self):
        """The flock, big enough to read: blackface ewes in their fleece (shorn in early summer), lambs in
        spring; side on, or walking toward you or away; lying down in the fold at night."""
        se = self.season
        W, H, s = self.W, self.H, self.s
        for i, (xn, yn, f, grazing, size, view) in enumerate(self.day.events.sheep(self.t, lambs=se.lambs)):
            x, y = xn * W, yn * H
            lamb = size < 1
            M = LIFE_M * s * self.persp(y) * size
            standing = self.sun_alt > -4 or lamb
            shorn = se.shorn and not lamb
            fleece = np.array((242, 238, 228) if lamb else (206, 200, 186) if shorn else (228, 223, 210), np.float32)
            v = view if standing else "lying"
            side = v in ("side", "lying")
            self.life_shadow(x, y, (1.15 if side else 0.72) * M, (0.8 if standing else 0.45) * M, y)
            L = Layer(self, x - 0.95 * M, y - 1.05 * M, x + 0.95 * M, y + 0.12 * M)
            sp = Sprite(x, y, M, f if side else 1)
            self.draw_sheep(sp, i, fleece, v, grazing, shorn, x, y)
            sp.draw(L, self.ink_w())
            self.life_put(L, y, xc=x)

    def draw_sheep(self, sp, i, fleece, view, grazing, shorn, x, y):
        lv = self.sunv if self.sun_alt > -3 else self.moonv
        rim_n = normalize([lv[0] * 0.8, lv[1] * 0.8 + 0.25, 0.45])
        b, t, u = (self.lit(fleece, n, x, y) for n in ((0, 0.5, 0.87), (0, -0.2, 0.98), (0, 0.8, -0.25)))
        m_ = 0.5 * (b + t)
        rim = self.lit(fleece, rim_n, x, y)
        fb, ft, _, _ = self.tones((50, 44, 42), x, y)
        legc = self.lit((82, 72, 64), (0, 0.8, 0.55), x, y)
        r = np.random.default_rng(700 + i)
        bw = 0.9 if shorn else 1.0
        if view in ("side", "lying"):
            lying = view == "lying"
            a_, b_ = 0.6 * bw, 0.31 * bw
            cy = 0.27 if lying else 0.25 + b_
            ox, oy = self.rim_off(sp.f, 0.06)
            if not lying:                                    # thin legs, the far pair darker
                for lx, far in ((0.44, True), (-0.36, True), (0.36, False), (-0.44, False)):
                    sp.limb([(lx, cy - b_ + 0.06), (lx + 0.015, 0.0)], 0.046, legc * (0.7 if far else 1.0), edge=False)
            # the fleece: a woolly barrel, scalloped along its back, lit on the side the light comes from
            xs = np.linspace(-0.47, 0.43, 7) * bw
            bumps = [(xx, cy + b_ * (0.84 - 0.25 * (abs(xx) / a_) ** 3), (0.085 + 0.02 * r.random()) * bw) for xx in xs]
            bumps += [(-a_ * 0.88, cy + 0.04, 0.17 * bw), (a_ * 0.86, cy + 0.03, 0.15 * bw)]
            bumps += [(xx, cy - b_ * 0.88, 0.06 * bw) for xx in np.linspace(-0.25, 0.25, 3) * bw]
            sp.blob(ox, cy + oy, a_, b_, rim, p=2.2)
            for bx_, by_, rr in bumps[:9]:
                sp.ell(bx_ + ox, by_ + oy, rr, rr * 0.88, rim)
            # lit from above: the back and its scallops in the light, shading down to the belly
            sp.blob(0.0, cy, a_, b_, b, p=2.2)
            for k, (bx_, by_, rr) in enumerate(bumps):
                sp.ell(bx_, by_, rr, rr * 0.88, t if k < 7 else m_ if k < 9 else b)
            sp.blob(0.0, cy + 0.05 * bw, a_ * 0.98, b_ * 0.86, 0.67 * b + 0.33 * t, edge=False, p=2.4)
            sp.blob(0.0, cy + 0.1 * bw, a_ * 0.92, b_ * 0.68, 0.33 * b + 0.67 * t, edge=False, p=2.3)
            sp.blob(0.0, cy + 0.16 * bw, a_ * 0.8, b_ * 0.48, t, edge=False, p=2.2)
            sp.blob(0.0, cy - 0.22 * bw, a_ * 0.8, b_ * 0.22, 0.5 * (u + b), edge=False, p=2.2)
            self.sheep_curls(sp, r, 0.0, cy, a_, b_, b, m_)
            # the neck and head, in front of the fleece
            hk = 1.25            # the head a little larger than life, so it reads
            if grazing and not lying:
                sp.limb([(0.42, cy), (0.6, 0.28)], 0.2, 0.5 * (b + m_))
                pv, ang = (0.62, 0.26), -62
            elif lying:
                sp.limb([(0.4, cy + 0.06), (0.56, cy + 0.12)], 0.2, m_)
                pv, ang = (0.6, cy + 0.14), (-14 if i % 2 else -40)
            else:
                sp.limb([(0.4, cy + 0.08), (0.6, cy + 0.14)], 0.2, m_)
                pv, ang = (0.64, cy + 0.15), -18
            with sp.turn(ang, *pv):
                P = lambda pts: [(pv[0] + dx * hk, pv[1] + dy * hk) for dx, dy in pts]
                sp.poly(P(SHEEP_HEAD), fb)
                sp.poly(P([(0.05, 0.085), (0.15, 0.06), (0.255, -0.03), (0.14, 0.03)]), ft, edge=False)   # the light down its nose
                sp.ell(pv[0] + 0.105 * hk, pv[1] + 0.02 * hk, 0.016, 0.011, fb * 0.35, edge=False)
                sp.poly(P(SHEEP_EAR), fb * 0.85)
                sp.poly(P([(-0.02, 0.045), (-0.12, 0.03), (-0.12, 0.018), (-0.02, 0.03)]), ft * 0.8, edge=False)
        else:
            front = view == "front"
            a_, b_ = 0.36 * bw, 0.32 * bw
            cy = 0.25 + b_
            ox, oy = self.rim_off(1, 0.05)
            for lx, far in ((-0.1, True), (0.1, True), (-0.16, False), (0.16, False)):
                sp.limb([(lx, cy - b_ + 0.06), (lx * 1.05, 0.0)], 0.048, legc * (0.7 if far else 1.0), edge=False)
            if not front and not grazing:                    # its head beyond the fleece
                for e in (-1, 1):
                    sp.poly([(e * 0.05, cy + 0.34), (e * 0.2, cy + 0.33), (e * 0.2, cy + 0.3), (e * 0.05, cy + 0.3)], fb * 0.8)
                sp.ell(0.0, cy + 0.32, 0.08, 0.07, fb)
            sp.blob(ox, cy + oy, a_, b_, rim, p=2.2)
            sp.blob(0.0, cy, a_, b_, b, p=2.2)
            for xx in np.linspace(-0.26, 0.26, 4) * bw:
                rr = (0.09 + 0.02 * r.random()) * bw
                sp.ell(xx, cy + b_ * 0.82, rr, rr * 0.85, t)
            sp.blob(0.0, cy + 0.05 * bw, a_ * 0.97, b_ * 0.86, 0.67 * b + 0.33 * t, edge=False, p=2.4)
            sp.blob(0.0, cy + 0.1 * bw, a_ * 0.9, b_ * 0.68, 0.33 * b + 0.67 * t, edge=False, p=2.3)
            sp.blob(0.0, cy + 0.16 * bw, a_ * 0.76, b_ * 0.48, t, edge=False, p=2.2)
            sp.blob(0.0, cy - 0.22 * bw, a_ * 0.78, b_ * 0.22, 0.5 * (u + b), edge=False)
            self.sheep_curls(sp, r, 0.0, cy, a_, b_, b, m_)
            if front:                                        # its face toward you, the ears out sideways
                dy = -0.36 if grazing else 0.0
                for e in (-1, 1):
                    sp.poly([(e * 0.07, cy + 0.2 + dy), (e * 0.22, cy + 0.18 + dy), (e * 0.22, cy + 0.14 + dy), (e * 0.07, cy + 0.15 + dy)], fb * 0.85)
                sp.poly([(-0.11, cy + 0.25 + dy), (0.11, cy + 0.25 + dy), (0.09, cy + 0.02 + dy), (0.05, cy - 0.1 + dy),
                         (-0.05, cy - 0.1 + dy), (-0.09, cy + 0.02 + dy)], fb)
                sp.poly([(-0.03, cy + 0.16 + dy), (0.03, cy + 0.16 + dy), (0.022, cy - 0.05 + dy), (-0.022, cy - 0.05 + dy)], ft, edge=False)
                sp.ell(0.0, cy + 0.24 + dy, 0.085, 0.045, b, edge=False)     # the wool on its poll
            else:
                sp.ell(0.0, cy - 0.04, 0.04, 0.08, 0.5 * (b + m_), edge=False)        # its tail

    def sheep_curls(self, sp, r, cx, cy, rx, ry, b, m_):
        """Curls of wool drawn into the fleece: short arcs a shade darker, for whoever looks closely."""
        c = 0.6 * m_ + 0.4 * b
        for _ in range(9):
            dx, dy = r.uniform(-0.75, 0.75), r.uniform(-0.35, 0.65)
            px, py, w = cx + dx * rx, cy + dy * ry, r.uniform(0.04, 0.06)
            sp.limb([(px - w, py), (px - w * 0.3, py + w * 0.5), (px + w * 0.4, py + w * 0.3)], 0.014, c, edge=False)

    # ------------------------------------------------------------------ fox --
    def fox(self):
        """The fox, when the day's schedule has it out: trotting, listening for voles, pouncing, standing to
        look at you, sitting, or sitting by the garden's wicket gate with its back to you."""
        if self.reference:
            return
        st = self.day.events.fox_at(self.m)
        if st is None or self.mysteries().prints:
            return
        xn, yn, pose, f, look = st
        W, H, s = self.W, self.H, self.s
        x, y = xn * W, yn * H
        M = LIFE_M * s * self.persp(y) * 1.1
        sitting = pose in ("sit", "wall")
        self.life_shadow(x, y, (0.5 if sitting else 0.85) * M, 0.4 * M, y, k=0.7 if pose == "pounce" else 1.0)
        L = Layer(self, x - 0.8 * M, y - 1.15 * M, x + 0.8 * M, y + 0.12 * M)
        sp = Sprite(x, y - (0.2 * M if pose == "pounce" else 0.0), M, f)
        self.draw_fox(sp, pose, look, x, y)
        sp.draw(L, self.ink_w())
        self.life_put(L, y, xc=x)

    def draw_fox(self, sp, pose, look, x, y):
        b, t, u, rim = self.tones((182, 92, 44), x, y)
        pb, pt, _, _ = self.tones((232, 224, 208), x, y)
        db, dt_, _, _ = self.tones((44, 32, 28), x, y)
        sun = self.sun_side(sp.f)

        def tail(pts, w):
            n = len(pts)
            sp.bushy(pts, w, b)
            k = max(2, n // 4)
            sp.bushy(pts[-k:], [w[-1] * 1.02] * k, pb, edge=False)      # its white tip

        def head(px, py, ang, front=False):
            if front:                    # turned to look at you
                with sp.turn(0, px, py):
                    for e in (-1, 1):
                        sp.poly([(px + e * 0.03, py + 0.05), (px + e * 0.085, py + 0.04), (px + e * 0.075, py + 0.15)], db)
                    sp.poly([(px - 0.075, py + 0.055), (px + 0.075, py + 0.055), (px + 0.03, py - 0.04), (px, py - 0.075),
                             (px - 0.03, py - 0.04)], b)
                    for e in (-1, 1):
                        sp.poly([(px + e * 0.07, py + 0.02), (px + e * 0.012, py - 0.02), (px + e * 0.01, py - 0.065), (px + e * 0.03, py - 0.045)],
                                pb, edge=False)
                    sp.ell(px, py - 0.07, 0.012, 0.01, db, edge=False)
                    for e in (-1, 1):
                        sp.ell(px + e * 0.03, py + 0.012, 0.009, 0.006, db, edge=False)
                return
            with sp.turn(ang, px, py):
                sp.poly([(px + dx, py + dy) for dx, dy in FOX_EARS[1]], db * 0.8)
                sp.poly([(px + dx, py + dy) for dx, dy in FOX_HEAD], b)
                sp.poly([(px + dx, py + dy) for dx, dy in FOX_CHEEK], pb, edge=False)
                sp.poly([(px + dx, py + dy) for dx, dy in FOX_EARS[0]], db)
                sp.ell(px + 0.228, py - 0.021, 0.012, 0.01, db, edge=False)
                sp.ell(px + 0.125, py + 0.02, 0.01, 0.006, db, edge=False)

        def leg(top, foot, w, far):
            c = (b * 0.7, db * 0.75) if far else (b, db)
            sp.limb([top, foot], w, c[0])
            mid = (top[0] + (foot[0] - top[0]) * 0.55, top[1] + (foot[1] - top[1]) * 0.55)
            sp.limb([mid, foot], w * 0.95, c[1], edge=False)          # its black stockings

        if pose in ("trot", "stand", "pounce"):
            ph = 1 if self.m % 2 else -1
            sw = 0.07 if pose == "trot" else 0.0
            if pose == "pounce":
                with sp.turn(-38, 0.0, 0.33):
                    tail([(-0.24, 0.35), (-0.42, 0.42), (-0.6, 0.47)], [0.045, 0.075, 0.05])
                    leg((-0.18, 0.3), (-0.42, 0.27), 0.045, True)
                    leg((0.17, 0.3), (0.4, 0.2), 0.04, True)
                    sp.ell(sun * 0.02, 0.335, 0.27, 0.1, rim)
                    sp.ell(0.0, 0.33, 0.27, 0.1, b)
                    sp.ell(0.2, 0.31, 0.075, 0.085, pb)
                    sp.ell(0.0, 0.27, 0.21, 0.04, u, edge=False)
                    leg((0.15, 0.3), (0.42, 0.24), 0.04, False)
                    leg((-0.2, 0.3), (-0.44, 0.3), 0.045, False)
                    head(0.24, 0.42, -18)
                return
            leg((0.16, 0.28), (0.16 - sw * ph, 0.0), 0.04, True)
            leg((-0.19, 0.28), (-0.19 + sw * ph, 0.0), 0.045, True)
            tail([(-0.24, 0.33), (-0.42, 0.29), (-0.6, 0.23), (-0.68, 0.2)], [0.04, 0.07, 0.065, 0.04])
            sp.ell(sun * 0.02, 0.335, 0.27, 0.1, rim)
            sp.ell(0.0, 0.33, 0.27, 0.1, b)
            sp.ell(-0.17, 0.31, 0.12, 0.11, b)
            sp.ell(0.15, 0.33, 0.1, 0.11, b)
            sp.ell(0.21, 0.31, 0.07, 0.085, pb)
            sp.ell(-0.02, 0.27, 0.22, 0.035, u, edge=False)
            sp.ell(-0.03, 0.4, 0.2, 0.03, t, edge=False)
            leg((0.14, 0.28), (0.14 + sw * ph, 0.0), 0.04, False)
            leg((-0.21, 0.28), (-0.21 - sw * ph, 0.0), 0.045, False)
            if pose == "stand" and look:
                head(0.25, 0.44, 0, front=True)
            else:
                head(0.24, 0.42, -4 if pose == "trot" else 6)
        elif pose == "mouse":                # crouched, nose down, ears forward, listening
            tail([(-0.22, 0.22), (-0.42, 0.13), (-0.6, 0.07), (-0.68, 0.05)], [0.04, 0.07, 0.06, 0.04])
            leg((0.15, 0.22), (0.2, 0.0), 0.04, True)
            sp.limb([(-0.16, 0.16), (-0.2, 0.0)], 0.05, b * 0.7)
            with sp.turn(-12, 0.0, 0.24):
                sp.ell(sun * 0.02, 0.245, 0.25, 0.095, rim)
                sp.ell(0.0, 0.24, 0.25, 0.095, b)
                sp.ell(0.19, 0.22, 0.07, 0.08, pb)
                sp.ell(0.0, 0.185, 0.2, 0.03, u, edge=False)
            sp.ell(-0.16, 0.17, 0.12, 0.11, b)
            leg((0.13, 0.2), (0.17, 0.0), 0.04, False)
            head(0.25, 0.25, -42)
        elif pose == "sit":
            tail([(-0.16, 0.05), (-0.04, 0.025), (0.08, 0.02), (0.16, 0.03)], [0.045, 0.06, 0.055, 0.035])
            leg((0.05, 0.18), (0.06, 0.0), 0.035, True)
            sp.ell(-0.07, 0.12, 0.14, 0.12, b)
            sp.ell(sun * 0.02, 0.26, 0.105, 0.17, rim)
            sp.ell(0.03, 0.25, 0.105, 0.17, b)
            sp.ell(0.09, 0.28, 0.05, 0.1, pb)
            sp.ell(-0.05, 0.3, 0.05, 0.1, t, edge=False)
            leg((0.1, 0.18), (0.11, 0.0), 0.035, False)
            head(0.08, 0.43, 4, front=look)
        else:                                # "wall": sitting by the wicket, its back to you
            tail([(0.02, 0.03), (0.2, 0.02), (0.34, 0.035), (0.42, 0.05)], [0.05, 0.065, 0.06, 0.04])
            sp.ell(0.0, 0.11, 0.15, 0.11, b)
            sp.ell(sun * 0.02, 0.25, 0.11, 0.16, rim)
            sp.ell(0.0, 0.25, 0.11, 0.16, b)
            sp.ell(-sun * 0.02, 0.29, 0.07, 0.1, t, edge=False)
            sp.ell(0.0, 0.43, 0.075, 0.065, b)
            for e in (-1, 1):
                sp.poly([(e * 0.065, 0.45), (e * 0.015, 0.475), (e * 0.055, 0.56)], db)

    # ---------------------------------------------------------------- hares --
    def hares(self):
        """Hares out in the fields at dawn and dusk: grazing hunched, sitting up, upright and alert, loping
        to a new place; in March and April a pair may stand up and box."""
        if self.reference:
            return
        W, H, s = self.W, self.H, self.s
        for xn, yn, pose, f, which, var in sorted(self.day.events.hares_at(self.m), key=lambda h: h[1]):
            x, y = xn * W, yn * H
            M = LIFE_M * s * self.persp(y) * 1.3
            self.life_shadow(x, y, 0.5 * M, 0.28 * M, y)
            L = Layer(self, x - 0.55 * M, y - 0.8 * M, x + 0.55 * M, y + 0.1 * M)
            sp = Sprite(x, y, M, f)
            self.draw_hare(sp, pose, var, which, x, y)
            sp.draw(L, self.ink_w())
            self.life_put(L, y, xc=x)

    def draw_hare(self, sp, pose, var, which, x, y):
        b, t, u, rim = self.tones((176, 130, 82), x, y)
        pb, _, _, _ = self.tones((224, 210, 186), x, y)
        db, _, _, _ = self.tones((34, 28, 26), x, y)
        sun = self.sun_side(sp.f)

        def ears(root, tip, tip2):
            for k, tp in enumerate((tip2, tip)):
                c = b * (0.75 if k == 0 else 1.0)
                mid = ((root[0] + tp[0]) / 2, (root[1] + tp[1]) / 2)
                sp.bushy([root, mid, tp], [0.017, 0.024, 0.011], c * 0.62)          # its edge, so it shows on the body
                sp.bushy([root, mid, tp], [0.011, 0.017, 0.007], c, edge=False)
                sp.bushy([(root[0] + (tp[0] - root[0]) * 0.7, root[1] + (tp[1] - root[1]) * 0.7), tp], [0.019, 0.011], db, edge=False)

        def scut(px, py):
            sp.ell(px, py, 0.04, 0.035, pb)
            sp.ell(px + 0.005, py + 0.015, 0.03, 0.018, db, edge=False)

        if pose == "graze":                  # hunched over the grass, hips high, ears back
            sp.limb([(0.15, 0.08), (0.19, 0.0)], 0.03, b * 0.75)
            scut(-0.25, 0.17)
            sp.ell(-0.12, 0.13, 0.14, 0.13, b)
            with sp.turn(-16, 0.0, 0.14):
                sp.ell(sun * 0.015, 0.145, 0.24, 0.1, rim)
                sp.ell(0.0, 0.14, 0.24, 0.1, b)
                sp.ell(-0.03, 0.19, 0.17, 0.035, t, edge=False)
                sp.ell(0.0, 0.09, 0.18, 0.03, u, edge=False)
            with sp.turn(-35, 0.19, 0.1):
                sp.ell(0.24, 0.1, 0.075, 0.055, b)
                sp.ell(0.3, 0.09, 0.03, 0.03, b)
            sp.ell(0.21, 0.1, 0.011, 0.008, db, edge=False)
            ears((0.19, 0.14), (0.04, 0.27), (0.07, 0.25))
        elif pose in ("sit", "up", "box"):
            upright = pose != "sit"
            rear = 0.03 if pose == "box" and var == 0 else 0.0
            lean = {"sit": 45, "up": 75, "box": 70 + 8 * var}[pose]
            scut(-0.18, 0.06 + rear)
            sp.ell(-0.06, 0.1 + rear, 0.14, 0.11, b)
            with sp.turn(lean, -0.02, 0.12 + rear):
                sp.ell(0.12 + sun * 0.015, 0.12 + rear, 0.17, 0.095, rim)
                sp.ell(0.12, 0.12 + rear, 0.17, 0.095, b)
                sp.ell(0.12, 0.05 + rear, 0.12, 0.035, pb, edge=False)
            hx, hy = (0.04, 0.42 + rear) if upright else (0.13, 0.3)
            if pose == "box":                 # forelegs up, sparring
                sp.limb([(hx + 0.0, hy - 0.12), (hx + 0.12, hy - 0.05 + 0.03 * var)], 0.028, b * 0.8)
                sp.limb([(hx + 0.01, hy - 0.14), (hx + 0.14, hy - 0.1 - 0.02 * var)], 0.028, b)
            elif upright:
                sp.limb([(hx + 0.02, hy - 0.13), (hx + 0.05, hy - 0.24)], 0.026, b)
            else:
                sp.limb([(0.12, 0.17), (0.13, 0.0)], 0.03, b)
            with sp.turn(-12 if upright else -18, hx, hy):
                sp.ell(hx, hy, 0.075, 0.055, b)
                sp.ell(hx + 0.07, hy - 0.012, 0.03, 0.03, b)
                sp.ell(hx + 0.02, hy + 0.012, 0.012, 0.009, db, edge=False)
            back = pose == "box" and var == 2
            ears((hx - 0.01, hy + 0.04), (hx - (0.12 if back else 0.04), hy + (0.17 if back else 0.2)),
                 (hx - (0.1 if back else 0.07), hy + (0.15 if back else 0.18)))
        else:                                 # loping: stretched out, forelegs reaching, hind legs thrusting
            sp.limb([(0.16, 0.16), (0.33, 0.07)], 0.028, b * 0.75)
            sp.limb([(-0.14, 0.16), (-0.36, 0.08)], 0.05, b * 0.75)
            scut(-0.29, 0.25)
            with sp.turn(4, 0.0, 0.2):
                sp.ell(sun * 0.015, 0.205, 0.3, 0.088, rim)
                sp.ell(0.0, 0.2, 0.3, 0.088, b)
                sp.ell(-0.14, 0.19, 0.12, 0.1, b)
                sp.ell(-0.02, 0.24, 0.22, 0.03, t, edge=False)
                sp.ell(0.0, 0.15, 0.22, 0.028, u, edge=False)
            sp.limb([(0.18, 0.15), (0.36, 0.1)], 0.028, b)
            sp.limb([(-0.16, 0.15), (-0.39, 0.12)], 0.05, b)
            sp.ell(0.3, 0.25, 0.075, 0.055, b)
            sp.ell(0.33, 0.255, 0.011, 0.008, db, edge=False)
            ears((0.27, 0.28), (0.1, 0.35), (0.13, 0.33))

    # ---------------------------------------------------------------- crows --
    def crow_spot(self, site, u, j):
        """Where crow j of a visit stands: (x, feet y, the row it stands in front of, px per metre), or None."""
        W, H, s = self.W, self.H, self.s
        gap = lambda yy: 0.55 * LIFE_M * s * self.persp(yy)       # birds keep about half a metre apart
        if site in ("wall-upper", "wall-lower"):
            seg = WALL_LINES[0 if site == "wall-upper" else 1] * (W, H)
            i = int((0.06 + 0.86 * u) * (len(seg) - 1))
            x = float(seg[i, 0]) + j * gap(seg[i, 1])
            yf = float(np.interp(x, seg[:, 0], seg[:, 1]))
            top = self.occl_top(site, x)
        elif site in ("garden-front", "garden-front-east", "garden-right"):
            a0, a1, b0, b1 = {"garden-front": (0.04, 0.74, 0.0, 0.0), "garden-front-east": (0.92, 0.985, 0.0, 0.0),
                              "garden-right": (1.0, 1.0, 0.06, 0.62)}[site]
            p0, p1 = self.hs_g(a0, b0), self.hs_g(a1, b1)
            ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) + 1e-6
            w = min(1.0, u + j * gap(p0[1]) / ln)
            x, yf = p0[0] + (p1[0] - p0[0]) * w, p0[1] + (p1[1] - p0[1]) * w
            top = self.occl_top(site, x)
        elif site == "gate-leaf":
            g = self.hs_gate_geom()
            ln = math.hypot(g["ex"] - g["hx"], g["ey"] - g["hy"]) + 1e-6
            w = min(0.92, 0.25 + 0.55 * u + j * gap(g["hy"]) / ln)
            x, yf = g["hx"] + (g["ex"] - g["hx"]) * w, g["hy"] + (g["ey"] - g["hy"]) * w
            top = self.occl_top(site, x)
        elif site in ("hinge-post", "latch-post"):
            g = self.hs_gate_geom()
            px, py = (g["hx"], g["hy"]) if site == "hinge-post" else (g["lx"], g["ly"])
            wall_h = g["per"](py)
            x, yf = px + 0.25 * wall_h * 0.24, py
            top = py - wall_h * 1.5 - 0.1 * wall_h * 0.24
        else:
            return None
        if top is None:
            return None
        return x, top + 0.5, yf + 1.5, LIFE_M * s * self.persp(yf) * 1.15

    def crows(self):
        """Crows by day: on the field walls' and the garden's coping, the gateposts and the open gate's top
        bar, now and then one walking the grass beside a sheep. Each sits a while, looks about, hunches,
        calls, preens, and goes."""
        if self.reference:
            return
        birds = self.day.events.crows_at(self.m)
        if not birds:
            return
        W, H, s = self.W, self.H, self.s
        spot, _, since, seeds, _ = self.day.events.cat_at(self.m)
        cat = self.cat_spot(spot, seeds) if spot == "wall" and since >= 5 else None
        flock = None
        for site, u, j, pose, f, key in birds:
            if site == "ground":
                if flock is None:
                    flock = self.day.events.sheep(self.t, lambs=self.season.lambs)
                if not flock or self.sun_alt < -4:
                    continue
                sx, sy, sf, _, size, _ = flock[int(u * len(flock)) % len(flock)]
                sy *= H
                Ms = LIFE_M * s * self.persp(sy)
                side = 1 if key[0] % 2 else -1
                x = sx * W + side * (0.95 + 0.25 * vnoise(key[0] * 31 + 7, self.m, 6)) * Ms
                y = sy + 0.05 * Ms * vnoise(key[0] * 31 + 8, self.m, 7)
                feet, depth, M = y, y, Ms * 1.15
                self.life_shadow(x, y, 0.3 * M, 0.2 * M, depth)
            else:
                at = self.crow_spot(site, u, j)
                if at is None:
                    continue
                x, feet, depth, M = at
                if cat and site == "wall-upper" and abs(x - cat[0]) < 2.5 * M:
                    continue
            L = Layer(self, x - 0.4 * M, feet - 0.45 * M, x + 0.4 * M, feet + 0.06 * M)
            if site != "ground" and self.life_crowded(L, 0.04):
                continue          # an animal stands right there (a sheep behind the gate): it has flown off
            sp = Sprite(x, feet, M, f)
            self.draw_crow(sp, pose, x, feet)
            sp.draw(L, self.ink_w() * 0.8)
            self.life_put(L, depth, xc=x)

    def draw_crow(self, sp, pose, x, y):
        b, t, u, _ = self.tones((24, 24, 28), x, y)
        sheen = self.lit((44, 46, 56), (0, 0.3, 0.95), x, y)
        beak = self.lit((40, 38, 40), (0, 0.6, 0.7), x, y)
        if pose in ("walk", "peck"):
            sp.limb([(-0.02, 0.075), (-0.045, 0.0)], 0.014, b)
            sp.limb([(0.03, 0.075), (0.05, 0.0)], 0.014, b)
            tilt = -18 if pose == "peck" else 8
            with sp.turn(tilt, 0.0, 0.12):
                sp.poly([(-0.08, 0.14), (-0.08, 0.11), (-0.27, 0.115), (-0.27, 0.14)], b)
                sp.ell(0.0, 0.125, 0.135, 0.062, b)
                sp.ell(-0.03, 0.14, 0.11, 0.035, sheen, edge=False)
            if pose == "peck":
                sp.ell(0.15, 0.06, 0.05, 0.048, b)
                sp.poly([(0.17, 0.08), (0.2, 0.06), (0.215, 0.0)], beak)
            else:
                sp.ell(0.14, 0.18, 0.05, 0.048, b)
                sp.poly([(0.17, 0.2), (0.175, 0.17), (0.25, 0.18)], beak)
            return
        sp.limb([(-0.005, 0.05), (0.0, 0.0)], 0.013, b)
        sp.limb([(0.025, 0.05), (0.03, 0.0)], 0.013, b)
        lean = {"perch": 30, "look": 30, "hunch": 44, "caw": 16, "preen": 34}[pose]
        sp.poly([(-0.07, 0.11), (-0.035, 0.08), (-0.2 if pose != "caw" else -0.24, -0.01 if pose != "caw" else 0.03),
                 (-0.225 if pose != "caw" else -0.255, 0.012 if pose != "caw" else 0.055)], b)
        fat = 1.25 if pose == "hunch" else 1.0
        with sp.turn(lean, 0.0, 0.12):
            sp.ell(0.0, 0.125, 0.125, 0.068 * fat, b)
            sp.ell(-0.04, 0.145, 0.085, 0.03, sheen, edge=False)
        if pose == "hunch":
            hx, hy = 0.065, 0.205
        elif pose == "caw":
            hx, hy = 0.13, 0.2
        elif pose == "preen":
            hx, hy = 0.065, 0.17
        else:
            hx, hy = 0.095, 0.225
        sp.ell(hx, hy, 0.052, 0.05, b)
        sp.ell(hx - 0.01, hy + 0.025, 0.03, 0.015, sheen, edge=False)
        if pose == "look":           # its head turned back over its shoulder
            sp.poly([(hx - 0.03, hy + 0.02), (hx - 0.03, hy - 0.012), (hx - 0.11, hy + 0.004)], beak)
        elif pose == "caw":          # calling: the bill open
            sp.poly([(hx + 0.035, hy + 0.018), (hx + 0.04, hy - 0.002), (hx + 0.12, hy + 0.02)], beak)
            sp.poly([(hx + 0.035, hy - 0.006), (hx + 0.04, hy - 0.022), (hx + 0.11, hy - 0.04)], beak)
        elif pose == "preen":        # its bill down in its breast
            sp.poly([(hx + 0.02, hy - 0.02), (hx + 0.045, hy - 0.01), (hx + 0.035, hy - 0.085)], beak)
        else:
            sp.poly([(hx + 0.035, hy + 0.02), (hx + 0.04, hy - 0.012), (hx + 0.12, hy + 0.002)], beak)
