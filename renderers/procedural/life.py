"""Living things and night lights: sheep, moths, fireflies, glows."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

from core import *  # noqa: F401,F403


class LifeMixin:
    def persp(self, y):
        return 0.35 + 1.3 * min(1.0, max(0.0, (y / self.H - 0.6) / 0.4))

    # ---------------------------------------------------------------- sheep --
    def sheep(self):
        s, W, H = self.s, self.W, self.H
        se = self.season
        flock = self.day.events.sheep(self.t, lambs=se.lambs)
        for i, (x, y, f, grazing, size) in enumerate(flock):
            x, y = x * W, y * H
            lamb = size < 1
            k = 30 * s * self.persp(y) * size
            standing = self.sun_alt > -4 or lamb
            shorn = se.shorn and not lamb
            fleece = np.array((242, 238, 228) if lamb else (204, 198, 186) if shorn else (228, 224, 212), np.float32)
            face = self.lit((40, 36, 34), [f * -0.3, 0.8, 0.4], x, y)
            L = Layer(self, x - 2 * k, y - 2.2 * k, x + 2 * k, y + k)
            L.ellipse(x, y + 0.08 * k, 1.15 * k, 0.24 * k, np.array([24, 32, 20]) * (self.amb + 0.25), a=0.5)
            lift = 0.55 * k if standing else 0.08 * k
            if standing:
                for lx in (-0.55, -0.32, 0.38, 0.6):
                    L.line([(x + lx * k, y - lift), (x + lx * k + 0.04 * k * f, y)], face * 0.9, 0.15 * k)
            bw = 0.85 if shorn else 1.0
            by = y - lift - 0.45 * k
            L.ellipse(x, by, 1.0 * k * bw, 0.55 * k * bw, self.lit(fleece * 0.8, [0, 0.7, 0.5], x, y))
            r = np.random.default_rng(700 + i)
            for _ in range(16 if not shorn else 9):   # tufts of fleece, each lit as a little dome
                dx, dy = r.uniform(-0.8, 0.8) * bw, r.uniform(-0.48, 0.25) * bw
                nrm = normalize([-dx * 0.8, 0.55, -dy * 1.2 + 0.35])
                rr = r.uniform(0.22, 0.34) * k * bw
                L.ellipse(x + dx * k, by + dy * k, rr, rr * 0.85, self.lit(fleece * r.uniform(0.92, 1.05), nrm, x, y))
            hx, hy = x + f * 0.92 * k * bw, by + (0.38 * k if grazing else -0.18 * k)
            L.ellipse(hx, hy, 0.27 * k, 0.21 * k, face)
            L.ellipse(hx + f * 0.18 * k, hy + 0.05 * k, 0.16 * k, 0.12 * k, face)
            for e in (-1, 1):   # ears out sideways
                L.ellipse(hx - f * 0.12 * k + e * 0.2 * k, hy - 0.12 * k, 0.13 * k, 0.05 * k, face)
            L.composite()

    # ------------------------------------------------------------------ cat --
    def cat_spot(self, spot, seeds):
        """Screen position (x, y) of the cat's feet, and the pose, for a named spot."""
        s, W, H = self.s, self.W, self.H
        a, b = seeds
        if spot == "wall":
            t = 0.25 + 0.6 * a
            p0, p1, p2, p3 = [np.array(v) for v in ((-0.02, 0.742), (0.04, 0.76), (0.10, 0.79), (0.148, 0.812))]
            x, y = (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3
            x, y = x * W, y * H
            return x, y - 27 * s * self.persp(y), "sit"
        if spot == "step":
            return self.tw["cx"] + 30 * s, self.tw["yb"] + 18 * s, "sit"
        if spot == "bench":
            return BENCH[0] * W - 40 * s + 70 * s * a, BENCH[1] * H - 40 * s, "curl"
        if spot == "lamp":
            return LAMP[0] * W + 18 * s, LAMP[1] * H + 4 * s, "sit"
        if spot == "grass":
            return (0.27 + 0.16 * a) * W, (0.745 + 0.06 * b) * H, "crouch"
        return None

    def cat(self):
        s = self.s
        spot, prev, since, seeds, pseeds = self.day.events.cat_at(self.m)
        here = self.cat_spot(spot, seeds)
        there = self.cat_spot(prev, pseeds)
        walk = 5
        if here is None and there is None:
            return
        if since < walk and here and there and prev != spot:
            u = (since + 0.5) / walk
            x, y = there[0] + (here[0] - there[0]) * u, there[1] + (here[1] - there[1]) * u
            pose, f = "walk", (1 if here[0] > there[0] else -1)
        elif here is None:
            return
        else:
            x, y, pose = here
            f = 1 if (seeds[0] * 10) % 2 > 1 else -1
        k = 30 * s * self.persp(y) * 0.36
        fur = self.lit((30, 28, 30), [0, 0.8, 0.5], x, y)
        rim = self.lit((60, 56, 58), [f * -0.6, 0.4, 0.7], x, y)
        L = Layer(self, x - 3 * k, y - 3.4 * k, x + 3 * k, y + 0.6 * k)
        L.ellipse(x, y + 0.05 * k, 1.0 * k, 0.18 * k, np.array([20, 24, 18]) * (self.amb + 0.25), a=0.45)
        if pose == "sit":
            L.ellipse(x, y - 0.9 * k, 0.62 * k, 0.95 * k, fur)
            L.line([(x - f * 0.5 * k, y - 0.1 * k), (x - f * 1.1 * k, y - 0.05 * k), (x - f * 1.3 * k, y - 0.4 * k)], fur, 0.16 * k)
            hx, hy = x + f * 0.1 * k, y - 2.0 * k
        elif pose == "curl":
            L.ellipse(x, y - 0.35 * k, 1.0 * k, 0.42 * k, fur)
            L.ellipse(x + 0.2 * k * f, y - 0.42 * k, 0.75 * k, 0.32 * k, rim)
            hx, hy = x + f * 0.75 * k, y - 0.45 * k
        elif pose == "crouch":
            L.ellipse(x, y - 0.45 * k, 1.0 * k, 0.42 * k, fur)
            L.line([(x - f * 0.9 * k, y - 0.4 * k), (x - f * 1.7 * k, y - 0.25 * k)], fur, 0.16 * k)
            hx, hy = x + f * 1.0 * k, y - 0.6 * k
        else:   # walking: body level, legs under it, tail up and curling
            L.ellipse(x, y - 0.75 * k, 1.05 * k, 0.38 * k, fur)
            ph = self.m % 2
            for lx in (-0.7, -0.45, 0.45, 0.7):
                L.line([(x + lx * k, y - 0.6 * k), (x + lx * k + (0.12 if ph else -0.12) * k * (1 if lx > 0 else -1), y)], fur, 0.16 * k)
            L.line([(x - f * 0.95 * k, y - 0.85 * k), (x - f * 1.25 * k, y - 1.6 * k), (x - f * 1.05 * k, y - 1.9 * k)], fur, 0.16 * k)
            hx, hy = x + f * 1.15 * k, y - 1.1 * k
        L.ellipse(hx, hy, 0.42 * k, 0.36 * k, fur)
        for e in (-1, 1):
            ex = hx + e * 0.24 * k
            L.poly([(ex - 0.14 * k, hy - 0.2 * k), (ex + 0.14 * k, hy - 0.2 * k), (ex + e * 0.06 * k, hy - 0.62 * k)], fur)
        L.composite()
        # eyes: a glint of green-gold when a lamp is near, as a cat's do
        if pose != "curl":
            near = self.lights_on * (1.0 if spot in ("lamp", "step") or pose == "walk" else 0.4)
            ec = np.array([200, 220, 90], np.float32)
            for e in (-1, 1):
                ex, ey = hx + e * 0.15 * k + f * 0.05 * k, hy - 0.02 * k
                if near > 0.05:
                    self.glow(ex, ey, 0.9 * s, ec, 1.6 * near)
                else:
                    self.glow(ex, ey, 0.5 * s, ec * 0.6, 0.5 * (1 - self.night))

    # ---------------------------------------------------------------- heron --
    def heron(self):
        ev = self.day.events
        if not ev.heron or not (ev.sunrise - 0.3 < self.t < ev.sunrise + 1.3) or self.wx.rain > 0.3:
            return
        s, W, H = self.s, self.W, self.H
        xn = ev.heron_x + 0.004 * math.sin(self.m * 0.05)
        x = xn * W
        y = (water_line(np.array([xn]), self.tide)[0] - 0.006) * H
        k = 30 * s * self.persp(y) * 0.5
        grey = self.lit((150, 154, 162), [0, 0.8, 0.5], x, y)
        white = self.lit((226, 228, 230), [0, 0.8, 0.5], x, y)
        dark = self.lit((40, 40, 46), [0, 0.8, 0.5], x, y)
        bill = self.lit((210, 170, 70), [0, 0.8, 0.5], x, y)
        f = -1 if xn > 0.85 else 1
        L = Layer(self, x - 3 * k, y - 5 * k, x + 3 * k, y + 0.6 * k)
        L.line([(x - 0.15 * k, y), (x - 0.1 * k, y - 1.5 * k)], dark, 0.1 * k)
        L.line([(x + 0.15 * k, y), (x + 0.1 * k, y - 1.5 * k)], dark, 0.1 * k)
        L.ellipse(x, y - 1.9 * k, 0.75 * k, 0.45 * k, grey)
        L.poly([(x - f * 0.5 * k, y - 2.1 * k), (x - f * 1.2 * k, y - 1.7 * k), (x - f * 0.4 * k, y - 1.6 * k)], dark)
        hunting = (self.m // 7) % 3 == 0
        nx = x + f * (0.9 if hunting else 0.4) * k
        ny = y - (2.7 if hunting else 3.2) * k
        L.line([(x + f * 0.4 * k, y - 2.1 * k), (x + f * 0.55 * k, y - 2.7 * k), (nx, ny)], white, 0.22 * k)
        L.ellipse(nx, ny, 0.22 * k, 0.17 * k, white)
        L.line([(nx - f * 0.1 * k, ny - 0.1 * k), (nx - f * 0.55 * k, ny - 0.02 * k)], dark, 0.06 * k)
        L.line([(nx + f * 0.18 * k, ny), (nx + f * 0.85 * k, ny + (0.25 if hunting else 0.05) * k)], bill, 0.08 * k)
        L.composite()
        # its reflection, broken by the ripples
        R = Layer(self, x - 3 * k, y, x + 3 * k, y + 4 * k)
        R.line([(x, y), (x + f * 0.2 * k, y + 1.4 * k)], grey * 0.5, 0.4 * k, a=0.35)
        R.ellipse(x, y + 1.9 * k, 0.6 * k, 0.35 * k, grey * 0.5, a=0.3)
        R.composite()

    # ------------------------------------------------------------------ owl --
    def owl(self):
        ev = self.day.events
        t = self.t
        if not ev.owl or self.sun_alt > -8 or not (t > ev.owl_from or t < ev.owl_to):
            return
        s, W, H = self.s, self.W, self.H
        x, y = (CANOPY[0] - 0.052) * W, (CANOPY[1] + 0.085) * H
        k = 6.5 * s
        body = self.lit((86, 70, 56), [0, 0.8, 0.5], x, y) * (0.6 + 0.4 * self.season.leaves * 0)
        L = Layer(self, x - 3 * k, y - 4 * k, x + 3 * k, y + 2 * k)
        L.ellipse(x, y - 1.3 * k, 0.95 * k, 1.35 * k, body)
        L.ellipse(x, y - 2.6 * k, 0.85 * k, 0.75 * k, body * 1.1)
        L.composite()
        turned = (self.m // 9) % 3 == 1       # now and then it looks away
        if not turned:
            for e in (-1, 1):
                self.glow(x + e * 0.35 * k, y - 2.65 * k, 0.55 * s, (255, 210, 90), 0.4 + 0.9 * self.lights_on * 0.5)

    # ----------------------------------------------------------- small life --
    def critters(self):
        """Bats at dusk, rabbits at dawn and dusk, swallows and butterflies in summer."""
        s, W, H, t = self.s, self.W, self.H, self.t
        ev, se, wx = self.day.events, self.season, self.wx
        r = self.rng
        fair = wx.rain < 0.05 and wx.snow < 0.05 and wx.wind_ms < 9
        L = Layer(self, 0, 0.3 * H, W, H)
        drew = False
        if se.bats > 0.3 and fair and wx.temp_c > 8 and ev.sunset + 0.15 < t < ev.sunset + 1.3:
            c = np.array([18, 16, 20], np.float32)
            for _ in range(3):
                bx, by = r.uniform(0.36, 0.6) * W, r.uniform(0.38, 0.6) * H
                w = r.uniform(5, 8) * s
                up = r.uniform(-0.6, 0.8)
                L.line([(bx - w, by - up * w * 0.5), (bx - w * 0.4, by - w * 0.35), (bx, by), (bx + w * 0.4, by - w * 0.35), (bx + w, by - up * w * 0.5)], c, 1.3 * s)
                drew = True
        dawn_dusk = (ev.sunrise - 0.4 < t < ev.sunrise + 1.2) or (ev.sunset - 1.0 < t < ev.sunset + 0.3)
        if dawn_dusk and se.winter < 0.5 and fair:
            rr = np.random.default_rng([self.day.date.toordinal(), 11])
            for i in range(int(rr.integers(1, 4))):
                x = (0.14 + 0.2 * rr.random()) * W + 3 * s * math.sin(self.m * 0.4 + i)
                y = (0.83 + 0.07 * rr.random()) * H
                k = 30 * s * self.persp(y) * 0.22
                fur = self.lit((112, 88, 64), [0, 0.8, 0.5], x, y)
                f = 1 if (self.m // 5 + i) % 2 else -1
                L.ellipse(x, y - 0.5 * k, 1.0 * k, 0.6 * k, fur)
                L.ellipse(x + f * 0.8 * k, y - 0.95 * k, 0.45 * k, 0.4 * k, fur)
                for e in (0, 1):
                    L.ellipse(x + f * (0.65 + 0.2 * e) * k, y - 1.65 * k, 0.12 * k, 0.45 * k, fur * 0.9)
                L.ellipse(x - f * 0.95 * k, y - 0.5 * k, 0.22 * k, 0.2 * k, self.lit((230, 228, 222), [0, 0.8, 0.5], x, y))
                drew = True
        if se.swallows > 0.3 and fair and self.sun_alt > 8:
            c = self.lit((28, 34, 60), [0, 0.5, 0.8])
            for _ in range(5):
                bx, by = r.uniform(0.2, 0.95) * W, r.uniform(0.55, 0.78) * H
                w = r.uniform(5, 8) * s
                d = r.choice([-1, 1])
                L.line([(bx - w, by - 0.4 * w), (bx, by), (bx + w, by - 0.4 * w)], c, 1.4 * s)
                L.line([(bx - d * 0.2 * w, by), (bx - d * 0.9 * w, by + 0.3 * w)], c, 0.9 * s)
                drew = True
        if 120 < se.doy < 265 and fair and self.sun_vis > 0.5 and wx.temp_c > 16:
            for _ in range(4):
                bx, by = r.uniform(0.05, 0.7) * W, r.uniform(0.72, 0.95) * H
                if by < self.edge(bx / W) * H + 10 * s:
                    continue
                c = [(236, 236, 226), (240, 200, 60), (214, 120, 50), (150, 160, 220)][int(r.integers(4))]
                w = 3 * s * self.persp(by)
                for e in (-1, 1):
                    L.poly([(bx, by), (bx + e * w, by - w * r.uniform(0.3, 1.0)), (bx + e * w * 0.8, by + w * 0.3)], self.lit(c, [0, 0.6, 0.8]))
                drew = True
        if drew:
            L.composite()

    def night_lights(self):
        s, on = self.s, self.lights_on
        if on <= 0:
            return
        for wx, wy in (self.win_pos if self.windows_lit > 0.05 else []):
            self.glow(wx, wy - 10 * s, 26 * s, (255, 176, 96), 0.28 * self.windows_lit, tail=0.25)
        self.glow(self.tw["cx"], CLOCK["y"] * self.H, CLOCK["R"] * s * 1.15, (255, 222, 170), 0.16 * on, tail=0.2)
        dx, dy = self.door_lantern
        self.glow(dx, dy, 5 * s, (255, 226, 170), 1.2 * on)
        self.glow(dx, dy, 55 * s, (255, 176, 96), 0.28 * on, tail=0.3)
        lx, ly = self.lamp_pos
        self.glow(lx, ly, 9 * s, (255, 232, 180), 1.4 * on)
        self.glow(lx, ly, 90 * s, (255, 180, 100), 0.30 * on, tail=0.35)
        px, py = self.pier_lantern()
        self.glow(px, py, 4 * s, (255, 226, 170), 1.3 * on)
        self.glow(px, py, 40 * s, (255, 176, 96), 0.25 * on, tail=0.3)
        r = self.rng
        for _ in range(3 if 100 < self.season.doy < 290 and self.wx.temp_c > 8 else 0):   # moths around the lamp
            mx, my = lx + r.normal(0, 22 * s), ly + r.normal(0, 18 * s)
            self.glow(mx, my, 1.6 * s, (255, 230, 190), 0.9 * on)
        if self.observing:
            cx, cy, R = self.tw["cx"], self.tw["yt"] - 16 * s, self.tw["r"]
            th = self.scope_theta
            self.glow(cx + math.cos(th) * R * 0.6, cy - math.sin(th) * R * 0.6, 20 * s, (200, 50, 36), 0.25)
        if self.dark > 0.5 and self.season.fireflies > 0.05 and self.wx.temp_c > 14 and self.wx.rain < 0.05:   # fireflies
            for _ in range(int(22 * self.season.fireflies)):
                fx, fy = r.uniform(0.36, 0.64), r.uniform(0.66, 0.84)
                if fy < self.edge(fx) + 0.01:
                    continue
                self.glow(fx * self.W, fy * self.H, 1.8 * s, (210, 255, 130), 1.3)
                self.glow(fx * self.W, fy * self.H, 9 * s, (170, 230, 100), 0.18)
