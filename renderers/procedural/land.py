"""The headland: shadows, grass, the path, rocks, flowers, the wall and the shore."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

from core import *  # noqa: F401,F403


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

    def wall(self, A, N, seg, r, persp):
        """A dry-stone wall along a curve: coursed stones with lit tops, then rounded capstones."""
        s = self.s
        d = np.cumsum(np.r_[0, np.linalg.norm(np.diff(seg, axis=0), axis=1)])
        dirs = np.gradient(seg, axis=0)
        dirs /= np.linalg.norm(dirs, axis=1, keepdims=True) + 1e-6
        # the dark body of the wall, seen between the stones
        top = [(x, y - 26 * s * persp(y)) for x, y in seg]
        A.poly([tuple(p) for p in seg] + top[::-1], (46, 44, 40))
        N.poly([tuple(p) for p in seg] + top[::-1], enc((0, 0.9, 0.3)))
        for row in range(4):
            u = r.uniform(0, 8) * s
            while u < d[-1]:
                i = int(np.searchsorted(d, u))
                i = min(i, len(seg) - 1)
                x, y = np.interp(u, d, seg[:, 0]), np.interp(u, d, seg[:, 1])
                dx, dy = dirs[i]
                nx, ny = (-dy, dx) if dx > 0 else (dy, -dx)
                front = (-nx * 0.85, ny * 0.85, 0.35)
                hgt = 26 * s * persp(y)
                sw_ = r.uniform(7, 13) * s * persp(y)
                sh_ = hgt / 4 * r.uniform(0.75, 0.95)
                yy = y - hgt * (row + 0.5) / 4
                pts = []
                for t_, v_ in ((-0.5, -0.38), (-0.38, -0.5), (0.4, -0.5), (0.5, -0.35), (0.48, 0.42), (-0.46, 0.45)):
                    tj, vj = t_ + r.normal(0, 0.05), v_ + r.normal(0, 0.06)
                    pts.append((x + dx * sw_ * tj, yy + dy * sw_ * tj + sh_ * vj))
                c = np.array([128, 124, 114]) * r.uniform(0.72, 1.18) * (0.84 + 0.06 * row)
                if r.random() < 0.18:
                    c = c * 0.8 + np.array([150, 150, 96]) * 0.2      # lichen
                A.poly(pts, c)
                N.poly(pts, enc(front))
                bevel = [pts[0], pts[1], pts[2], pts[3], (pts[3][0], pts[3][1] + sh_ * 0.25), (pts[0][0], pts[0][1] + sh_ * 0.25)]
                A.poly(bevel, c * 1.08)
                N.poly(bevel, enc((-nx * 0.3, ny * 0.3, 0.9)))
                u += sw_ * r.uniform(0.9, 1.08)
        for u in np.arange(0, d[-1], 9 * s):   # capstones
            x, y = np.interp(u, d, seg[:, 0]), np.interp(u, d, seg[:, 1])
            hgt = 26 * s * persp(y)
            c = np.array([150, 146, 136]) * r.uniform(0.85, 1.15)
            A.ellipse(x, y - hgt, 6.5 * s * persp(y), 3.4 * s * persp(y), c * 0.85)
            N.ellipse(x, y - hgt, 6.5 * s * persp(y), 3.4 * s * persp(y), enc((0, 0.8, 0.6)))
            A.ellipse(x - 0.8 * s, y - hgt - 1.0 * s * persp(y), 5 * s * persp(y), 2.2 * s * persp(y), c)
            N.ellipse(x - 0.8 * s, y - hgt - 1.0 * s * persp(y), 5 * s * persp(y), 2.2 * s * persp(y), enc((0.1, 0.25, 0.96)))

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
        A.poly(self.ribbon(p, 0.038 * W, 0.009 * W), (150, 128, 98))
        q = self.bezier((0.205 * W, 0.80 * H), (0.30 * W, 0.755 * H), (0.40 * W, 0.735 * H), (BENCH[0] * W, BENCH[1] * H + 6 * s))
        A.poly(self.ribbon(q, 0.007 * W, 0.004 * W), (126, 124, 84), a=0.35)
        for _ in range(1400):   # gravel and pebbles, with their own little shapes
            i = r.integers(0, len(p))
            t = i / len(p)
            w = (0.038 - 0.029 * t) * W
            px, py = p[i] + r.uniform(-w * 0.9, w * 0.9, 2) * np.array([1, 0.35])
            rr = r.uniform(1.0, 3.4) * s * persp(py)
            c = np.array([150, 128, 98]) * r.uniform(0.7, 1.3)
            A.ellipse(px, py, rr, rr * 0.6, c)
            N.ellipse(px, py, rr, rr * 0.6, enc((r.normal(0, 0.3), 0.3, 0.9)))
        # stones by the path and in the grass
        for (rx, ry, rs) in [(0.09, 0.93, 26), (0.205, 0.83, 12), (0.36, 0.69, 9), (0.42, 0.88, 14), (0.25, 0.97, 18),
                             (0.53, 0.80, 8), (0.31, 0.76, 7)]:
            self.rock(A, N, rx * W, ry * H, rs * s, rs * s * 0.62, r, (122, 118, 110))
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
        for seg in (self.bezier((-0.02 * W, 0.742 * H), (0.04 * W, 0.76 * H), (0.10 * W, 0.79 * H), (0.148 * W, 0.812 * H), 90),
                    self.bezier((0.196 * W, 0.826 * H), (0.25 * W, 0.845 * H), (0.30 * W, 0.88 * H), (0.34 * W, 0.95 * H), 90)):
            self.wall(A, N, seg, r, persp)
        # tufts across the slope; browner in winter, straw-coloured in a dry summer
        tuft = np.array([[58, 90, 40], [84, 112, 48], [108, 124, 60], [146, 136, 80]], np.float32)
        tuft = tuft * (1 - 0.35 * se.winter) + np.array([118, 108, 70]) * 0.35 * se.winter
        tuft[2:] = tuft[2:] * (1 - 0.4 * se.dry) + np.array([176, 160, 104]) * 0.4 * se.dry
        for _ in range(int(11000)):
            gx, gy = r.uniform(0, x1), r.uniform(y0, H)
            if gy < self.edge(gx / W) * H + 3 * s + band(gx / W) * r.uniform(0.85, 1.05):
                continue
            ln = r.uniform(4, 11) * s * persp(gy) * (1 - 0.3 * se.winter)
            c = tuft[r.integers(0, 4)] * r.uniform(0.8, 1.15)
            for k in range(3):
                lean = r.uniform(-0.5, 0.5) * ln
                A.line([(gx + k * 1.5 * s, gy), (gx + k * 1.5 * s + lean, gy - ln)], c, 1.1 * s)
        # blades along the crest, against the sea
        for x in np.arange(0, 0.60 * W, 2.2 * s):
            y = self.edge(x / W) * H + 2 * s
            ln = r.uniform(4, 14) * s * persp(y)
            lean = r.uniform(-4, 4) * s
            c = tuft[r.integers(0, 4)] * r.uniform(0.85, 1.1)
            A.line([(x, y), (x + lean, y - ln)], c, 1.3 * s)
            M.line([(x, y), (x + lean, y - ln)], (255, 255, 255), 1.3 * s)
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
            nrm = normalize(nrm * (1 - nal) + (nrgb / 127.5 - 1) * nal)
            # weather on the ground: lying snow on whatever faces up, rime on the grass, wet darkening
            if PATCH is not None:
                patch = sm(-0.8, 0.6, PATCH[sl] + 3 * (wx.snow_cover - 0.5))
                snow = (wx.snow_cover * sm(0.5, 0.85, nrm[..., 2]) * patch)[..., None]
                alb = alb * (1 - snow) + np.array([236, 240, 246], np.float32) * snow
            if wx.frost > 0.01:
                rime = (wx.frost * 0.55 * (1 - beach) * (1 - oal[..., 0]) * sm(-0.5, 0.8, g2))[..., None]
                alb = alb * (1 - rime) + np.array([200, 210, 218], np.float32) * rime
            if wx.wet > 0.01:
                alb *= 1 - 0.28 * wx.wet
            shade, ao = self.shade[y0 + r0:y0 + r1, :x1], self.ao[y0 + r0:y0 + r1, :x1]
            L = self.light(nrm, shade, 1 - 0.55 * ao)
            if self.pools:
                X = np.arange(x1, dtype=np.float32)[None, :] + 0.5
                L = L + self.local(X, Yg, ground=True)
            col = alb * L
            # wet stones and shingle catch the sky
            sheen = (np.maximum(wet, 0.6 * wx.wet * beach) * sm(0.6, 0.95, nrm[..., 2]))[..., None]
            col += sheen * self.hor_col * 0.18
            crest = (sm(0.05 * H, 0, Yg - ey_row) * 0.12 * (1 - on_shore))[..., None]
            col = col * (1 - crest) + self.hor_col * crest
            # the sea covers the lower beach as the tide comes in
            sea = sm(0.5 * self.tide + 0.02, 0.5 * self.tide - 0.02, v) * on_shore * (1 - oal[..., 0] * sm(0.0, 0.3, v + 0.3))
            self.over(y0 + r0, y0 + r1, 0, x1, col, mask * (1 - sea[..., None]))
