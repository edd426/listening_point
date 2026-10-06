"""Distant scenery: the lighthouse headland, the far coast, and the lighthouse beams."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

from core import *  # noqa: F401,F403


class DistantMixin:
    def haze_mix(self, col, haze):
        return np.asarray(col, np.float32) * (1 - haze) + self.hor_col * haze

    def headland(self):
        """The lighthouse headland across the bay: cliffs below, a patchwork of fields above, a village with
        a church, a little harbour at its foot, and the lighthouse with its keeper's cottage."""
        W, H, s = self.W, self.H, self.s
        se = self.season
        x0, x1 = 0.585, 0.815
        t = np.linspace(0, 1, 900)
        bumps = np.interp(t, np.linspace(0, 1, 1024), fnoise(4, 1024, 1.5, 1, 21)[0])
        hgt = 0.020 * sm(0, 0.2, t) + 0.009 * sm(0.3, 0.7, t) + 0.0015 * bumps * sm(0, 0.1, t)
        hgt = hgt * sm(1.0, 0.955, t)
        self.hd = (x0, x1, t, hgt)
        top = VH - hgt
        pts = [((x0 + (x1 - x0) * ti) * W, yi * H) for ti, yi in zip(t, top)] + [(x1 * W, VH * H + 1), (x0 * W, VH * H + 1)]
        L = Layer(self, x0 * W - 2, (VH - 0.04) * H, x1 * W + 2, VH * H + 2)
        L.poly(pts, (255, 255, 255))
        _, al = L.arrays()
        X = (np.arange(L.x0, L.x1, dtype=np.float32) + 0.5) / W
        Y = (np.arange(L.y0, L.y1, dtype=np.float32) + 0.5) / H
        tc = ((X - x0) / (x1 - x0))[None, :]
        hx = np.interp(tc, t, hgt) + 1e-4
        rel = (VH - Y[:, None]) / hx                         # 0 at the waterline, 1 on the skyline
        tex = fnoise(L.y1 - L.y0, L.x1 - L.x0, 1.8, 0.6, 22)
        # fields: seen almost edge-on from this far, they stack up as strips, each its own crop
        wob = 0.35 * np.interp(tc, t, bumps) + 0.2 * np.sin(tc * 23.0)
        band = rel * 6 + wob
        field = np.floor(band) * 7 + np.floor(tc * 9 + 0.5 * np.floor(band))
        fid = hash2(field, 3)
        crops = np.array([(70, 92, 58), (88, 104, 60), (62, 84, 54), (120, 118, 72)], np.float32)
        if 160 < se.doy < 240:
            crops[3] = (176, 160, 92)                         # ripe barley
        elif 240 <= se.doy < 300:
            crops[3] = (118, 96, 72)                          # ploughed
        land = crops[np.minimum((fid * 4).astype(int), 3)]
        land = land * (1 - 0.35 * se.winter) + np.array([92, 96, 76], np.float32) * 0.35 * se.winter
        land = land * (1 + 0.10 * tex)[..., None]
        hedge = sm(0.12, 0.0, np.abs((band % 1.0) - 0.5) - 0.38)
        land = land * (1 - 0.3 * hedge)[..., None]
        # low cliffs under the fields, higher toward the lighthouse end, with ledges along them
        edge = 0.16 + 0.05 * tex + 0.22 * sm(0.45, 0.85, tc) + 0.3 * sm(0.9, 0.97, tc)
        cliff = sm(edge + 0.04, edge - 0.04, rel)[..., None]
        strata = 1 + 0.10 * np.sin(rel * 55 + tex * 3)
        rock = np.array([150, 140, 122], np.float32) * strata[..., None] * (1 + 0.12 * tex)[..., None]
        alb = land * (1 - cliff) + rock * cliff
        if self.wx.snow_cover > 0.05:
            snow = (min(1.0, self.wx.snow_cover * 1.4) * (1 - cliff[..., 0] * 0.7))[..., None]
            alb = alb * (1 - snow) + np.array([232, 236, 242], np.float32) * snow
        nl = self.light(normalize([0, 0.25, 0.97]))
        nc = self.light(normalize([-0.25, 0.92, 0.3]))
        col = alb * (nl * (1 - cliff) + nc * cliff)
        haze = 0.5 - 0.15 * self.night
        col = col * (1 - haze) + self.hor_col * haze * (0.9 + 0.1 * (Y[:, None] - VH + 0.04) / 0.04)[..., None]
        self.over(L.y0, L.y1, L.x0, L.x1, col, al)

        def ground(ti):
            return (VH - np.interp(ti, t, hgt) * 0.98) * H

        r = np.random.default_rng(23)
        L = Layer(self, x0 * W - 30 * s, (VH - 0.045) * H, x1 * W + 2, VH * H + 6 * s)
        treec = self.haze_mix(self.lit((44, 62, 40) if se.leaves > 0.3 else (70, 62, 52), (0, 0.5, 0.9)), haze * 0.7)
        for _ in range(80):
            ti = r.uniform(0.12, 0.9)
            if abs(ti - (LH_X - x0) / (x1 - x0)) < 0.05 or 0.18 < ti < 0.42:
                continue
            L.ellipse((x0 + (x1 - x0) * ti) * W, ground(ti) + 1.5 * s, r.uniform(3, 7) * s, r.uniform(3, 6) * s, treec)
        # the village climbs the slope above the harbour, around its church
        wall = self.haze_mix(self.lit((226, 220, 206), (0, 1, 0.2)), haze * 0.6)
        roofs = [self.haze_mix(self.lit(c, (0, 0.6, 0.8)), haze * 0.6) for c in ((150, 70, 50), (96, 92, 96), (132, 84, 60))]
        houses = []
        for i in range(34):
            ti = r.uniform(0.05, 0.45)
            depth = r.uniform(0.0, 0.55)
            hy = ground(ti) + depth * np.interp(ti, t, hgt) * H * 0.75
            hs = r.uniform(3.5, 6.5) * s * (1 + 0.3 * depth)
            houses.append(((x0 + (x1 - x0) * ti) * W, hy, hs, int(r.integers(3)), r.uniform(21.3, 25.2), r.random() < 0.12))
        houses.sort(key=lambda h: h[1])
        for hxx, hy, hs, rc, _, _ in houses:
            L.poly([(hxx - hs, hy), (hxx + hs, hy), (hxx + hs, hy - hs * 0.8), (hxx - hs, hy - hs * 0.8)], wall)
            L.poly([(hxx - hs * 1.15, hy - hs * 0.8), (hxx + hs * 1.15, hy - hs * 0.8), (hxx + hs * 0.6, hy - hs * 1.35), (hxx - hs * 0.6, hy - hs * 1.35)], roofs[rc])
        cxh = (x0 + (x1 - x0) * 0.27) * W
        cyh = ground(0.27) + 6 * s
        L.poly([(cxh - 9 * s, cyh), (cxh + 9 * s, cyh), (cxh + 9 * s, cyh - 10 * s), (cxh - 9 * s, cyh - 10 * s)], wall)
        L.poly([(cxh + 3 * s, cyh - 10 * s), (cxh + 9 * s, cyh - 10 * s), (cxh + 9 * s, cyh - 22 * s), (cxh + 3 * s, cyh - 22 * s)], wall)
        L.poly([(cxh + 2.5 * s, cyh - 22 * s), (cxh + 9.5 * s, cyh - 22 * s), (cxh + 6 * s, cyh - 36 * s)], roofs[1])
        L.poly([(cxh - 10 * s, cyh - 10 * s), (cxh + 3 * s, cyh - 10 * s), (cxh - 3.5 * s, cyh - 16 * s)], roofs[1])
        # the harbour: a breakwater curling out from the foot of the headland, boats inside it
        bx0 = x0 * W
        stone = self.haze_mix(self.lit((140, 134, 124), (0, 0.8, 0.6)), haze * 0.7)
        bw = [(bx0 + 8 * s, VH * H + 1.5 * s), (bx0 - 10 * s, VH * H + 2.5 * s), (bx0 - 26 * s, VH * H + 2 * s), (bx0 - 34 * s, VH * H + 0.5 * s)]
        L.line(bw, stone, 2.4 * s)
        L.poly([(bw[-1][0] - 2 * s, bw[-1][1]), (bw[-1][0] + 2 * s, bw[-1][1]), (bw[-1][0] + 1.5 * s, bw[-1][1] - 7 * s), (bw[-1][0] - 1.5 * s, bw[-1][1] - 7 * s)],
               self.haze_mix(self.lit((220, 218, 210), (0, 1, 0.3)), haze * 0.6))
        boat = self.haze_mix(self.lit((232, 232, 228), (0, 1, 0.3)), haze * 0.5)
        for k in range(4):
            bxk = bx0 - (5 + 6 * k + 2 * (k % 2)) * s
            L.line([(bxk - 2 * s, VH * H + 1 * s), (bxk + 2 * s, VH * H + 1 * s)], boat, 1.4 * s)
            L.line([(bxk, VH * H + 0.5 * s), (bxk, VH * H - (3 + 2 * (k % 3)) * s)], boat * 0.7, 0.4 * s, a=0.7)
        # the keeper's cottage beside the lighthouse
        tl = (LH_X - x0) / (x1 - x0)
        kx, ky = LH_X * W - 16 * s, ground(tl - 0.02) + 2 * s
        L.poly([(kx - 8 * s, ky), (kx + 6 * s, ky), (kx + 6 * s, ky - 6 * s), (kx - 8 * s, ky - 6 * s)], wall)
        L.poly([(kx - 9 * s, ky - 6 * s), (kx + 7 * s, ky - 6 * s), (kx - 1 * s, ky - 11 * s)], roofs[1])
        L.composite()
        on = self.lights_on
        if on > 0:
            for hxx, hy, hs, rc, bed, porch in houses:
                # people go to bed one house at a time; a few porch lights burn all night
                if self.t >= 12:
                    up = self.t < bed
                else:
                    up = (bed > 24 and self.t < bed - 24) or self.t > self.day.events.wake + 0.6 * float(hash2(hxx, 1))
                if not (up or porch):
                    continue
                k = on * (0.6 + 0.4 * hash2(hxx, hy))
                self.glow(hxx + (hash2(hy, 2) - 0.5) * hs, hy - 0.35 * hs, 1.6 * s, (255, 200, 120), 1.3 * k)
                self.glow(hxx, hy - 0.35 * hs, 6 * s, (255, 170, 90), 0.10 * k)
                self.emitters.append((hxx, hy, np.array([255, 190, 110], np.float32), 0.3 * k, self.hz))
            hl = bw[-1]
            self.glow(hl[0], hl[1] - 7 * s, 1.6 * s, (90, 255, 120), 1.4 * on)
            self.emitters.append((hl[0], hl[1] - 7 * s, np.array([90, 255, 120], np.float32), 0.5 * on, self.hz))
            self.glow(kx, ky - 3 * s, 1.4 * s, (255, 200, 120), 1.0 * on * self.windows_lit)

        # the lighthouse
        by = (VH - np.interp(tl, t, hgt)) * H + 2 * s
        lx = LH_X * W
        hgt_l = 0.050 * H

        def lh_albedo(sv, v, X, Y, r):
            red = ((v > 0.18) & (v < 0.32)) | ((v > 0.52) & (v < 0.66))
            a = np.where(red[..., None], np.array([178, 52, 44], np.float32), np.array([238, 236, 230], np.float32))
            return a * (1 - 0.12 * sv ** 2)[..., None]
        self.cylinder(lx, by - hgt_l, by, 8 * s, 11 * s, lh_albedo, haze=haze * 0.8, local=False)
        ty = by - hgt_l
        L = Layer(self, lx - 20 * s, ty - 30 * s, lx + 20 * s, ty + 4 * s)
        dark = self.lit((40, 38, 40), (0, 1, 0)) * (1 - haze * 0.5) + self.hor_col * haze * 0.5
        L.poly([(lx - 11 * s, ty + 1 * s), (lx + 11 * s, ty + 1 * s), (lx + 11 * s, ty - 2 * s), (lx - 11 * s, ty - 2 * s)], dark)
        glass = (self.lit((70, 80, 92), (0, 1, 0.3)) * (1 - self.night) + np.array([255, 236, 200]) * self.night)
        L.poly([(lx - 6 * s, ty - 2 * s), (lx + 6 * s, ty - 2 * s), (lx + 6 * s, ty - 13 * s), (lx - 6 * s, ty - 13 * s)], glass)
        L.poly([(lx - 8 * s, ty - 13 * s), (lx + 8 * s, ty - 13 * s), (lx, ty - 21 * s)], dark)
        L.composite()
        self.lamp_lh = (lx, ty - 7.5 * s)

    def far_coast(self):
        """The far shore to the south-east: two ranges of low hills in the haze, a town on the nearer one, and
        the islets offshore, one with an empty cottage."""
        W, H, s = self.W, self.H, self.s
        x0, x1 = 0.15, 0.52
        t = np.linspace(0, 1, 600)
        L = Layer(self, 0.03 * W, (VH - 0.03) * H, 0.58 * W, VH * H + 2)
        back = (0.009 + 0.006 * np.interp(t, np.linspace(0, 1, 1024), fnoise(4, 1024, 2.6, 1, 27)[1])) * sm(0.05, 0.3, t) * sm(0.95, 0.7, t)
        pts = [((x0 + (x1 - x0) * ti) * W, (VH - hi) * H) for ti, hi in zip(t, back)] + [(x1 * W, VH * H + 1), (x0 * W, VH * H + 1)]
        haze = 0.82 - 0.2 * self.night
        L.poly(pts, self.haze_mix(self.lit((76, 90, 80), (0, 0.3, 0.95)), haze))
        hgt = (0.006 + 0.004 * np.interp(t, np.linspace(0, 1, 1024), fnoise(4, 1024, 2.2, 1, 25)[1])) * sm(0, 0.15, t) * sm(1, 0.8, t)
        pts = [((x0 + (x1 - x0) * ti) * W, (VH - hi) * H) for ti, hi in zip(t, hgt)] + [(x1 * W, VH * H + 1), (x0 * W, VH * H + 1)]
        haze = 0.72 - 0.2 * self.night
        L.poly(pts, self.haze_mix(self.lit((70, 84, 70), (0, 0.3, 0.95)), haze))
        r = np.random.default_rng(26)
        town = []
        for _ in range(26):
            ti = r.uniform(0.55, 0.72)
            hy = (VH - np.interp(ti, t, hgt) * r.uniform(0.2, 0.8)) * H
            town.append(((x0 + (x1 - x0) * ti) * W, hy))
            L.ellipse(town[-1][0], hy, 1.6 * s, 1.0 * s, self.haze_mix(self.lit((220, 216, 206), (0, 1, 0.3)), haze * 0.8))
        # islets, and the cottage on the outermost one
        rock = self.haze_mix(self.lit((96, 92, 84), (0, 0.6, 0.8)), haze * 0.85)
        for (ix, iw, ih) in ((0.055, 0.010, 0.0035), (0.072, 0.004, 0.0018), (0.535, 0.006, 0.0022), (0.56, 0.003, 0.0012)):
            L.poly([(ix * W - iw * W, VH * H + 1), (ix * W - iw * W * 0.4, (VH - ih) * H), (ix * W + iw * W * 0.3, (VH - ih * 1.1) * H),
                    (ix * W + iw * W, VH * H + 1)], rock)
        cx_, cy_ = 0.057 * W, (VH - 0.0035) * H
        L.poly([(cx_ - 4 * s, cy_ + 1 * s), (cx_ + 4 * s, cy_ + 1 * s), (cx_ + 4 * s, cy_ - 4 * s), (cx_ - 4 * s, cy_ - 4 * s)],
               self.haze_mix(self.lit((200, 196, 186), (0, 1, 0.3)), haze * 0.7))
        L.poly([(cx_ - 5 * s, cy_ - 4 * s), (cx_ + 5 * s, cy_ - 4 * s), (cx_, cy_ - 8 * s)], rock)
        self.cottage = (cx_, cy_ - 1.5 * s)
        L.composite()
        if self.lights_on > 0:
            for i, (tx, ty) in enumerate(town):
                if self.t > 1.5 and self.t < 5.5 and i % 3:      # the town sleeps in the small hours
                    continue
                self.glow(tx, ty, 1.0 * s, (255, 170, 80), 0.9 * self.lights_on)
                self.emitters.append((tx, ty, np.array([255, 170, 80], np.float32), 0.12 * self.lights_on, self.hz))

    def ships(self):
        """Ships passing along the horizon, hull down in the haze; lit at night."""
        ships = self.day.events.ship_positions(self.t)
        if not ships:
            return
        s, W, H, hz = self.s, self.W, self.H, self.hz
        haze = 0.55 - 0.15 * self.night
        L = Layer(self, 0, hz - 40 * s, W, hz + 4 * s)
        lights = []
        for (xn, d, kind) in ships:
            x, y = xn * W, hz + 1 * s
            def tone(c):
                return self.lit(c, (0, 1, 0.3)) * (1 - haze) + self.hor_col * haze
            if kind == "tall":
                L.poly([(x - 16 * s, y), (x + 16 * s, y), (x + 13 * s, y - 4 * s), (x - 14 * s, y - 4 * s)], tone((50, 40, 34)))
                for mx in (-8, 0, 8):
                    L.line([(x + mx * s, y - 4 * s), (x + mx * s, y - 30 * s)], tone((50, 40, 34)), 0.8 * s)
                    for k in range(3):
                        L.poly([(x + (mx - 4) * s, y - (8 + 8 * k) * s), (x + (mx + 4) * s, y - (8 + 8 * k) * s),
                                (x + (mx + 3.5) * s, y - (14 + 8 * k) * s), (x + (mx - 3.5) * s, y - (14 + 8 * k) * s)], tone((226, 220, 204)))
                lights.append((x + d * 14 * s, y - 6 * s))
            elif kind == "ferry":
                L.poly([(x - 22 * s, y), (x + 22 * s, y), (x + 24 * s, y - 6 * s), (x - 20 * s, y - 6 * s)], tone((230, 230, 226)))
                L.poly([(x - 14 * s, y - 6 * s), (x + 12 * s, y - 6 * s), (x + 9 * s, y - 13 * s), (x - 11 * s, y - 13 * s)], tone((236, 236, 232)))
                L.line([(x - 18 * s, y - 3 * s), (x + 21 * s, y - 3 * s)], tone((40, 60, 120)), 1.2 * s)
                L.poly([(x - 2 * s, y - 13 * s), (x + 3 * s, y - 13 * s), (x + 3 * s, y - 18 * s), (x - 2 * s, y - 18 * s)], tone((190, 50, 40)))
                lights.append((x, y - 15 * s))
            else:
                L.poly([(x - 30 * s, y), (x + 30 * s, y), (x + 32 * s, y - 5 * s), (x - 31 * s, y - 5 * s)], tone((70, 52, 50)))
                for k in range(5):
                    L.poly([(x + (-22 + 9 * k) * s, y - 5 * s), (x + (-15 + 9 * k) * s, y - 5 * s),
                            (x + (-15 + 9 * k) * s, y - 10 * s), (x + (-22 + 9 * k) * s, y - 10 * s)], tone([(150, 60, 50), (60, 90, 140), (170, 150, 70)][k % 3]))
                bx = x - d * 25 * s
                L.poly([(bx - 5 * s, y - 5 * s), (bx + 5 * s, y - 5 * s), (bx + 5 * s, y - 15 * s), (bx - 5 * s, y - 15 * s)], tone((230, 230, 224)))
                lights.append((bx, y - 17 * s))
        L.composite()
        if self.lights_on > 0:
            for (lx, ly) in lights:
                self.glow(lx, ly, 1.6 * s, (255, 250, 235), 1.2 * self.lights_on)
                self.glow(lx, ly + 3 * s, 1.2 * s, (255, 70, 60) if (lx * 7) % 2 > 1 else (80, 255, 120), 0.8 * self.lights_on)
                self.emitters.append((lx, ly, np.array([255, 240, 220], np.float32), 0.25 * self.lights_on, self.hz))

    def beams(self):
        if self.sun_alt > -2.5:
            return
        k = sm(-2.5, -9, self.sun_alt)
        s, W, H = self.s, self.W, self.H
        lx, ly = self.lamp_lh
        phi = self.day.events.beam_angle(self.m)
        colr = np.array([255, 206, 160], np.float32)
        for p in (phi, phi + math.pi):
            dx, dy = math.cos(p), 0.05 * math.sin(p)
            nrm = math.hypot(dx, dy)
            dx, dy = dx / nrm, dy / nrm
            reach = 0.30 * W * (0.25 + 0.75 * abs(math.cos(p)))
            ex = lx + dx * reach * 2.5
            x0, x1 = int(max(0, min(lx, ex) - 60 * s)), int(min(W, max(lx, ex) + 60 * s))
            y0, y1 = int(max(0, ly - 0.14 * H)), int(min(self.hz, ly + 0.10 * H))
            X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5 - lx
            Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - ly
            along = X * dx + Y * dy
            perp = np.abs(-X * dy + Y * dx)
            width = 3 * s + np.maximum(along, 0) * 0.035
            I = np.exp(-(perp / width) ** 2) * np.exp(-np.maximum(along, 0) / reach) * sm(0, 25 * s, along)
            # fade to nothing before the edges of the box, so it never shows as a rectangle
            Xa, Ya = X + lx, Y + ly
            I = I * sm(x0, x0 + 50 * s, Xa) * sm(x1, x1 - 50 * s, Xa) * sm(y0, y0 + 40 * s, Ya) * sm(y1, y1 - 2 * s, Ya)
            self.c[y0:y1, x0:x1] += I[..., None] * colr * 0.28 * k
        toward = abs(math.sin(phi)) ** 3
        self.glow(lx, ly, 3.5 * s, (255, 240, 215), 1.6 * k)
        self.glow(lx, ly, 26 * s, colr, (0.18 + 0.5 * toward) * k, tail=0.3)
        self.emitters.append((lx, ly, colr, (0.9 + 0.8 * toward) * k, self.hz))
