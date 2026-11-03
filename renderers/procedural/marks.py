"""The marks the story leaves on the land (v3 phase 5, part 1), drawn from the Day's story (story.py).

Near scenery, drawn with the hill (into its albedo and normal layers, so the scene's own light falls on
them): the stones of a fallen length of wall lying in the grass, then sorted into a pile by the gap with a
builder's line across it while the wall is rebuilt; the spade left standing where the digging stopped; a
branch blown down from the tree lying under it, and the logs it was cut into stacked against the shed;
snow drifted against the lee of the walls. In front, every minute, like the washed-up bottle: driftwood on
the shingle.

No people, ever: only what they leave. Every mark has its own generator, seeded by the event it belongs
to ([story.STORY + 20 + kind, ...]), so it lies in the same place every day it is shown, and drawing it moves no
other draw. With nothing in the story (and in reference mode) nothing here draws at all.
"""
import math

import numpy as np

from core import CANOPY, KF, Layer, hill_edge_y, hull, shore_band, sm
from hillside import BED_A, BEDS, GATE_GAP, OBJ, SHED_AB, enc
from season import Season
from story import rng
from tree import GREENS, LEAF, skeleton

STONE = np.array((128, 124, 114), np.float32)
LICHEN = np.array((150, 150, 96), np.float32)
WOOD = np.array((84, 70, 56), np.float32)          # bark of the tree's limbs (tree.py)
FRESH = np.array((206, 184, 140), np.float32)      # new-split wood
SNOW = np.array((236, 240, 246), np.float32)
DRIFTWOOD = np.array((178, 172, 160), np.float32)  # bleached by the sea
DRIFT_X = ((0.605, 0.685), (0.885, 0.962))         # where driftwood lies along the shore (frame widths)
DRIFT_FULL = 25.0                                  # cm m/s of blown snow that makes a full drift


def ground(e, n, m):
    """A ground vector (east, north, metres) on the screen at m px per metre: west is right, north is down."""
    return -e * m, n * m * KF


