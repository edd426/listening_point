"""The headland: shadows, grass, the path, rocks, flowers, the wall and the shore."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

from core import *  # noqa: F401,F403
import ground
from events import FIELD_WALLS, FIELD_WALL_END
from fauna import Tee

# How strongly the grass's fine structure reads (1 = the first phase-1 look, which Evan found a bit
# distracting): the tufts' light tips against their dark feet, the shade between them, the blades' lean.
TUFT_SHOW = 0.55
TUFT_LIFT = 1.10


def enc(n):
    """A normal as a colour for the normal layer."""
    n = normalize(n)
    return tuple(float(v) for v in (np.asarray(n) + 1) * 127.5)


class LandMixin:
    def casters(self):
        s, W, H = self.s, self.W, self.H
        tw = self.tw
        out = []
        foot = [(tw["cx"] + tw["r"] * math.cos(a), tw["yb"] + tw["r"] * 0.22 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 24)]
        out.append((foot, tw["yb"] - tw["yt"] + tw["r"] * 1.1))
        bx, by = BENCH[0] * W, BENCH[1] * H
        out.append(([(bx - 96 * s, by), (bx + 96 * s, by), (bx + 96 * s, by - 8 * s), (bx - 96 * s, by - 8 * s)], 70 * s))
        lx, ly = LAMP[0] * W, LAMP[1] * H
        out.append(([(lx - 4 * s, ly), (lx + 4 * s, ly), (lx, ly - 3 * s)], LAMP[2] * s))
        tx, ty = TREE_BASE[0] * W, TREE_BASE[1] * H
        out.append(([(tx - 16 * s, ty), (tx + 16 * s, ty), (tx, ty - 5 * s)], ty - (CANOPY[1] * H + CANOPY[3] * s * 0.6)))
        return out

    def shadow_masks(self):
        W, H, s = self.W, self.H, self.s
        q = 4
        sw, sh = W // q + 1, H // q + 1
        sim, aim = Image.new("L", (sw, sh), 0), Image.new("L", (sw, sh), 0)
        ds, da = ImageDraw.Draw(sim), ImageDraw.Draw(aim)
        src = None
        if self.sun_alt > 1:
            src = (self.sun_alt, self.sun_az, 0.82)
        elif self.moon_alt > 4 and self.sun_alt < -6:
            src = (self.moon_alt, self.moon_az, 0.6)
        tw = self.tw
        # contact shadows (ambient occlusion)
        tx, ty = TREE_BASE[0] * W, TREE_BASE[1] * H
        for (cx, cy, rx, ry, v) in [(tw["cx"], tw["yb"] + 4 * s, tw["r"] * 1.15, tw["r"] * 0.2, 150),
                                    (tx, ty, 40 * s, 10 * s, 150), (BENCH[0] * W, BENCH[1] * H, 100 * s, 9 * s, 110),
                                    (LAMP[0] * W, LAMP[1] * H, 14 * s, 4 * s, 120)]:
            da.ellipse([(cx - rx) / q, (cy - ry) / q, (cx + rx) / q, (cy + ry) / q], fill=v)
        if src:
            alt, az, k = src
            cot = min(1 / math.tan(math.radians(alt)), 3.0)
            sx, sy = math.sin(math.radians(az)) * cot, -math.cos(math.radians(az)) * cot * KF
            for foot, h in self.casters():
                pts = foot + [(x + sx * h, y + sy * h) for x, y in foot]
                ds.polygon([(x / q, y / q) for x, y in hull(pts)], fill=int(255 * k))
            # the canopy
            Rx, Ry = CANOPY[2] * s, CANOPY[3] * s
            hc = ty - CANOPY[1] * H
            cx, cy = tx + sx * hc, ty + sy * hc
            rx = Rx * (1 + 0.35 * min(abs(sx), 2))
            ry = Rx * KF * 1.4 * (1 + 0.35 * min(abs(sy) / KF, 2))
            cim = Image.new("L", (sw, sh), 0)
            ImageDraw.Draw(cim).ellipse([(cx - rx) / q, (cy - ry) / q, (cx + rx) / q, (cy + ry) / q], fill=int(255 * k * 0.72))
            can = np.asarray(cim, np.float32) / 255
            dap = fnoise(sh, sw, 1.4, 1.0, 55)
            can *= np.clip(0.7 + 0.4 * dap, 0, 1)
            shade = np.maximum(np.asarray(sim, np.float32) / 255, can)
        else:
            shade = np.zeros((sh, sw), np.float32)
        shade = 0.5 * ndi.gaussian_filter(shade, 1.0) + 0.5 * ndi.gaussian_filter(shade, 3.5)
        ao = ndi.gaussian_filter(np.asarray(aim, np.float32) / 255, 2.5)
        up = lambda a: np.asarray(Image.fromarray(a).resize((W, H), Image.BILINEAR), np.float32)
        return up(shade), up(ao)

    def field_walls(self):
        """The two field walls' foot lines in frame pixels (events.FIELD_WALLS)."""
        W, H = self.W, self.H
        return tuple(self.bezier(*[(x * W, y * H) for x, y in p], 90) for p in FIELD_WALLS)

    def field_wall_end(self):
        """The lower wall's run out of the bottom of the frame (events.FIELD_WALL_END), in frame pixels."""
        return self.bezier(*[(x * self.W, y * self.H) for x, y in FIELD_WALL_END], 30)

    def wall_end(self, A, N, persp, WM):
        """The lower wall's last stretch, from a generator of its own: its stones, and grass at its foot."""
        seg, re_ = self.field_wall_end(), np.random.default_rng(39)
        self.wall_body(A, N, seg, persp, re_, WM)
        return seg, re_

    def bezier(self, p0, p1, p2, p3, n=120):
        t = np.linspace(0, 1, n)[:, None]
        P = [np.array(p) for p in (p0, p1, p2, p3)]
        return (1 - t) ** 3 * P[0] + 3 * (1 - t) ** 2 * t * P[1] + 3 * (1 - t) * t ** 2 * P[2] + t ** 3 * P[3]

    def ribbon(self, pts, w0, w1):
        d = np.gradient(pts, axis=0)
        d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-6
        nrm = np.stack([-d[:, 1], d[:, 0]], 1)
        w = np.linspace(w0, w1, len(pts))[:, None]
        left, right = pts + nrm * w, pts - nrm * w
        return [tuple(p) for p in left] + [tuple(p) for p in right[::-1]]

    # ------------------------------------------------------------ stones --
    def rock(self, A, N, cx, cy, rx, ry, rng, alb, wet=0.0, weed=0.0):
        """An irregular faceted stone, written to the albedo and normal layers so the sun shades it."""
        k = int(rng.integers(7, 11))
        ang = (np.arange(k) + rng.uniform(-0.3, 0.3, k)) / k * 2 * np.pi + rng.uniform(0, 6.28)
        rad = rng.uniform(0.78, 1.0, k)
        outer = [(cx + rx * r_ * math.cos(a_), cy + ry * r_ * math.sin(a_) * (0.8 if math.sin(a_) > 0 else 1.0)) for a_, r_ in zip(ang, rad)]
        tcx, tcy = cx + rng.normal(0, 0.12) * rx, cy - 0.32 * ry
        top = rng.uniform(0.35, 0.55)
        inner = [(tcx + top * (x - cx), tcy + top * 0.8 * (y - cy)) for x, y in outer]
        alb = np.asarray(alb, np.float32) * (1 - 0.45 * wet)
        A.ellipse(cx, cy + 0.55 * ry, rx * 1.05, ry * 0.45, (20, 22, 18), a=0.45)
        A.poly(outer, alb * 0.75)
        N.poly(outer, enc((0, 0.85, 0.25)))
        for i in range(k):
            j = (i + 1) % k
            am = (ang[i] + ang[j] + (2 * np.pi if j == 0 else 0)) / 2
            n = (-math.cos(am) * 0.72, math.sin(am) * 0.72, 0.6)
            facet = [outer[i], outer[j], inner[j], inner[i]]
            A.poly(facet, alb * rng.uniform(0.86, 1.1))
            N.poly(facet, enc(n))
        A.poly(inner, alb * 1.06)
        N.poly(inner, enc((rng.normal(0, 0.12), 0.22 + rng.normal(0, 0.1), 0.95)))
        if weed > 0:   # wrack on the lower, wetter side
            for _ in range(int(3 + 4 * weed)):
                a_ = rng.uniform(0.2, 2.9)
                A.ellipse(cx + rx * 0.8 * math.cos(a_), cy + ry * 0.55 * math.sin(a_), rx * 0.3, ry * 0.18, (48, 52, 26), a=0.75 * weed)

    def wall_draws(self, seg, d, r, persp):
        """Make the draws the first wall made from the hill's shared generator, in the same order, and
        nothing else, so everything drawn after the walls (the shore's grass among it) keeps its place."""
        s = self.s
        for row in range(4):
            u = r.uniform(0, 8) * s
            while u < d[-1]:
                y = np.interp(u, d, seg[:, 1])
                sw_ = r.uniform(7, 13) * s * persp(y)
                r.uniform(0.75, 0.95)
                for _ in range(6):
                    r.normal(0, 0.05)
                    r.normal(0, 0.06)
                r.uniform(0.72, 1.18)
                r.random()
                u += sw_ * r.uniform(0.9, 1.08)
        for u in np.arange(0, d[-1], 9 * s):
            r.uniform(0.85, 1.15)

    def wall(self, A, N, seg, r, persp, r2, WM):
        """A dry-stone wall along a curve: three courses of stones, big footings to small, each its own
        shade with a lit top and dark joints, under a row of upright coping stones. WM gets its outline."""
        d = np.cumsum(np.r_[0, np.linalg.norm(np.diff(seg, axis=0), axis=1)])
        self.wall_draws(seg, d, r, persp)
        self.wall_body(A, N, seg, persp, r2, WM)

    def wall_body(self, A, N, seg, persp, r2, WM, courses=None, height=1.0, X=None):
        """The stones of a wall along seg, from generator r2. courses (0..4: three courses, then the
        coping; None = finished) builds a wall only so far, a fraction of a course along the wall from its
        start, with the same stones at every stage; height scales it; X (if given) marks it as built."""
        s = self.s
        d = np.cumsum(np.r_[0, np.linalg.norm(np.diff(seg, axis=0), axis=1)])
        dirs = np.gradient(seg, axis=0)
        dirs /= np.linalg.norm(dirs, axis=1, keepdims=True) + 1e-6
        full = courses is None
        laid = lambda row, u: full or courses >= row + 1 or (courses > row and u < (courses - row) * d[-1])
        top_f = 1.0 if full else (0.0, 0.37, 0.67, 0.9, 1.0)[int(min(4, max(0, math.floor(courses))))]
        # the dark body of the wall, seen in the joints between the stones
        if top_f > 0:
            top = [(x, y - 26 * s * persp(y) * height * top_f) for x, y in seg]
            A.poly([tuple(p) for p in seg] + top[::-1], (30, 29, 27))
            N.poly([tuple(p) for p in seg] + top[::-1], enc((0, 0.9, 0.3)))
            body = [tuple(p) for p in seg] + [(x, y - 31 * s * persp(y) * height * top_f) for x, y in seg][::-1]
            WM.poly(body, (255, 255, 255))
            if X is not None:
                X.poly(body, (0, 0, 255))

        def at(u):
            i = min(int(np.searchsorted(d, u)), len(seg) - 1)
            x, y = np.interp(u, d, seg[:, 0]), np.interp(u, d, seg[:, 1])
            dx, dy = dirs[i]
            nx, ny = (-dy, dx) if dx > 0 else (dy, -dx)
            return x, y, dx, dy, nx, ny

        stone = np.array([128, 124, 114], np.float32)
        lichen, moss = np.array([150, 150, 96], np.float32), np.array([78, 98, 54], np.float32)
        corners = ((-0.47, 0.06), (-0.5, 0.62), (-0.42, 0.95), (0.4, 0.97), (0.5, 0.66), (0.46, 0.05))
        for row, (f0, f1) in enumerate(((0.0, 0.37), (0.37, 0.67), (0.67, 0.9))):
            u = r2.uniform(0, 12) * s
            while u < d[-1]:
                x, y, dx, dy, nx, ny = at(u)
                hgt = 26 * s * persp(y) * height
                sw_ = r2.uniform(9, 17) * s * persp(y) * (1.12 - 0.12 * row)
                ch = (f1 - f0) * hgt * r2.uniform(0.86, 0.98)
                yb = y - hgt * f0
                pts = []
                for t_, v_ in corners:
                    tj, vj = t_ + r2.normal(0, 0.035), v_ + r2.normal(0, 0.06)
                    pts.append((x + dx * sw_ * tj, yb + dy * sw_ * tj - ch * vj))
                c = stone * r2.uniform(0.6, 1.3) * (0.9 + 0.06 * row)
                k = r2.random()
                if k < 0.16:
                    c = c * 0.72 + lichen * 0.28
                elif k < 0.26 and row == 0:
                    c = c * 0.7 + moss * 0.3
                tilt = (-nx * 0.75 + r2.normal(0, 0.16), ny * 0.75, 0.55 + r2.normal(0, 0.1))   # battered back
                if laid(row, u):
                    A.poly(pts, c)
                    N.poly(pts, enc(tilt))
                    cap = [pts[1], pts[2], pts[3], pts[4]]           # the top edge, turned up to the sky
                    A.poly(cap, c * 1.12)
                    N.poly(cap, enc((-nx * 0.3, ny * 0.3, 0.9)))
                u += sw_ * r2.uniform(0.97, 1.08)
        # coping: a row of stones set on edge along the top, each with a lit top
        cope = np.array([150, 146, 136], np.float32)
        u = r2.uniform(0, 4) * s
        while u < d[-1]:
            x, y, dx, dy, nx, ny = at(u)
            p_ = persp(y)
            hgt = 26 * s * p_ * height
            w_ = r2.uniform(3.2, 5.6) * s * p_
            yb, yt = y - hgt * 0.86, y - hgt - r2.uniform(2.0, 5.0) * s * p_ * height
            lean = r2.normal(0, 0.18) * (yb - yt)
            pts = [(x - w_ / 2, yb + dy * w_ * -0.5), (x + w_ / 2, yb + dy * w_ * 0.5),
                   (x + w_ * 0.42 + lean, yt + dy * w_ * 0.4), (x - w_ * 0.4 + lean, yt - dy * w_ * 0.4)]
            c = cope * r2.uniform(0.7, 1.15)
            if r2.random() < 0.15:
                c = c * 0.75 + lichen * 0.25
            nc = enc((-nx * 0.75 + r2.normal(0, 0.2), ny * 0.75, 0.55))
            if laid(3, u):
                A.poly(pts, c * 0.92)
                N.poly(pts, nc)
                tp = [pts[3], pts[2], (pts[2][0] - lean * 0.25, pts[2][1] + (yb - yt) * 0.25),
                      (pts[3][0] - lean * 0.25, pts[3][1] + (yb - yt) * 0.25)]
                A.poly(tp, c * 1.08)
                N.poly(tp, enc((0, 0.25, 0.95)))
            u += w_ * r2.uniform(1.0, 1.25)

    def tuft(self, A, N, x, y, h, rng, dark, light):
        """A tuft of a few tapering blades rooted at (x, y), dark at the foot and light at the tips."""
        for _ in range(int(rng.integers(3, 6))):
            lean = rng.uniform(-0.55, 0.55)
            hk = h * rng.uniform(0.55, 1.0)
            bw = max(0.6 * self.s, h * 0.08)
            bx = x + rng.uniform(-0.18, 0.18) * h
            mx, my = bx + lean * hk * 0.45, y - hk * 0.5
            n = enc((-lean * 0.5, -0.3, 0.9))          # facing the way the slope does, leaning out
            low = [(bx - bw, y + bw * 0.5), (bx + bw, y + bw * 0.5), (mx + bw * 0.7, my), (mx - bw * 0.7, my)]
            high = [(mx - bw * 0.7, my), (mx + bw * 0.7, my), (bx + lean * hk, y - hk)]
            A.poly(low, dark * rng.uniform(0.85, 1.1))
            A.poly(high, light * rng.uniform(0.85, 1.1))
            N.poly(low, n)
            N.poly(high, n)

    # -------------------------------------------------------------- hill --
    def hill(self):
        W, H, s = self.W, self.H, self.s
        se, wx = self.season, self.wx
        xd, yd = self._edge
        x1 = W
        y0 = int((yd.min() - 0.012) * H)
        hh, hw = H - y0, x1
        r = np.random.default_rng(31)
        xs = np.arange(0, x1, 1.0 * s + 0.5)
        ex = self.edge(xs / W) * H
        poly = [(0, H + 2), (0, ex[0])] + list(zip(xs, ex)) + [(x1, H + 2)]
        M = Layer(self, 0, y0, x1, H)
        M.poly(poly, (255, 255, 255))
        A = Layer(self, 0, y0, x1, H)   # albedo overlay (path, stones, flowers, blades ...)
        N = Layer(self, 0, y0, x1, H)   # and the normals of whatever has its own shape

        def persp(y):
            return 0.35 + 1.3 * np.clip((y / H - 0.6) / 0.4, 0, 1)

        def band(xn):
            return shore_band(xn) * H

        # the path to the door, and a worn trail to the bench
        tw = self.tw
        p = self.bezier((0.10 * W, 1.03 * H), (0.15 * W, 0.80 * H), (0.27 * W, 0.71 * H), (tw["cx"], tw["yb"] + 10 * s))
        q = self.bezier((0.205 * W, 0.80 * H), (0.30 * W, 0.755 * H), (0.40 * W, 0.735 * H), (BENCH[0] * W, BENCH[1] * H + 6 * s))
        # The ground's fine structure (ground.py) covers the whole hill, but stops a few rows short of the
        # shingle: the shingle, the sea and the pier stay exactly as they always were (and so does every
        # draw from r, which places the shore's stones), so the shore kit's reference frames still hold.
        xk, xw = W, int(math.ceil(0.46 * W))    # the ground's columns, and the walls' (and the hillside's)
        grass_y = lambda xn: self.edge(xn) * H + band(xn)     # where the grass starts (the top of the hill
        F = ground.fields(W, H, y0, xk, (p, 0.038 * W, 0.009 * W), (q, 0.007 * W, 0.004 * W), grass_y)  # left)
        r2 = np.random.default_rng(32)          # everything new draws from here, never from r
        free = lambda x, y: 0 <= x < xk and y0 <= y < H

        def clear_of_shingle(x0_, x1_, top):
            """Whether a stroke whose highest point is `top` stays below the shingle and the three rows of
            grass under it (where the shore kit fits its contact shadows) between columns x0_ and x1_."""
            xs_ = np.array([x0_, (x0_ + x1_) / 2, x1_], np.float32) / W
            return top - 1 > float(np.max(grass_y(xs_))) + 4 or float(np.max(band(xs_))) < 0.5
        on_path = lambda x, y: free(x, y) and float(F["path"][int(y) - y0, int(x)]) > 0.6
        tuft = np.array([[58, 90, 40], [84, 112, 48], [108, 124, 60], [146, 136, 80]], np.float32)
        tuft = tuft * (1 - 0.35 * se.winter) + np.array([118, 108, 70]) * 0.35 * se.winter
        tuft[2:] = tuft[2:] * (1 - 0.4 * se.dry) + np.array([176, 160, 104]) * 0.4 * se.dry
        for _ in range(1400):   # gravel and pebbles, each a little dome sitting in its own shadow
            i = r.integers(0, len(p))
            t = i / len(p)
            w = (0.038 - 0.029 * t) * W
            px, py = p[i] + r.uniform(-w * 0.9, w * 0.9, 2) * np.array([1, 0.35])
            rr = r.uniform(1.0, 3.4) * s * persp(py)
            c = np.array([150, 128, 98]) * r.uniform(0.7, 1.3)
            nx_ = r.normal(0, 0.3)
            if not on_path(px, py):
                continue
            rr *= 0.85
            c = c * 0.4 + np.array([132, 126, 114]) * (0.36 + 0.4 * c[0] / 150)   # greyer than the soil
            A.ellipse(px, py + rr * 0.3, rr * 1.15, rr * 0.62, (52, 44, 34), a=0.4)
            A.ellipse(px, py, rr, rr * 0.6, c * 0.85)
            N.ellipse(px, py, rr, rr * 0.6, enc((nx_ * 0.5, 0.55, 0.8)))       # its face, toward us
            A.ellipse(px, py - rr * 0.16, rr * 0.72, rr * 0.38, c * 1.12)
            N.ellipse(px, py - rr * 0.16, rr * 0.72, rr * 0.38, enc((nx_ * 0.3, -0.3, 0.92)))   # its top
        for _ in range(70):     # flat stones set in the path, worn level with it
            i = int(r2.integers(0, len(p) - 6))
            w = (0.038 - 0.029 * i / len(p)) * W
            px, py = p[i] + r2.uniform(-w * 0.8, w * 0.8, 2) * np.array([1, 0.3])
            if on_path(px, py):
                rs = r2.uniform(3.5, 8.0) * s * persp(py)
                self.rock(A, N, px, py, rs, rs * 0.42, r2, np.array([136, 126, 110]) * r2.uniform(0.85, 1.12))
        # stones by the path and in the grass, a few blades grown up round their feet
        for (rx, ry, rs) in [(0.09, 0.93, 26), (0.205, 0.83, 12), (0.36, 0.69, 9), (0.42, 0.88, 14), (0.25, 0.97, 18),
                             (0.53, 0.80, 8), (0.31, 0.76, 7)]:
            self.rock(A, N, rx * W, ry * H, rs * s, rs * s * 0.62, r, (122, 118, 110))
            if free(rx * W + rs * s, ry * H):
                for _ in range(int(3 + rs / 3)):
                    a_ = r2.uniform(0.15, 2.99)
                    gx_, gy_ = rx * W + math.cos(a_) * rs * s * 1.05, ry * H + math.sin(a_) * rs * s * 0.62 * 0.8 + 1.5 * s
                    self.tuft(A, N, gx_, gy_, r2.uniform(5, 9) * s * persp(gy_), r2, tuft[0] * 0.95, tuft[2])
        for (rx, ry, rs) in [(0.035, 0.80, 11), (0.16, 0.95, 9), (0.46, 0.96, 12), (0.385, 0.785, 7), (0.07, 0.70, 6)]:
            self.rock(A, N, rx * W, ry * H, rs * s, rs * s * 0.55, r2, (120, 116, 106))   # a few more, half sunk
            for _ in range(int(3 + rs / 3)):
                a_ = r2.uniform(0.15, 2.99)
                gx_, gy_ = rx * W + math.cos(a_) * rs * s * 1.05, ry * H + math.sin(a_) * rs * s * 0.55 * 0.8 + 1.5 * s
                self.tuft(A, N, gx_, gy_, r2.uniform(5, 9) * s * persp(gy_), r2, tuft[0] * 0.95, tuft[2])
        # the shore: a shingle beach between the low-water line and the grass, rocks along it
        x = 0.565 * W
        while x < 1.0 * W:
            xn = x / W
            e = self.edge(xn) * H
            b = band(xn)
            steep = sm(0.70, 0.62, xn)
            dense = 0.45 + 0.55 * steep
            x += r.choice([5, 8, 12, 18, 26, 40]) * s / dense
            if e > H + 20 * s or b < 1:
                continue
            big = r.random() < 0.16 + 0.3 * steep
            v = r.uniform(-0.08, 0.45) if big else r.uniform(-0.05, 1.0)
            by_ = e + v * b
            rs = (r.uniform(18, 40) if big else r.uniform(5, 14)) * s * persp(by_)
            wet = sm(0.4, 0.0, v)
            grey = np.array([134, 130, 122]) * r.uniform(0.8, 1.15)
            self.rock(A, N, x, by_, rs, rs * 0.62, r, grey, wet=wet, weed=wet * (r.random() < 0.6))
            if big and v > 0.15 and r.random() < 0.7:   # orange lichen above the splash zone
                for _ in range(int(r.integers(2, 6))):
                    A.ellipse(x + r.normal(0, rs * 0.3), by_ - rs * r.uniform(0.2, 0.5), rs * 0.08, rs * 0.05, (196, 132, 46), a=0.8)
        # strandline: a thin, broken line of dried wrack at the high-water mark
        for x in np.arange(0.575 * W, W, 2.5 * s):
            if r.random() < 0.45:
                continue
            xn = x / W
            yh = self.edge(xn) * H + 0.74 * band(xn) + r.normal(0, 1.2 * s)
            A.line([(x, yh), (x + r.uniform(2, 7) * s, yh + r.normal(0, 0.8) * s)], (58, 54, 40), 1.4 * s, a=0.8)
        # fallen leaves under the tree, more of them as autumn goes on
        tx, ty = TREE_BASE[0] * W, TREE_BASE[1] * H
        autumn = [(196, 150, 58), (205, 112, 48), (170, 90, 40), (150, 130, 50), (120, 84, 46)]
        rotten = 1 - se.autumn if se.doy < 200 else 0.0
        for _ in range(int(60 + 700 * se.fallen)):
            lx, ly = tx + r.normal(0, 90 * s), ty + abs(r.normal(0, 26 * s)) - 6 * s
            c = np.array(autumn[r.integers(0, 5)], np.float32) * (1 - 0.35 * rotten)
            A.ellipse(lx, ly, 2.6 * s, 1.4 * s, c, a=0.4 + 0.6 * min(1, se.fallen * 3))
        # wildflowers, in drifts, whatever is in bloom
        fl = fnoise(64, 128, 2.0, 1.0, 33)
        cols = se.flower_palette(np.random.default_rng(34), 3000)
        n = 0
        while n < int(3000 * se.flower_density):
            fx, fy = r.uniform(0, 1.0), r.uniform(0.61, 1.0)
            if fy * H < self.edge(fx) * H + 4 * s + band(fx) or fl[int((fy - 0.6) / 0.4 * 63), int(fx * 127)] < 0.35:
                continue
            rr = r.uniform(1.2, 2.4) * s * persp(fy * H)
            A.ellipse(fx * W, fy * H, rr, rr, cols[n])
            n += 1
        # a dry-stone wall across the lower field, open where the path crosses
        walls = self.field_walls()
        WM = Layer(self, 0, y0, xw, H)          # where the walls stand, so they don't fall in their own shadow
        HSL = Layer(self, 0, y0, xw, H)           # the hillside's built things (blue) and puddles (red, green)
        # what stands up from the ground is also recorded (fauna.py), once a day, so animals behind it hide
        rec = self.occl_recorder()
        At = Tee(A, rec) if rec else A
        for name, seg in zip(("wall-upper", "wall-lower"), walls):
            if rec:        # the lower wall and its last stretch are one wall to what stands on or behind it
                rec.begin(name, seg if name == "wall-upper" else np.concatenate([seg, self.field_wall_end()]))
            self.wall(At, N, seg, r, persp, r2, WM)
        wend, re_ = self.wall_end(At, N, persp, WM)
        if rec:
            rec.end()
        for seg in walls:                        # grass grown up against the foot of the wall
            for x_, y_ in seg[1:-1:2]:
                for _ in range(2):
                    gx_, gy_ = x_ + r2.uniform(-5, 5) * s, y_ + r2.uniform(0.5, 3.0) * s * persp(y_)
                    if r2.random() < 0.7 and free(gx_, gy_):
                        self.tuft(A, N, gx_, gy_, r2.uniform(5, 10) * s * persp(gy_), r2, tuft[0] * 0.95, tuft[2])
        for x_, y_ in wend[1:-1:2]:              # and at the foot of the lower wall's last stretch
            for _ in range(2):
                gx_, gy_ = x_ + re_.uniform(-5, 5) * s, y_ + re_.uniform(0.5, 3.0) * s * persp(y_)
                if re_.random() < 0.7 and free(gx_, gy_):
                    self.tuft(A, N, gx_, gy_, re_.uniform(5, 10) * s * persp(gy_), re_, tuft[0] * 0.95, tuft[2])
        # tufts across the slope; browner in winter, straw-coloured in a dry summer. The ground's own tufts
        # (ground.py) take their place, except where one reaches the shingle; near the bottom of the
        # frame some become larger blades in the foreground.
        for _ in range(int(11000)):
            gx, gy = r.uniform(0, x1), r.uniform(y0, H)
            if gy < self.edge(gx / W) * H + 3 * s + band(gx / W) * r.uniform(0.85, 1.05):
                continue
            ln = r.uniform(4, 11) * s * persp(gy) * (1 - 0.3 * se.winter)
            c = tuft[r.integers(0, 4)] * r.uniform(0.8, 1.15)
            leans = [r.uniform(-0.5, 0.5) * ln for k in range(3)]
            if not clear_of_shingle(gx - 0.5 * ln - 2 * s, gx + 3 * s + 0.5 * ln + 2 * s, gy - ln):
                for k in range(3):       # reaches the shingle: drawn exactly as it always was
                    A.line([(gx + k * 1.5 * s, gy), (gx + k * 1.5 * s + leans[k], gy - ln)], c, 1.1 * s)
            elif gy > 0.88 * H and not on_path(gx, gy) and r2.random() < 0.10 \
                    and clear_of_shingle(gx - 2.2 * ln, gx + 2.2 * ln, gy - 2.0 * ln):
                self.tuft(A, N, gx, gy, ln * 2.0, r2, tuft[0] * 0.95, tuft[2] * 1.05)
        # blades along the crest, against the sea
        for x in np.arange(0, 0.60 * W, 2.2 * s):
            y = self.edge(x / W) * H + 2 * s
            ln = r.uniform(4, 14) * s * persp(y)
            lean = r.uniform(-4, 4) * s
            c = tuft[r.integers(0, 4)] * r.uniform(0.85, 1.1)
            A.line([(x, y), (x + lean, y - ln)], c, 1.3 * s)
            M.line([(x, y), (x + lean, y - ln)], (255, 255, 255), 1.3 * s)
        # the hillside's built things and land detail (hillside.py): the garden, its shed and hives, the
        # field gate, outcrops, gorse, heather, wildflowers, puddles
        casters, feet = self.hillside(At, N, HSL, WM, persp)
        if rec:
            self.occl_store(rec)
        # shade it in strips of rows, so the big per-pixel arrays never exist for the whole hill at once
        G1 = fnoise(hh, hw, 2.4, 1.6, 101)
        G2 = fnoise(hh, hw, 1.0, 1.0, 102)
        G3 = fnoise(hh, hw, 1.6, 0.25, 103)
        DRY = fnoise(hh, hw, 2.8, 1.3, 104)
        HF = fnoise(hh, hw, 0.9, 1.0, 105)
        PATCH = fnoise(hh, hw, 2.2, 1.0, 106) if wx.snow_cover > 0.01 else None
        GY, GX = np.gradient(G1)
        HY, HX = np.gradient(HF)
        k = 0.15 / (np.std(GX) + 1e-6)
        kb = 0.5 / (np.std(HX) + 1e-6)
        base = np.array([58, 80, 40], np.float32) + np.array([-6, 14, -4], np.float32) * se.lush
        base = base * (1 - 0.3 * se.winter) + np.array([84, 86, 58], np.float32) * 0.3 * se.winter
        xn = (np.arange(x1, dtype=np.float32) + 0.5) / W
        ey_row = self.edge(xn)[None, :] * H
        bw_row = band(xn)[None, :] + 1e-3
        on_shore = sm(0.555, 0.59, xn)[None, :]
        wetline = 0.5 * self.tide + 0.12 + 0.22 * (1 - self.tide)
        # the walls' shadows, cast from wherever the sun (or a bright moon) stands, and
        # the darker grass in the angle at their foot
        src = None
        if self.sun_alt > 1:
            src = (self.sun_alt, self.sun_az, 0.82)
        elif self.moon_alt > 4 and self.sun_alt < -6:
            src = (self.moon_alt, self.moon_az, 0.6)
        wsh, wao = Image.new("L", (xw, hh), 0), Image.new("L", (xw, hh), 0)
        dsh, dao = ImageDraw.Draw(wsh), ImageDraw.Draw(wao)
        if src:
            cot = min(1 / math.tan(math.radians(src[0])), 3.0)
            sx, sy = math.sin(math.radians(src[1])) * cot, -math.cos(math.radians(src[1])) * cot * KF
        for seg in walls + (wend,):
            for (xa, ya), (xb, yb) in zip(seg[:-1], seg[1:]):
                dao.line([(xa, ya - y0 + s), (xb, yb - y0 + s)], fill=255, width=max(2, int(7 * s * persp(ya))))
                if src:
                    ha, hb = 29 * s * persp(ya), 29 * s * persp(yb)
                    dsh.polygon([(xa, ya - y0), (xb, yb - y0), (xb + sx * hb, yb - y0 + sy * hb), (xa + sx * ha, ya - y0 + sy * ha)], fill=255)
        for (xa, ya), (xb, yb) in feet:           # and the hillside's things, at their foot
            dao.line([(xa, ya - y0 + s), (xb, yb - y0 + s)], fill=200, width=max(2, int(5 * s * persp(ya))))
        if src:
            for c_ in casters:
                kind = c_[0]
                if kind == "poly":
                    foot, h = c_[1], c_[2]
                    pts = foot + [(x_ + sx * h, y_ + sy * h) for x_, y_ in foot]
                    dsh.polygon([(x_, y_ - y0) for x_, y_ in hull(pts)], fill=255)
                elif kind == "box":       # a footprint, the top corners, and the ground point under each top
                    foot, tops, under = c_[1], c_[2], c_[3]
                    pts = list(foot)
                    for (x_, y_), (xt, yt) in zip(under, tops):
                        h = y_ - yt
                        pts.append((x_ + sx * h, y_ + sy * h))
                    dsh.polygon([(x_, y_ - y0) for x_, y_ in hull(pts)], fill=255)
                elif kind == "wall":
                    (xa, ya), (xb, yb), ha, hb = c_[1], c_[2], c_[3], c_[4]
                    dsh.polygon([(xa, ya - y0), (xb, yb - y0), (xb + sx * hb, yb - y0 + sy * hb), (xa + sx * ha, ya - y0 + sy * ha)], fill=255)
                else:                     # a bar: a rail or a pole
                    (xa, ya), (xb, yb), ha, hb, w_ = c_[1], c_[2], c_[3], c_[4], c_[5]
                    dsh.line([(xa + sx * ha, ya - y0 + sy * ha), (xb + sx * hb, yb - y0 + sy * hb)], fill=255, width=max(1, int(round(w_))))
        WSH = ndi.gaussian_filter(np.asarray(wsh, np.float32) / 255, 1.2 * s) * (src[2] if src else 0)
        WAO = ndi.gaussian_filter(np.asarray(wao, np.float32) / 255, 3.0 * s)
        shore_cols = sm(0.54, 0.56, xn)[None, :]
        clip0 = ey_row + bw_row + 4.0                     # 4 rows under the top of the grass, at the shore
        clip1 = clip0 + np.maximum(6.0, 0.12 * bw_row)
        soil_c = np.array([150, 128, 98], np.float32) * 0.97
        worn_c = np.array([126, 124, 84], np.float32)
        frost_c = np.array([200, 210, 218], np.float32)
        step = 96
        for r0 in range(0, hh, step):
            r1 = min(hh, r0 + step)
            sl = slice(r0, r1)
            _, mask = M.arrays_rows(r0, r1)
            orgb, oal = A.arrays_rows(r0, r1)
            nrgb, nal = N.arrays_rows(r0, r1)
            g1, g2, g3, hf = G1[sl], G2[sl], G3[sl], HF[sl]
            dry = sm(0.1, 1.4, DRY[sl])[..., None] * (0.35 + 0.5 * se.dry - 0.25 * se.lush)
            alb = base + np.array([46, 34, 18], np.float32) * sm(-1.5, 1.5, g1)[..., None]
            alb = alb * (1 - dry) + np.array([156, 142, 92], np.float32) * dry
            alb *= (1 + 0.07 * g2 + 0.09 * g3)[..., None]
            # the ground's fine structure: tufts with dark feet and light tips, darker
            # hollows between them, swathes along the slope, and the worn path with its ruts and verges
            f = {k_: v_[sl].astype(np.float32) for k_, v_ in F.items()}
            Ygk = np.arange(y0 + r0, y0 + r1, dtype=np.float32)[:, None] + 0.5
            keep = 1 - shore_cols * (1 - sm(clip0, clip1, Ygk))   # 0 on the shingle, exactly
            kk = keep[..., None]
            tc, tip, pm = f["tuft"][..., None], f["tip"][..., None], f["path"][..., None]
            ac, rut, trail = np.abs(f["across"])[..., None], f["rut"][..., None], f["trail"][..., None]
            dl = f["dense"][..., None]
            gk = alb[:, :xk]
            g = gk * (TUFT_LIFT + 0.09 * f["swathe"] + 0.06 * f["hum"])[..., None]   # lifted for what the
            gap = g * (1 - 0.3 * TUFT_SHOW * dl)                                           # tufts' feet take back
            gap = gap * (1 - 0.6 * trail) + (g * 0.55 + worn_c * 0.45) * 0.6 * trail
            soil = soil_c * (1 + 0.08 * sm(0.55, 0.05, ac) - 0.14 * sm(0.5, 1.0, ac) - 0.1 * rut) \
                * (1 + 0.05 * g2[:, :xk] + 0.04 * g1[:, :xk])[..., None]
            verge = sm(0.7, 1.05, ac)
            soil = soil * (1 - 0.35 * verge) + g * 0.8 * 0.35 * verge
            ground_ = gap * (1 - pm) + soil * pm
            tlo = g * 0.8
            thi = g * 0.85 + tuft[2] * 0.5
            tcol = (tlo + (thi - tlo) * tip ** 1.3) * (0.86 + 0.18 * f["blade"] + 0.2 * f["tone"] - 0.1)[..., None]
            straw = sm(0.82, 0.95, f["tone"])[..., None] * (0.25 + 0.4 * se.winter + 0.3 * se.dry)
            tcol = tcol * (1 - straw) + tuft[3] * (0.6 + 0.4 * tip) * straw
            tcol = ground_ + (tcol - ground_) * TUFT_SHOW
            new = ground_ * (1 - tc) + tcol * tc
            alb[:, :xk] = gk + kk * (new - gk)
            Yg = np.arange(y0 + r0, y0 + r1, dtype=np.float32)[:, None] + 0.5
            v = (Yg - ey_row) / bw_row                      # 0 at low water, 1 where the grass starts
            grassline = 1 + 0.12 * g2 + 0.10 * g3
            beach = sm(grassline + 0.12, grassline - 0.25, v) * on_shore
            shingle = np.array([124, 116, 102], np.float32) * (1 + 0.14 * hf + 0.08 * g1)[..., None]
            wet = sm(wetline + 0.08, wetline - 0.08, v) * on_shore
            shingle = shingle * (1 - 0.5 * wet[..., None])
            alb = alb * (1 - beach[..., None]) + shingle * beach[..., None]
            alb = alb * (1 - oal) + orgb * oal
            nrm = np.stack([-GX[sl] * k, -0.34 + GY[sl] * k, np.full_like(g1, 0.94)], -1)
            nrm += beach[..., None] * np.stack([-HX[sl] * kb, HY[sl] * kb, np.zeros_like(g1)], -1)
            # tufts lean their blades out to either side; hummocks and ruts tilt the ground under them
            t0, p0 = f["tuft"], f["path"]
            dnx = -0.5 * TUFT_SHOW * f["lean"] * t0 + 0.13 * f["hum_x"] * (1 - p0) - f["rut_x"]
            dny = -0.13 * f["hum_y"] * (1 - p0) + f["rut_y"]
            nrm[:, :xk, :2] += kk * np.stack([dnx, dny], -1)
            nrm = normalize(nrm * (1 - nal) + (nrgb / 127.5 - 1) * nal)
            # the hillside's built things take no grass shading; the wet rims of its puddles are darker
            xr, _ = HSL.arrays_rows(r0, r1)
            xr *= 1 / 255
            obj, hpud, rim = xr[..., 2], xr[..., 0], xr[..., 1]
            dnx[:, :xw] *= 1 - obj
            dny[:, :xw] *= 1 - obj
            alb[:, :xw] *= (1 - 0.32 * rim)[..., None]
            # weather on the ground: lying snow on whatever faces up, rime on the grass, wet darkening
            buried = 0.0                 # how far lying snow has filled in the tufts and the ruts
            if PATCH is not None:
                patch = sm(-0.8, 0.6, PATCH[sl] + 3 * (wx.snow_cover - 0.5))
                snow = (wx.snow_cover * sm(0.5, 0.85, nrm[..., 2]) * patch)[..., None]
                alb = alb * (1 - snow) + np.array([236, 240, 246], np.float32) * snow
                buried = snow[:, :xk, 0]
                nrm[:, :xk, :2] -= kk * np.stack([dnx, dny], -1) * (0.8 * buried)[..., None]
                nrm[:, :xk] = np.where(kk > 0, normalize(nrm[:, :xk]), nrm[:, :xk])
            if wx.frost > 0.01:
                rime = (wx.frost * 0.55 * (1 - beach) * (1 - oal[..., 0]) * sm(-0.5, 0.8, g2))[..., None]
                alb = alb * (1 - rime) + np.array([200, 210, 218], np.float32) * rime
                tips = (wx.frost * 0.35 * tc * tip * (1 - oal[:, :xk, :1])) * kk
                alb[:, :xk] = alb[:, :xk] * (1 - tips) + frost_c * tips
            if wx.wet > 0.01:
                alb *= 1 - 0.28 * wx.wet
            shade, ao = self.shade[y0 + r0:y0 + r1, :x1], self.ao[y0 + r0:y0 + r1, :x1]
            amb = 1 - 0.55 * ao
            # the feet of the tufts and the hollows between them get less of the sky and
            # the sun; the walls cast their shadows and darken the grass at their foot
            shade, wk = shade.copy(), keep
            _, wal = WM.arrays_rows(r0, r1)
            d0 = f["dense"]
            occ = ((1 - t0) * (1 - p0) * 0.4 * d0 + t0 * (1 - f["tip"]) * 0.3) * TUFT_SHOW * (1 - buried)
            occ[:, :xw] *= 1 - obj
            sk = 1 - (1 - shade[:, :xk]) * (1 - occ)
            sk[:, :xw] = np.maximum(sk[:, :xw], WSH[sl] * (1 - wal[..., 0]))
            shade[:, :xk] += wk * (sk - shade[:, :xk])
            oa = (1 - t0) * ((1 - 0.3 * d0) * (1 - p0) + p0 * (1 - 0.2 * f["rut"])) + t0 * (0.72 + 0.28 * f["tip"])
            oa = 1 + (oa - 1) * TUFT_SHOW
            oa[:, :xw] = 1 + (oa[:, :xw] - 1) * (1 - obj)
            oa = oa * (1 - 0.1 * sm(0.5, -1.5, f["hum"]))
            oa[:, :xw] *= 1 - 0.45 * WAO[sl] * (1 - wal[..., 0])
            amb[:, :xk] *= 1 + wk * (oa - 1) * (1 - 0.8 * buried)
            L = self.light(nrm, shade, amb)
            if self.pools:
                X = np.arange(x1, dtype=np.float32)[None, :] + 0.5
                L = L + self.local(X, Yg, ground=True)
            col = alb * L
            # wet stones and shingle catch the sky
            sheen = (np.maximum(wet, 0.6 * wx.wet * beach) * sm(0.6, 0.95, nrm[..., 2]))[..., None]
            col += sheen * self.hor_col * 0.18
            if wx.wet > 0.01:          # water standing here and there in the ruts catches the sky
                pud = wx.wet * sm(0.55, 0.95, f["rut"]) * sm(0.2, 1.2, g3[:, :xk]) * f["path"]
                pud = (pud * (1 - oal[:, :xk, 0]) * (1 - buried) * sm(0.6, 0.95, nrm[:, :xk, 2]))[..., None] * kk
                col[:, :xk] = col[:, :xk] * (1 - 0.35 * pud) + pud * self.hor_col * 0.09
            if wx.wet > 0.01 and hpud.any():
                self.puddle_light(col, hpud, Yg, xw, L, buried)
            crest = (sm(0.05 * H, 0, Yg - ey_row) * 0.12 * (1 - on_shore))[..., None]
            col = col * (1 - crest) + self.hor_col * crest
            # the sea covers the lower beach as the tide comes in
            sea = sm(0.5 * self.tide + 0.02, 0.5 * self.tide - 0.02, v) * on_shore * (1 - oal[..., 0] * sm(0.0, 0.3, v + 0.3))
            self.over(y0 + r0, y0 + r1, 0, x1, col, mask * (1 - sea[..., None]))
