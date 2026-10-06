"""Boats, the bench, the lamp and the pier."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

from core import *  # noqa: F401,F403


class PropsMixin:
    def boat(self, cx, cy, size, facing, sails, masthead=False):
        s = self.s
        L = Layer(self, cx - size * 0.8, cy - size * 1.35, cx + size * 0.8, cy + size * 0.3)
        f = facing

        def P(x, y):
            return (cx + f * x * size, cy + y * size)
        side = normalize([0, 1, 0.2])
        seacol = self.c[min(self.H - 1, int(cy + 0.12 * size)), int(np.clip(cx, 0, self.W - 1))]
        L.poly([P(-0.40, 0.10), P(0.42, 0.10), P(0.32, 0.17), P(-0.30, 0.17)], seacol * 0.6, a=0.6)
        L.poly([P(-0.46, -0.05), P(0.56, -0.07), P(0.40, 0.10), P(-0.38, 0.09)], self.lit((228, 226, 220), side))
        L.poly([P(-0.44, 0.00), P(0.50, -0.01), P(0.47, 0.025), P(-0.43, 0.035)], self.lit((40, 52, 84), side))
        L.poly([P(-0.20, -0.05), P(0.10, -0.06), P(0.08, -0.13), P(-0.17, -0.13)], self.lit((214, 208, 196), [0, .8, .6]))
        L.line([P(0.05, -0.06), P(0.05, -1.20)], self.lit((70, 62, 55), side), max(1.0, size * 0.018))
        if sails:
            back = max(0.0, -float(self.sunv[1])) * self.sun_str * 0.35
            sail = self.lit((240, 236, 222), [-f * 0.3, 0.8, 0.3]) + np.array([255, 220, 170]) * back * self.sun_col
            L.poly([P(0.035, -1.16), P(0.035, -0.13), P(-0.40, -0.13)], sail)
            L.poly([P(0.07, -1.05), P(0.55, -0.09), P(0.07, -0.10)], sail * 0.94)
            L.line([P(0.05, -0.12), P(-0.42, -0.12)], self.lit((70, 62, 55), side), max(1.0, size * 0.014))
        else:
            L.line([P(0.05, -0.16), P(-0.36, -0.14)], self.lit((200, 196, 186), side), max(1.0, size * 0.03))
        L.composite()
        if masthead and self.night > 0:
            x, y = P(0.05, -1.22)
            self.glow(x, y, 2.2 * s, (235, 240, 255), 1.4 * self.night)
            self.glow(x, y, 9 * s, (200, 215, 255), 0.18 * self.night)

    def boats(self):
        s, W, H = self.s, self.W, self.H
        b = self.day.events.boat(self.t)
        if b:
            x, y, facing = b
            size = 170 * s * (y - VH) / (MOORED[1] - VH)
            self.boat(x * W, y * H, size, facing, True)

    def moored_boat(self):
        if self.day.events.boat(self.t):
            return
        s = self.s
        cx, cy, size = MOORED[0] * self.W, MOORED[1] * self.H, 170 * s
        self.boat(cx, cy, size, -1, False, masthead=True)
        # the bow line, slack, to the post at the end of the pier
        px, py = self.pproj(*self.pier_pt(1.0, 0.06, PIER3["deck"] + 0.008))
        bx, by = cx - 0.52 * size, cy - 0.04 * size
        L = Layer(self, min(px, bx) - 4 * s, min(py, by) - 4 * s, max(px, bx) + 4 * s, max(py, by) + 14 * s)
        sag = [(bx + (px - bx) * t, by + (py - by) * t + 9 * s * math.sin(math.pi * t)) for t in np.linspace(0, 1, 12)]
        L.line(sag, self.lit((150, 140, 116), [0, 1, 0.4]), 1.3 * s)
        L.composite()

    def bench(self):
        s, W, H = self.s, self.W, self.H
        bx, gy = BENCH[0] * W, BENCH[1] * H
        L = Layer(self, bx - 110 * s, gy - 95 * s, bx + 110 * s, gy + 10 * s)
        wood_n, iron_n = normalize([0, 0.8, 0.6]), normalize([0, 1, 0.2])
        wood = self.lit((128, 86, 54), wood_n, bx, gy - 40 * s)
        iron = self.lit((36, 36, 40), iron_n, bx, gy - 40 * s)
        L.poly([(bx - 92 * s, gy - 42 * s), (bx + 92 * s, gy - 42 * s), (bx + 92 * s, gy - 36 * s), (bx - 92 * s, gy - 36 * s)], wood * 0.75)
        for yy in (-78, -64, -50):
            L.poly([(bx - 94 * s, gy + (yy - 0) * s), (bx + 94 * s, gy + yy * s), (bx + 94 * s, gy + (yy + 9) * s), (bx - 94 * s, gy + (yy + 9) * s)], wood)
            L.line([(bx - 94 * s, gy + yy * s + 0.8 * s), (bx + 94 * s, gy + yy * s + 0.8 * s)], wood * 1.25, 1.2 * s)
        for sx in (-1, 1):
            x = bx + sx * 97 * s
            L.line([(x, gy), (x, gy - 82 * s)], iron, 5 * s)
            L.line([(x - sx * 4 * s, gy - 6 * s), (x - sx * 4 * s, gy - 34 * s)], iron, 4 * s)
            L.line([(x, gy - 44 * s), (x + sx * 12 * s, gy - 48 * s), (x + sx * 16 * s, gy - 56 * s)], iron, 4 * s)
            L.ellipse(x + sx * 16 * s, gy - 58 * s, 4 * s, 4 * s, iron)
        L.poly([(bx - 9 * s, gy - 61 * s), (bx + 9 * s, gy - 61 * s), (bx + 9 * s, gy - 56 * s), (bx - 9 * s, gy - 56 * s)],
               self.lit((196, 156, 70), wood_n) + 20 * self.sun_str)
        L.composite()

    def lamp(self):
        s, W, H = self.s, self.W, self.H
        lx, gy, hgt = LAMP[0] * W, LAMP[1] * H, LAMP[2] * s
        on = self.lights_on
        L = Layer(self, lx - 30 * s, gy - hgt - 40 * s, lx + 30 * s, gy + 6 * s)
        iron = self.lit((34, 34, 38), normalize([0, 1, 0.2]), lx, gy - hgt * 0.5)
        L.poly([(lx - 9 * s, gy), (lx + 9 * s, gy), (lx + 6 * s, gy - 16 * s), (lx - 6 * s, gy - 16 * s)], iron)
        L.poly([(lx - 3.6 * s, gy - 14 * s), (lx + 3.6 * s, gy - 14 * s), (lx + 2.6 * s, gy - hgt), (lx - 2.6 * s, gy - hgt)], iron)
        L.line([(lx - 14 * s, gy - hgt * 0.86), (lx + 14 * s, gy - hgt * 0.86)], iron, 2.4 * s)
        ty = gy - hgt
        glass = self.lit((170, 180, 190), normalize([0, 1, 0.3])) * (1 - on) + np.array([255, 222, 160], np.float32) * on
        L.poly([(lx - 9 * s, ty), (lx + 9 * s, ty), (lx + 12 * s, ty - 30 * s), (lx - 12 * s, ty - 30 * s)], glass)
        L.line([(lx, ty), (lx, ty - 30 * s)], iron, 1.5 * s)
        L.line([(lx - 9 * s, ty), (lx + 9 * s, ty)], iron, 2.5 * s)
        L.poly([(lx - 15 * s, ty - 30 * s), (lx + 15 * s, ty - 30 * s), (lx, ty - 42 * s)], iron)
        L.ellipse(lx, ty - 43 * s, 2.5 * s, 2.5 * s, iron)
        L.composite()
        self.lamp_pos = (lx, ty - 15 * s)

    def world_n(self, nx, ny, nz):
        """World-space normal (x right/west, y up, z ahead/south) to the east/north/up frame of the lights."""
        return normalize([-nx, -nz, ny])

    def post(self, L, X, Z, y0, y1, r, albedo, x=None, y=None):
        """A round timber post standing at world (X, Z) from height y0 to y1, shaded across its width."""
        cx, ya = self.pproj(X, y0, Z)
        _, yb = self.pproj(X, y1, Z)
        D = math.hypot(X, Z)
        half = r / D * self.W / math.radians(AZ_SPAN)
        az = math.atan2(X, Z)
        pdir, qdir = (math.sin(az), math.cos(az)), (math.cos(az), -math.sin(az))
        edges = np.linspace(-1, 1, 5)
        for e0, e1 in zip(edges[:-1], edges[1:]):
            th = (e0 + e1) / 2 * math.pi / 2
            n = (-pdir[0] * math.cos(th) + qdir[0] * math.sin(th), 0, -pdir[1] * math.cos(th) + qdir[1] * math.sin(th))
            c = self.lit(albedo, self.world_n(*n), x, y)
            L.poly([(cx + e0 * half, ya), (cx + e1 * half, ya), (cx + e1 * half, yb), (cx + e0 * half, yb)], c)
        return cx, ya, yb, half

    def pier(self):
        s, W, H = self.s, self.W, self.H
        P = PIER3
        deck, thick = P["deck"], P["thick"]
        r = np.random.default_rng(61)
        xs, ys = self.pproj(*self.pier_pt(np.array([-0.05, 1.05, 1.05, -0.05]), np.array([-0.3, -0.3, 1.3, 1.3]), np.zeros(4)))
        L = Layer(self, xs.min() - 40 * s, ys.min() - 140 * s, xs.max() + 40 * s, ys.max() + 60 * s)
        U = np.linspace(0, 1, 25)

        def quad(u0, u1, v0, v1, y0, y1=None, n=8):
            """Outline of a deck-aligned rectangle; with y1 it is a vertical face along v0."""
            uu = np.linspace(u0, u1, n)
            if y1 is None:
                a = self.pproj(*self.pier_pt(uu, v0 + 0 * uu, y0 + 0 * uu))
                b = self.pproj(*self.pier_pt(uu[::-1], v1 + 0 * uu, y0 + 0 * uu))
            else:
                a = self.pproj(*self.pier_pt(uu, v0 + 0 * uu, y0 + 0 * uu))
                b = self.pproj(*self.pier_pt(uu[::-1], v0 + 0 * uu, y1 + 0 * uu))
            return list(zip(a[0], a[1])) + list(zip(b[0], b[1]))

        timber = np.array([96, 80, 64], np.float32)
        old = np.array([118, 112, 102], np.float32)
        side_n = self.world_n(P["dir"][1], 0, -P["dir"][0])   # the near side faces the camera
        up = normalize([0, 0, 1])
        bays = 8
        # only open water takes the shadow and the reflections, not the shore
        water = 1 - self.a[L.y0:L.y1, L.x0:L.x1] if self.a is not None else None
        # shadow of the deck on the water: faint, since the water mostly mirrors the sky
        if self.sun_alt > 8:
            S = Layer(self, L.x0, L.y0, L.x1, L.y1)
            sx, sy, sz = -self.sunv[0], self.sunv[2], -self.sunv[1]
            Xc, Yc, Zc = self.pier_pt(np.array([0, 1, 1, 0.0]), np.array([0, 0, 1, 1.0]), np.full(4, deck))
            Qx, Qz = Xc - Yc * sx / sy, Zc - Yc * sz / sy
            px, py = self.pproj(Qx, np.zeros(4), Qz)
            S.poly(list(zip(px, py)), np.array([8, 22, 34]) * (self.amb + 0.3), a=0.16 * self.sun_str)
            S.composite(allow=water)
        # reflections: the posts and the stringer mirrored in the water, broken up by ripples
        R = Layer(self, L.x0, L.y0, L.x1, L.y1)
        for j in range(bays + 1):
            for v in (1, 0):
                X, _, Z = self.pier_pt(j / bays, v, 0)
                self.post(R, float(X), float(Z), 0, -(deck - thick), 0.0085, timber * 0.55)
        R.poly(quad(0, 1, 0, 0, -(deck - thick), -deck), timber * 0.45)
        rgb, al = R.arrays()
        if al.max() > 0:
            rows = np.arange(al.shape[0], dtype=np.float32)[:, None]
            cols = np.arange(al.shape[1], dtype=np.float32)[None, :]
            off = 2.2 * s * np.sin(rows * 0.9 / s + 1.3) + 1.2 * s * np.sin(rows * 0.37 / s)
            for ch in range(3):
                rgb[..., ch] = ndi.map_coordinates(rgb[..., ch], [rows + 0 * cols, cols + off], order=1, mode="nearest")
            al = ndi.map_coordinates(al[..., 0], [rows + 0 * cols, cols + off], order=1, mode="nearest")[..., None]
            al = ndi.gaussian_filter(al, (0.8 * s, 0.4 * s, 0)) * 0.55 * (1 - 0.4 * self.night)
            if water is not None:
                al = al * water[..., None]
            self.over(R.y0, R.y1, R.x0, R.x1, rgb, al)
        # far posts, then the bracing between the near ones, the stringer, the near posts
        for j in range(bays + 1):
            X, _, Z = self.pier_pt(j / bays, 1, 0)
            self.post(L, float(X), float(Z), -0.004, deck - thick, 0.0085, timber * 0.8)
        for j in range(bays):
            for (ua, ya), (ub, yb) in (((j / bays, 0.006), ((j + 1) / bays, deck - thick)), ((j / bays, deck - thick), ((j + 1) / bays, 0.006))):
                pa = self.pproj(*self.pier_pt(ua, 0, ya))
                pb = self.pproj(*self.pier_pt(ub, 0, yb))
                L.line([(float(pa[0]), float(pa[1])), (float(pb[0]), float(pb[1]))], self.lit(timber * 0.8, side_n), 2.2 * s)
        L.poly(quad(0, 1, 0, 0, deck, deck - thick, 25), self.lit(timber * 0.85, side_n))
        L.line(list(zip(*self.pproj(*self.pier_pt(U, 0 * U, deck - thick + 0.002)))), self.lit(timber * 0.6, side_n), 1.2 * s)
        for j in range(bays + 1):
            X, _, Z = self.pier_pt(j / bays, -0.04, 0)
            cx, ya, yb, half = self.post(L, float(X), float(Z), -0.004, deck + 0.004, 0.0095, timber)
            # wet, weedy foot and a ring of foam where it meets the water
            _, yw = self.pproj(float(X), 0.010, float(Z))
            L.poly([(cx - half, ya), (cx + half, ya), (cx + half, yw), (cx - half, yw)], np.array([34, 44, 30]) * (self.amb + 0.3 * self.sun_str), a=0.8)
            L.ellipse(cx, ya, half * 1.4, half * 0.28, self.lit((190, 200, 206), up), a=0.3)
        # the deck: weathered planks across the pier, with dark gaps between them
        L.poly(quad(0, 1, 0, 1, deck, None, 25), self.lit(timber * 0.32, up))
        n = 64
        for k in range(n):
            u0, u1 = k / n, (k + 0.84) / n
            tone = r.uniform(0.82, 1.12)
            grey = r.uniform(0.2, 0.75)
            alb = (timber * (1 - grey) + old * grey) * tone * (1.18, 1.0, 0.9)
            L.poly(quad(u0, u1, 0.0, 1.0, deck, None, 2), self.lit(alb, up))
        L.line(list(zip(*self.pproj(*self.pier_pt(U, 0 * U, deck)))), self.lit(old * 1.15, up), 1.1 * s)
        # a ladder down to the water near the end, a life ring, and bollards
        la, lb = 0.90, 0.935
        for u in (la, lb):
            pa = self.pproj(*self.pier_pt(u, -0.05, deck + 0.012))
            pb = self.pproj(*self.pier_pt(u, -0.05, -0.004))
            L.line([(float(pa[0]), float(pa[1])), (float(pb[0]), float(pb[1]))], self.lit((70, 70, 72), side_n), 1.6 * s)
        for k in range(5):
            y = deck - (k + 0.5) * deck / 5
            pa = self.pproj(*self.pier_pt(la, -0.05, y))
            pb = self.pproj(*self.pier_pt(lb, -0.05, y))
            L.line([(float(pa[0]), float(pa[1])), (float(pb[0]), float(pb[1]))], self.lit((80, 80, 82), side_n), 1.3 * s)
        X, _, Z = self.pier_pt(0.5, -0.05, 0)
        rx, ry = self.pproj(float(X), deck - thick - 0.012, float(Z))
        rr = 5.5 * s
        for i in range(8):
            a0 = i * math.pi / 4
            c = (210, 60, 48) if i % 2 == 0 else (236, 232, 222)
            pts = [(rx + rr * math.cos(a0 + t), ry + rr * 0.95 * math.sin(a0 + t)) for t in np.linspace(0, math.pi / 4, 4)]
            L.line(pts, self.lit(c, side_n), 2.4 * s)
        for (u, v, hgt) in ((0.985, 0.92, 0.022), (0.62, 0.92, 0.018), (0.25, 0.92, 0.018)):
            X, _, Z = self.pier_pt(u, v, 0)
            self.post(L, float(X), float(Z), deck, deck + hgt, 0.0075, timber * 0.7)
        # the end post with its lantern
        X, _, Z = self.pier_pt(1.0, 0.06, 0)
        cx, ya, yb, half = self.post(L, float(X), float(Z), deck, deck + 0.105, 0.007, timber * 0.75)
        on = self.lights_on
        lx, ly = self.pier_lantern()
        L.poly([(lx - 4 * s, ly + 5 * s), (lx + 4 * s, ly + 5 * s), (lx + 4 * s, ly - 5 * s), (lx - 4 * s, ly - 5 * s)],
               self.lit((160, 160, 150), [0, 1, 0.2]) * (1 - on) + np.array([255, 205, 130]) * on)
        L.poly([(lx - 6 * s, ly - 5 * s), (lx + 6 * s, ly - 5 * s), (lx, ly - 10 * s)], self.lit((40, 38, 36), up))
        # where it meets the land: a few set stones
        for k in range(5):
            X, _, Z = self.pier_pt(-0.02 - 0.03 * k, r.uniform(-0.2, 1.2), 0)
            cx, cy = self.pproj(float(X), 0.01, float(Z))
            rs = r.uniform(7, 12) * s
            L.ellipse(float(cx), float(cy), rs, rs * 0.55, self.lit((116, 112, 104), up))
            L.ellipse(float(cx) - rs * 0.2, float(cy) - rs * 0.2, rs * 0.6, rs * 0.3, self.lit((150, 146, 138), up))
        L.composite()

    def pier_gulls(self):
        s, W, H = self.s, self.W, self.H
        perches = self.day.events.pier_gulls(self.m)
        if not perches:
            return
        xs, ys = self.pproj(*self.pier_pt(np.array([0.0, 1.0]), np.array([0.5, 0.5]), np.array([0.05, 0.05])))
        L = Layer(self, xs.min() - 30 * s, ys.min() - 60 * s, xs.max() + 30 * s, ys.max() + 20 * s)
        white = self.lit((236, 236, 232), [0, 0.8, 0.6])
        for k in perches:
            u = (0.35, 0.55, 0.72, 0.88)[k]
            gx, gy = self.pproj(*self.pier_pt(u, 0.55, PIER3["deck"]))
            gx, gy = float(gx), float(gy)
            gs = 7 * s * (1 - 0.3 * u)
            f = 1 if k % 2 else -1
            L.ellipse(gx, gy - gs * 0.9, gs, gs * 0.55, white)
            L.ellipse(gx + f * gs * 0.8, gy - gs * 1.5, gs * 0.42, gs * 0.38, white)
            L.poly([(gx - f * gs * 0.6, gy - gs * 1.2), (gx + f * gs * 0.5, gy - gs * 1.3), (gx - f * gs * 1.5, gy - gs * 0.8)], self.lit((120, 124, 132), [0, 0.8, 0.6]))
            L.line([(gx + f * gs * 1.15, gy - gs * 1.5), (gx + f * gs * 1.6, gy - gs * 1.45)], (230, 180, 60), 1.4 * s)
        L.composite()