class MarksMixin:
    def story(self):
        return getattr(self.day, "story", None)

    # ------------------------------------------------------------- walls --
    def mk_site(self, site):
        """The foot line of wall stretch `site` and its height factor (as the hill draws it)."""
        if site == "garden-front":
            return np.array([self.hs_g(a_, 0.0) for a_ in np.linspace(0.0, GATE_GAP[0], 40)], np.float64), 1.25
        return self.field_walls()[0 if site == "wall-upper" else 1], 1.0

    def mk_wall(self):
        """The stones of the fallen length: lying in the grass where they fell, then in a pile by the gap
        while it is rebuilt (fewer as they go back in), and the builder's line across the gap."""
        st = self.story()
        w = st.wall if st else None
        if not w:
            return
        seg, height = self.mk_site(w["site"])
        d = np.cumsum(np.r_[0, np.linalg.norm(np.diff(seg, axis=0), axis=1)])
        span = w["half"] * self.W / d[-1]
        t0, t1 = w["mid"] - span, w["mid"] + span

        def at(t):
            u = t * d[-1]
            x, y = float(np.interp(u, d, seg[:, 0])), float(np.interp(u, d, seg[:, 1]))
            i = min(int(np.searchsorted(d, u)), len(seg) - 2)
            dx, dy = seg[i + 1] - seg[i]
            ln = math.hypot(dx, dy) + 1e-6
            dx, dy = dx / ln, dy / ln
            nx, ny = (-dy, dx) if dx > 0 else (dy, -dx)        # toward you
            return x, y, dx, dy, nx, ny

        persp = lambda y: 0.35 + 1.3 * min(1.0, max(0.0, (y / self.H - 0.6) / 0.4))
        s = self.s
        r = rng(20, w["seed"])
        # every stone that came down, wherever it is shown: (t along the wall, how far out, size, colour)
        fallen = []
        for i in range(22):
            t = t0 + (t1 - t0) * float(np.clip(r.normal(0.5, 0.25), -0.05, 1.05))
            fallen.append((t, r.uniform(0.0, 1.0) ** 1.6, r.normal(0, 0.15), r.uniform(0.75, 1.2), r.uniform(0.66, 1.25),
                           r.random(), i))
        pile = []
        for row, cnt in enumerate((8, 7, 5, 3, 1)):          # a heap, its biggest stones at the bottom
            for j in range(cnt):
                pile.append((row, ((j + 0.5) / cnt - 0.5) * (1 - 0.16 * row) + r.normal(0, 0.03), r.uniform(0.85, 1.2) * (1.1 - 0.08 * row),
                             r.uniform(0.66, 1.25), r.random(), 100 + len(pile), r.normal(0, 0.25)))

        def stone(x, y, rx, tone, k, i):
            c = STONE * tone
            if k < 0.18:
                c = c * 0.7 + LICHEN * 0.3
            self.hs_rock(x, y, rx, rx * 0.68, rng(21, w["seed"], i), c, shadow=0.3)

        if w["state"] == "fallen":
            for t, out, along, size, tone, k, i in sorted(fallen, key=lambda q: q[1]):
                x, y, dx, dy, nx, ny = at(t)
                p = persp(y)
                hgt = 26 * s * p * height
                rx = 7.0 * s * p * size * height        # within a metre or so of its foot, most of them close
                stone(x + nx * (0.15 + out) * hgt * 0.75 + dx * along * hgt, y + ny * (0.15 + out) * hgt * 0.75, rx, tone, k, i)
        elif w["pile"] > 0:
            x, y, dx, dy, nx, ny = at(w["mid"])
            p = persp(y)
            hgt = 26 * s * p * height
            cx, cy = x + nx * 1.15 * hgt - dx * 0.2 * hgt, y + ny * 1.15 * hgt
            wide = (t1 - t0) * d[-1] * 0.62
            show = int(round(len(pile) * w["pile"]))
            st_h = 8.5 * s * p * height
            for row, f, size, tone, k, i, deep in pile[:show]:
                stone(cx + f * wide, cy + deep * st_h * 0.5 - row * st_h * 0.85, st_h * size, tone * 1.08, k + 0.1, i)
        if w.get("line"):                  # two pins at the gap's ends and a line at the course being laid
            lvl = min(4, int(math.floor(w["built"])) + 1)
            top = (0.0, 0.37, 0.67, 0.9, 1.0)[lvl]
            pins = []
            for t in (t0 - 0.004, t1 + 0.004):
                x, y, dx, dy, nx, ny = at(t)
                p = persp(y)
                hgt = 26 * s * p * height
                px_, py_ = x + nx * 0.22 * hgt, y + ny * 0.22 * hgt
                self.hs_line([(px_, py_), (px_, py_ - 1.25 * hgt)], FRESH * 0.85, (0.0, 0.9, 0.3), max(1.5, 1.6 * s * p))
                pins.append((px_, py_ - top * hgt))
            self.hs_line(pins, (250, 246, 228), (0.0, 0.7, 0.7), max(1.0, 0.75 * s), obj=False)

    def mk_drift(self, A, N, X, seg, persp, height, gap):
        """Snow drifted against the near side of a wall where the wind that brought it blew from beyond the
        wall, as deep as the blown snow and the snow still lying allow (wall_body's own geometry)."""
        st = self.story()
        if not st or self.wx.snow_cover < 0.05:
            return
        e, n = getattr(st, "drift", None) or (0.0, 0.0)
        wx, m = self.day.wx, min(self.m, 1439)
        if m >= 0:                                    # today's snow, blown so far
            sf = np.asarray(wx.snowfall_cmph[:m + 1], np.float64) / 60
            ws = np.maximum(np.asarray(wx.wind_ms[:m + 1], np.float64) - 3.0, 0.0)
            th = np.radians(np.asarray(wx.wind_dir_deg[:m + 1], np.float64))
            e += float((sf * ws * -np.sin(th)).sum())
            n += float((sf * ws * -np.cos(th)).sum())
        S = math.hypot(e, n)
        k = min(1.0, math.sqrt(S / DRIFT_FULL)) * sm(0.05, 0.6, self.wx.snow_cover)
        if k < 0.04:
            return
        wsx, wsy = -e / S, n / S * KF                 # downwind on the screen
        wl = math.hypot(wsx, wsy) + 1e-9
        wsx, wsy = wsx / wl, wsy / wl
        seg = np.asarray(seg, np.float64)
        lv, _ = self.wall_gap(gap, seg)
        gf = np.ones(len(seg)) if lv is None else np.interp(lv, range(5), (0.0, 0.37, 0.67, 0.9, 1.0))
        tops, toes, s = [], [], self.s
        # deeper here, shallower there along the wall, where the wind eddied (the same for this wall every time)
        ph = rng(25, int(seg[0][0] * 10 / self.s), int(seg[0][1] * 10 / self.s)).uniform(0, 2 * math.pi, 3)
        dl = np.cumsum(np.r_[0, np.linalg.norm(np.diff(seg, axis=0), axis=1)]) / (60 * s)
        wob = 0.72 + 0.28 * (np.sin(dl * 1.3 + ph[0]) * 0.5 + np.sin(dl * 2.9 + ph[1]) * 0.3 + np.sin(dl * 6.1 + ph[2]) * 0.2)
        dirs = np.gradient(seg, axis=0)
        dirs /= np.linalg.norm(dirs, axis=1, keepdims=True) + 1e-6
        nn = len(seg)
        for i, ((x, y), (dx, dy)) in enumerate(zip(seg, dirs)):
            nx, ny = (-dy, dx) if dx > 0 else (dy, -dx)
            lee = max(0.0, nx * wsx + ny * wsy)
            end = min(1.0, min(i, nn - 1 - i) / 4.0)             # tapering out at the wall's ends
            hgt = 26 * s * float(persp(y)) * height
            h = 0.38 * hgt * k * sm(0.1, 0.6, lee) * end * (0.45 + 0.55 * float(gf[i])) * float(wob[i])
            tops.append((x, y - h))
            toes.append((x + nx * h * 1.4 + wsx * h * 0.4, y + ny * h * 1.4 + max(0.0, wsy) * h * 0.4))
        if max(y - ty for (x, y), (_, ty) in zip(seg, tops)) < 0.8 * s:
            return
        # a smooth bank: its upper half leaning toward you against the wall, its lower half running out into
        # the lying snow at the ground's own slope, so it shows as the wall's foot buried, not as a new shape
        mids = [((tx + fx) / 2, (ty + fy) / 2) for (tx, ty), (fx, fy) in zip(tops, toes)]
        low = mids + toes[::-1]
        A.poly(low, SNOW)
        N.poly(low, enc((0.0, -0.2, 0.98)))
        high = tops + mids[::-1]
        A.poly(high, SNOW)
        N.poly(high, enc((0.0, 0.3, 0.95)))
        crest = [(x, y + 0.5 * s) for x, y in tops]
        A.line(crest, SNOW, max(1.0, 1.0 * s))
        N.line(crest, enc((0.0, 0.05, 1.0)), max(1.0, 1.0 * s))
        X.poly(tops + toes[::-1], OBJ)

    # ------------------------------------------------------------ garden --
    def mk_spade(self, k):
        """The spade, left standing in bed k where the digging stopped (only while that bed is being dug)."""
        st = self.story()
        sp = st.spade if st else None
        if not sp or sp[0] != k:
            return
        b0, b1 = BEDS[k]
        a0, a1 = BED_A
        x, y = self.hs_g(a0 + (a1 - a0) * min(0.97, sp[1] + 0.01), b0 + (b1 - b0) * 0.55, 0.12)
        m = self.hs_m(y)
        lean = 0.12 * m
        top = (x + lean, y - 0.86 * m)
        self.hs_face([(x - 0.07 * m, y + 0.02 * m), (x + 0.07 * m, y + 0.02 * m), (x + 0.075 * m + lean * 0.12, y - 0.1 * m),
                      (x - 0.065 * m + lean * 0.12, y - 0.1 * m)], (96, 98, 102), (0.0, 0.8, 0.5))       # the blade's top, in the soil
        self.hs_line([(x + lean * 0.1, y - 0.08 * m), top], (150, 118, 80), (0.3, 0.7, 0.6), max(1.0, 0.035 * m))
        self.hs_line([(top[0] - 0.07 * m, top[1]), (top[0] + 0.07 * m, top[1])], (128, 100, 70), (0.0, 0.6, 0.8), max(1.0, 0.035 * m))
        self.hs_cast_line((x, y), (x, y), 0, 0.86 * m, 0.035 * m)

    def mk_logs(self):
        """Logs from the cleared branches, stacked against the shed's gable, cut ends toward you."""
        st = self.story()
        n = st.logs if st else 0
        if n <= 0:
            return
        g = self.hs_g
        a1 = SHED_AB[1]
        r = rng(22, 0)
        slots = []
        for row in range(4):
            for j in range(5 - (row + 1) // 2):
                slots.append((row, j, r.uniform(0.85, 1.15), r.normal(0, 0.12), r.uniform(0.85, 1.12)))
        x0, y0 = g(a1 + 0.012, 0.80)
        m = self.hs_m(y0)
        rad = 0.11 * m
        for row, j, size, jit, tone in slots[:min(n, len(slots))]:
            x = x0 + (j * 2.05 + row % 2 + 1) * rad + jit * rad
            y = y0 - (row * 1.7 + 1) * rad
            rr = rad * size
            self.hs_ell(x + rr * 0.25, y - rr * 0.1, rr * 1.05, rr, WOOD * 0.8, (-0.8, 0.3, 0.5))     # its bark, behind
            self.hs_ell(x, y, rr, rr * 0.95, FRESH * tone * 0.92, (0.0, 0.95, 0.3))                   # the cut end
            self.hs_ell(x - rr * 0.1, y + rr * 0.05, rr * 0.35, rr * 0.33, FRESH * tone * 0.78, (0.0, 0.95, 0.3))

    # ------------------------------------------------------------ branch --
    def mk_branch(self):
        """The branch the last gale brought down, lying on the grass under the tree: a limb as thick as an arm
        at its torn end, forking into side branches and a fan of twigs, its leaves (if it fell in leaf)
        wilting from the day it fell. It lies downwind of the trunk, to its left, clear of the bench."""
        st = self.story()
        b = st.branch if st else None
        if not b:
            return
        W, H = self.W, self.H
        r = rng(23, b["seed"])
        th = math.radians(b["wind_from"])
        e, n = -math.sin(th), -math.cos(th)          # downwind
        e = max(e, 0.55)                             # out to the left (east) of the trunk
        ln = math.hypot(e, n)
        e, n = e / ln, n / ln
        bx, by = 0.4285 * W, 0.7125 * H
        m = self.hs_m(by)
        limbs = []                                   # (points, width at the start, at the end, depth), all drawn up front

        def grow(x, y, he, hn, length, w, depth):
            pts, nseg = [(x, y)], 4
            for _ in range(nseg):
                a = r.normal(0, 0.2)
                he, hn = he * math.cos(a) - hn * math.sin(a), hn * math.cos(a) + he * math.sin(a)
                dx, dy = ground(he * length / nseg, hn * length / nseg, m)
                # the side branches it rests on stand up off the grass
                x, y = x + dx, y + dy - r.uniform(0.0, (0.0, 0.7, 0.45, 0.3)[depth]) * length / nseg * m
                pts.append((x, y))
            limbs.append((pts, w, w * 0.4, depth))
            if depth >= 3:
                return
            kids = (5, 3, 4)[depth]
            for _ in range(kids):
                t = r.uniform(0.25, 1.0)
                i = min(nseg - 1, int(t * nseg))
                f = t * nseg - i
                px_ = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f
                py_ = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f
                a = r.uniform(0.35, 1.0) * (1 if r.random() < 0.5 else -1)
                ce, cn = he * math.cos(a) - hn * math.sin(a), hn * math.cos(a) + he * math.sin(a)
                grow(px_, py_, ce, cn, length * r.uniform(0.35, 0.6) * (1.2 - 0.4 * t), w * (0.95 - 0.45 * t) * 0.55, depth + 1)

        grow(bx, by, e, n, r.uniform(2.7, 3.5), 0.2 * m, 0)
        leafy = Season(b["fell"]).leaves
        wilt = min(1.0, b["age"] / 9.0)
        brown = np.array((136, 110, 62), np.float32)
        leaves = [(r.uniform(0, 1), r.normal(0, 0.12), r.normal(0, 0.08), r.uniform(0.8, 1.2), r.uniform(0.8, 1.15),
                   r.integers(0, len(GREENS)), r.normal(0, 0.5), r.normal(0, 0.5)) for _ in range(650)]
        # crushed grass under it, then the limbs, thinnest first, each with its top catching the light
        main = limbs[0][0]
        self._hsA.poly(hull([(x, y + 0.05 * m) for x, y in main] + [(x, y + 0.14 * m) for x, y in main]), (30, 40, 22), a=0.3)
        for pts, w0, w1, depth in sorted(limbs, key=lambda q: -q[3]):
            tone = 0.9 + 0.08 * depth
            for i in range(len(pts) - 1):
                w = max(0.7, w0 + (w1 - w0) * (i + 0.5) / (len(pts) - 1))
                self.hs_line([pts[i], pts[i + 1]], WOOD * tone, (0.0, 0.88, 0.45), w)       # its side, toward you
                if w > 2.2:                          # and its top, where the light (or new snow) lies
                    self.hs_line([(pts[i][0], pts[i][1] - w * 0.32), (pts[i + 1][0], pts[i + 1][1] - w * 0.32)], WOOD * tone * 1.3,
                                 (0.0, 0.3, 0.95), max(1.0, w * 0.25))
        x, y = main[0]                               # the torn butt: pale splintered wood
        w0 = limbs[0][1]
        self.hs_ell(x, y - w0 * 0.1, w0 * 0.45, w0 * 0.55, FRESH, (0.8, 0.4, 0.45))
        for k in range(3):
            self.hs_line([(x - w0 * 0.2, y - w0 * (0.3 - 0.25 * k)), (x + w0 * (0.6 + 0.3 * k), y - w0 * (0.5 - 0.3 * k))], FRESH * 0.92,
                         (0.6, 0.4, 0.7), max(1.0, w0 * 0.18))
        if leafy > 0.15:                             # leaves, as the tree had them, wilting from the day it fell
            tips = [pts for pts, _, _, depth in limbs if depth >= 2]
            keep = leafy * (1 - 0.4 * wilt)
            placed = []
            for u, ox, oy, size, tone, pal, nx_, ny_ in leaves:   # the tree's own leaves, lit each by its own face
                if u > keep or not tips:
                    continue
                pts = tips[int(u * 7919) % len(tips)]
                j = 1 + int(u * 1000) % (len(pts) - 1)
                x, y = pts[j]
                placed.append((y + oy * m, x + ox * m, size, tone, pal, nx_, ny_, (u * 977.0) % math.pi))
            for y, x, size, tone, pal, nx_, ny_, a in sorted(placed):
                col = np.array(GREENS[pal], np.float32) * (1 - wilt) + brown * wilt
                rr = 0.1 * m * size * (1 - 0.3 * wilt)
                ca, sa = math.cos(a), math.sin(a)
                leaf = [(x + rr * (px * ca - py * sa), y + rr * (px * sa + py * ca) * (1 - 0.4 * wilt)) for px, py in LEAF]
                self.hs_face(leaf, col * tone, (nx_, 0.2 + ny_ * 0.6, 0.8))
        self.hs_cast([main[0], main[2], main[-1], (main[-1][0], main[-1][1] - 2)], (0.5 if leafy > 0.15 else 0.3) * m)

    def mk_scar(self, L):
        """Where the branch tore from the tree: pale torn wood on a lower limb of the crown, greying over two
        months (tree.py)."""
        st = self.story()
        age = st.scar if st else None
        if age is None or age > 75:
            return
        W, H, s = self.W, self.H, self.s
        segs, _ = skeleton(W, H)
        ccx, ccy = CANOPY[0] * W, CANOPY[1] * H
        cand = [q for q in segs if 3.0 * s <= q[4] <= 7.0 * s and q[2] < ccx - 40 * s and ccy + 40 * s < q[3] < 0.56 * H]
        if not cand:
            return
        q = cand[len(cand) // 3]
        x, y, w = q[2], q[3], q[4]
        f = 1 - min(1.0, age / 75)
        col = self.lit(FRESH * (0.55 + 0.45 * f) + WOOD * 0.45 * (1 - f), [0.2, 0.7, 0.6], x, y)
        L.ellipse(x, y, w * 0.9, w * 0.7, col)
        L.line([(x - w * 0.6, y + w * 0.2), (x - w * 1.3, y + w * 0.9)], col * 0.92, max(1.0, w * 0.4))

    # --------------------------------------------------------- driftwood --
    def driftwood(self):
        """Driftwood an onshore gale threw up the shingle, lying a little above the day's high water until the
        sea takes it back or it is taken for the fire; hidden by anything standing nearer on the shore."""
        st = self.story()
        pieces = st.driftwood if st else ()
        if not pieces:
            return
        W, H, s = self.W, self.H, self.s
        for p in pieces:
            if p["gone"] is not None and self.m >= p["gone"]:
                continue
            if 0.5 * self.tide >= p["v"] - 0.012:        # the sea is round it
                continue
            r = rng(24, p["seed"])
            lo, hi = DRIFT_X[p["slot"] % 2]
            xn = lo + (hi - lo) * ((p["slot"] >> 1) % 1000) / 1000.0
            xs = np.array([xn - 0.004, xn, xn + 0.004])
            band = shore_band(xs)
            ys = hill_edge_y(xs) + p["v"] * band
            x, y = xn * W, float(ys[1]) * H
            ang = math.atan2(float(ys[2] - ys[0]) * H, 0.008 * W) + r.normal(0, 0.12)
            p_ = 0.35 + 1.3 * min(1.0, max(0.0, (y / H - 0.6) / 0.4))
            mpx = 72.0 * s * p_                               # the hillside's pixels per metre (hillside.MS)
            length = r.uniform(1.0, 1.9) * mpx
            thick = r.uniform(0.09, 0.16) * mpx
            ca, sa = math.cos(ang), math.sin(ang)
            P = lambda u, v: (x + ca * u - sa * v, y + sa * u + ca * v)
            Lr = Layer(self, x - length, y - length * 0.6 - thick * 2, x + length, y + length * 0.6 + thick * 2)
            if not Lr.ok:
                continue
            wet = self.wx.wet
            alb = DRIFTWOOD * (1 - 0.35 * wet) * r.uniform(0.92, 1.05)
            top = self.lit(alb * 1.08, [0.0, 0.3, 0.95], x, y)
            side = self.lit(alb * 0.86, [0.0, 0.85, 0.5], x, y)
            dark = self.lit(alb * 0.5, [0.0, 0.85, 0.5], x, y)
            # its shadow on the stones, then the log: a tapering trunk, a knot or two, a root-plate or a split end
            Lr.poly([P(-length * 0.5, thick * 0.35), P(length * 0.5, thick * 0.25), P(length * 0.48, thick * 0.75),
                     P(-length * 0.5, thick * 0.85)], (18, 18, 20), a=0.45)
            taper = r.uniform(0.55, 0.8)
            body = [P(-length * 0.5, -thick * 0.5), P(length * 0.5, -thick * 0.5 * taper), P(length * 0.5, thick * 0.5 * taper),
                    P(-length * 0.5, thick * 0.5)]
            Lr.poly(body, side)
            Lr.poly([P(-length * 0.5, -thick * 0.5), P(length * 0.5, -thick * 0.5 * taper), P(length * 0.49, -thick * 0.05),
                     P(-length * 0.49, -thick * 0.05)], top)
            for _ in range(int(r.integers(2, 5))):        # cracks along the grain
                u0, v0 = r.uniform(-0.45, 0.3) * length, r.uniform(-0.3, 0.3) * thick
                Lr.line([P(u0, v0), P(u0 + r.uniform(0.1, 0.35) * length, v0 + r.normal(0, 0.05) * thick)], dark, max(1.0, 0.5 * s))
            if r.random() < 0.6:                          # a gnarled root end
                for k in range(int(r.integers(3, 6))):
                    a_ = r.uniform(-2.3, -0.8) if k % 2 else r.uniform(0.8, 2.3)
                    l_ = r.uniform(0.15, 0.4) * length
                    Lr.line([P(-length * 0.48, 0), P(-length * 0.48 - math.cos(a_) * l_ * 0.3, math.sin(a_) * l_ * 0.35)],
                            side * 0.95, max(1.0, thick * 0.3))
            Lr.ellipse(*P(length * 0.5, 0), thick * 0.12, thick * 0.45 * taper, dark)
            Lr.composite(allow=self.shore_allow(Lr, y + thick * 0.5))
