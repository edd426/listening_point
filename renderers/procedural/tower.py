"""The observatory tower: masonry, dome, telescope, windows, door and clock."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

import astro
from core import *  # noqa: F401,F403
from stars import STAR_DEC, STAR_MAG, STAR_RA


class TowerMixin:
    def cylinder(self, cx, yt, yb, rt, rb, albedo_fn, haze=0.0, local=True, ell_k=1.2):
        rmax = max(rt, rb)
        et = ell_k * (yt / self.H - VH) * rt
        eb = ell_k * (yb / self.H - VH) * rb
        x0, x1 = int(max(0, cx - rmax - 2)), int(min(self.W, cx + rmax + 3))
        y0, y1 = int(max(0, yt - abs(et) - 3)), int(min(self.H, yb + abs(eb) + 3))
        X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5
        Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5
        v0 = np.clip((Y - yt) / (yb - yt), 0, 1)
        r = rt + (rb - rt) * v0
        dx = X - cx
        sv = np.clip(dx / r, -1, 1)
        cv = np.sqrt(1 - sv ** 2)
        top, bot = yt + et * cv, yb + eb * cv
        cov = np.clip(r - np.abs(dx) + 0.5, 0, 1) * np.clip(Y - top + 0.5, 0, 1) * np.clip(bot - Y + 0.5, 0, 1)
        v = np.clip((Y - top) / (bot - top), 0, 1)
        alb = albedo_fn(sv, v, X, Y, r)
        nrm = np.stack([-sv, cv, np.zeros_like(sv)], -1)
        L = self.light(nrm) * (0.8 + 0.2 * cv)[..., None]
        if local and self.pools:
            L = L + self.local(X, Y)
        col = alb * L
        if haze:
            col = col * (1 - haze) + self.hor_col * haze
        self.over(y0, y1, x0, x1, col, cov[..., None])

    def tower(self):
        s, W, H = self.s, self.W, self.H
        tw = self.tw
        cx, yb, yt, r = tw["cx"], tw["yb"], tw["yt"], tw["r"]
        tex = fnoise(512, 512, 2.0, 1.0, 71)
        tex2 = fnoise(512, 512, 1.4, 1.0, 72)

        def stone(sv, v, X, Y, rr):
            arc = np.arcsin(sv) * rr
            hp = v * (yb - yt)
            ch, sw = 21 * s, 46 * s
            ci = np.floor(hp / ch)
            fy = hp / ch - ci
            sx = (arc + hash2(ci, 7) * sw) / sw
            si = np.floor(sx)
            fx = sx - si
            tint = hash2(ci, si)
            ep = np.minimum(np.minimum(fy, 1 - fy) * ch, np.minimum(fx, 1 - fx) * sw * np.sqrt(1 - sv ** 2) + 1e-3)
            mort = sm(2.2 * s, 0.7 * s, ep)[..., None]
            n1 = sample(tex, Y * 0.5 / s + 0 * X, X * 0.5 / s + 0 * Y)
            n2 = sample(tex2, Y * 1.5 / s + 0 * X, X * 1.5 / s + 0 * Y)
            base = np.array([150, 140, 124], np.float32) + np.array([36, 36, 32], np.float32) * tint[..., None]
            base = base * (1 + 0.07 * n1 + 0.05 * n2)[..., None] * (1 + 0.06 * (0.5 - fy))[..., None]
            col = base * (1 - mort) + np.array([112, 104, 92], np.float32) * mort
            moss = (sm(0.72, 1.0, v) * sm(-0.2, 0.9, n1) * 0.5)[..., None]
            col = col * (1 - moss) + np.array([78, 98, 54], np.float32) * moss
            # rain has stained the stone below the cornice and under the window sills
            streak = sample(fnoise(64, 512, 2.0, 0.08, 73), Y * 0.05 / s + 0 * X, arc / s * 1.2)
            stain = sm(0.25, 0.0, v) * sm(-0.3, 1.0, streak) * 0.3
            for wsv in (-0.52, 0.52):
                below = sm(0.0, 0.05, v - 0.43) * sm(0.45, 0.0, v - 0.43)
                stain = stain + 0.28 * below * sm(16, 6, np.abs(arc / s - wsv * 146 * 1.1)) * sm(-0.5, 1.0, streak)
            col = col * (1 - np.clip(stain, 0, 0.5))[..., None]
            col = col * (1 - 0.3 * self.wx.wet)
            under = (0.72 + 0.28 * sm(0, 0.05, v))[..., None]
            return col * under
        self.cylinder(cx, yt, yb, r, r * 1.03, stone)
        # dome, then the cornice ring that it sits on
        cy = yt - 16 * s
        self.dome(cx, cy, r * 0.99)

        def cornice(sv, v, X, Y, rr):
            arc = np.arcsin(sv) * rr
            fx = (arc / (16 * s)) % 1.0
            dent = ((fx < 0.35) & (v > 0.62))[..., None]
            base = np.array([198, 190, 172], np.float32) * (1 - 0.1 * (v > 0.55))[..., None]
            return np.where(dent, base * 0.55, base)
        self.cylinder(cx, cy, yt + 8 * s, r * 1.08, r * 1.08, cornice)
        self.telescope(cx, cy, r * 0.99)
        self.tower_details()

    def dome(self, cx, cy, R):
        s = self.s
        x0, x1 = int(cx - R - 2), int(cx + R + 3)
        y0, y1 = int(cy - R - 2), int(cy + 0.35 * R)
        X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5
        Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5
        sx, sy = [np.ascontiguousarray(a) for a in np.broadcast_arrays((X - cx) / R, (cy - Y) / R)]
        rho = np.sqrt(sx ** 2 + sy ** 2)
        cov = np.clip((1 - rho) * R + 0.5, 0, 1) * (sy > -0.3)
        z = np.sqrt(np.clip(1 - rho ** 2, 0, 1))
        nrm = np.stack([-sx, z, sy], -1)
        lon = np.degrees(np.arctan2(sx, z))
        lat = np.arcsin(np.clip(sy, -1, 1))
        streak = sample(fnoise(256, 256, 2.0, 0.12, 61), Y * 0.6 / s + 0 * X, X * 0.6 / s + 0 * Y)
        alb = np.array([80, 142, 120], np.float32) * (1 + 0.13 * streak)[..., None]
        ribd = np.abs(((lon + 11.25) % 22.5) - 11.25) * math.pi / 180 * R * np.cos(lat)
        rib = sm(1.6 * s, 0.4 * s, ribd)[..., None]
        alb = alb * (1 - 0.45 * rib)
        if self.wx.snow_cover > 0.02:
            cap = (sm(0.15, 0.55, sy) * min(1.0, self.wx.snow_cover * 1.6) * (1 - 0.6 * rib[..., 0]))[..., None]
            alb = alb * (1 - cap) + np.array([236, 240, 246], np.float32) * cap
        spec_dir = normalize(self.sunv + np.array([0, 1, 0], np.float32))
        spec = np.clip(nrm @ spec_dir, 0, 1) ** 40 * self.sun_str * (0.5 + 0.6 * self.wx.wet)
        col = alb * self.light(nrm) + spec[..., None] * 255 * self.sun_col
        col += (self.wx.wet * 0.12 * sm(0.0, 0.8, sy))[..., None] * self.hor_col
        if self.observing:
            mx, my = self.scope_target()
            th = math.atan2(cy - my * self.H, mx * self.W - cx)
            th = min(max(th, math.radians(25)), math.radians(155))
            self.scope_theta = th
            phi = np.arctan2(sy, sx)
            dphi = np.degrees(np.abs((phi - th + math.pi) % (2 * math.pi) - math.pi))
            wedge = sm(5.0, 3.8, dphi) * (rho > 0.1)
            inner = np.array([18, 6, 5], np.float32) + np.array([100, 26, 18], np.float32) * np.clip(1 - rho, 0, 1)[..., None] ** 0.7
            col = col * (1 - wedge[..., None]) + inner * wedge[..., None]
            self.slit = (x0, y0, x1, y1, wedge, rho)
        else:
            self.scope_theta = None
            seam = sm(1.4 * s, 0.3 * s, np.abs(np.abs(sx) - 0.1 * z) * R)[..., None] * (sy > 0)[..., None]
            col = col * (1 - 0.35 * seam)
        self.over(y0, y1, x0, x1, col, cov[..., None])
        L = Layer(self, cx - 40 * s, cy - R - 64 * s, cx + 40 * s, cy - R + 4 * s)
        brass = self.lit((176, 136, 64), (0, 0.6, 0.8))
        L.line([(cx, cy - R + 2 * s), (cx, cy - R - 48 * s)], brass * 0.8, 2.2 * s)
        L.ellipse(cx, cy - R - 6 * s, 5.5 * s, 5.5 * s, brass)
        # a weathervane: the cross shows north and east, the arrow points into the wind
        iron = self.lit((40, 38, 36), (0, 0.6, 0.8))
        top = cy - R - 30 * s
        L.line([(cx - 14 * s, top), (cx + 14 * s, top)], iron, 1.4 * s)
        L.line([(cx, top - 5 * s), (cx, top + 5 * s)], iron, 1.4 * s)
        for ex, ey in ((cx - 14 * s, top), (cx + 14 * s, top), (cx, top - 5 * s), (cx, top + 5 * s)):
            L.ellipse(ex, ey, 1.6 * s, 1.6 * s, brass)
        A = math.radians(self.wx.wind_dir_deg)
        dx, dy = -math.sin(A), math.cos(A) * 0.35
        ln, ay = 20 * s, cy - R - 44 * s
        hx, hy, tx, ty = cx + dx * ln, ay + dy * ln, cx - dx * ln, ay - dy * ln
        L.line([(tx, ty), (hx, hy)], iron, 1.8 * s)
        px, py = -dy, dx
        L.poly([(hx + dx * 6 * s, hy + dy * 6 * s), (hx + px * 4 * s, hy + py * 4 * s), (hx - px * 4 * s, hy - py * 4 * s)], iron)
        L.poly([(tx, ty), (tx - dx * 5 * s + px * 7 * s, ty - dy * 5 * s + py * 7 * s - 3 * s),
                (tx - dx * 9 * s, ty - dy * 9 * s - 2 * s), (tx - dx * 5 * s - px * 7 * s, ty - dy * 5 * s - py * 7 * s + 1 * s)], iron)
        L.composite()

    def scope_target(self):
        """Where the telescope looks, as screen fractions: the moon when it is up and lit, else the
        brightest planet, else the brightest star well up; chosen on the hour and then tracked."""
        day, m = self.day, self.m
        h0 = min(1440, (m // 60) * 60)
        if day.moon_alt[h0] > 10 and self.moon_alt > 6 and day.moon_frac[h0] > 0.12:
            return to_screen(self.moon_alt, self.moon_az)
        best = None
        for name, (alt, az, mag) in day.planets.items():
            if alt[h0] > 12 and alt[m] > 6 and mag[h0] < 1.2 and (best is None or mag[h0] < best[0]):
                best = (mag[h0], alt[m], az[m])
        if best:
            return to_screen(best[1], best[2])
        alt, az = astro.star_vectors_to_altaz(STAR_RA[:85], STAR_DEC[:85], float(day.jd[h0]), day.lat, day.lon)
        ok = (alt > 25) & (np.abs(az - 180) < 100)
        i = int(np.argmin(np.where(ok, STAR_MAG[:85], 99)))
        alt, az = astro.star_vectors_to_altaz(STAR_RA[i:i + 1], STAR_DEC[i:i + 1], self.jd, day.lat, day.lon)
        return to_screen(float(alt[0]), float(az[0]))

    def telescope(self, cx, cy, R):
        th = self.scope_theta
        if th is None:
            return
        s = self.s
        ux, uy = math.cos(th), -math.sin(th)
        px, py = -uy, ux
        a0, a1 = 0.05 * R, 1.04 * R
        w = 0.085 * R
        L = Layer(self, cx - 1.5 * R, cy - 1.5 * R, cx + 1.5 * R, cy + 0.3 * R)
        brass = self.lit((120, 124, 134), (ux * 0.3, 0.5, 0.8)) + np.array([14, 4, 3])
        L.poly([(cx + ux * a0 + px * w, cy + uy * a0 + py * w), (cx + ux * a1 + px * w, cy + uy * a1 + py * w),
                (cx + ux * a1 - px * w, cy + uy * a1 - py * w), (cx + ux * a0 - px * w, cy + uy * a0 - py * w)], brass)
        a2 = a1 + 0.16 * R
        w2 = w * 1.25
        L.poly([(cx + ux * a1 + px * w2, cy + uy * a1 + py * w2), (cx + ux * a2 + px * w2, cy + uy * a2 + py * w2),
                (cx + ux * a2 - px * w2, cy + uy * a2 - py * w2), (cx + ux * a1 - px * w2, cy + uy * a1 - py * w2)], brass * 0.8)
        ring = self.lit((150, 132, 96), (ux * 0.3, 0.5, 0.8)) + np.array([60, 66, 84]) * self.moon_str
        am = a1 - 0.25 * R
        L.poly([(cx + ux * am + px * w * 1.1, cy + uy * am + py * w * 1.1), (cx + ux * (am + 0.05 * R) + px * w * 1.1, cy + uy * (am + 0.05 * R) + py * w * 1.1),
                (cx + ux * (am + 0.05 * R) - px * w * 1.1, cy + uy * (am + 0.05 * R) - py * w * 1.1), (cx + ux * am - px * w * 1.1, cy + uy * am - py * w * 1.1)], ring)
        L.line([(cx + ux * a0 + px * w * 0.5, cy + uy * a0 + py * w * 0.5), (cx + ux * a1 + px * w * 0.5, cy + uy * a1 + py * w * 0.5)],
               brass * 1.4 + np.array([60, 66, 84]) * self.moon_str, 1.4 * s)
        # visible through the open slit, or where it pokes out beyond the dome
        X = np.arange(L.x0, L.x1, dtype=np.float32)[None, :] + 0.5
        Y = np.arange(L.y0, L.y1, dtype=np.float32)[:, None] + 0.5
        rho = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2) / R
        allow = np.clip((rho - 1) * R + 0.5, 0, 1)
        x0, y0, x1, y1, wedge, _ = self.slit
        ax0, ay0 = max(L.x0, x0), max(L.y0, y0)
        ax1, ay1 = min(L.x1, x1), min(L.y1, y1)
        allow[ay0 - L.y0:ay1 - L.y0, ax0 - L.x0:ax1 - L.x0] = np.maximum(
            allow[ay0 - L.y0:ay1 - L.y0, ax0 - L.x0:ax1 - L.x0], wedge[ay0 - y0:ay1 - y0, ax0 - x0:ax1 - x0])
        allow *= (Y < cy + 2 * s)
        L.composite(allow=allow)

    def tower_details(self):
        s, W, H, h = self.s, self.W, self.H, self.h
        tw = self.tw
        cx, yb, yt, r = tw["cx"], tw["yb"], tw["yt"], tw["r"]
        on = self.lights_on
        L = Layer(self, cx - r * 1.1, yt - 10 * s, cx + r * 1.1, yb + 30 * s)
        front = normalize([0, 1, 0.1])
        stone_hi = self.lit((200, 192, 176), front, cx, yb - 60 * s)
        # windows
        wins = []
        for sv, wy in ((-0.52, 0.548), (0.52, 0.548)):
            k = math.sqrt(1 - sv * sv)
            nrm = normalize([-sv, k, 0.05])
            wx, wy = cx + sv * r, wy * H
            ww, wh = 13 * s * k, 40 * s
            surround = self.lit((196, 188, 170), nrm, wx, wy)
            L.poly([(wx - ww - 6 * s * k, wy + wh + 5 * s), (wx + ww + 6 * s * k, wy + wh + 5 * s),
                    (wx + ww + 6 * s * k, wy - wh), (wx - ww - 6 * s * k, wy - wh)], surround)
            L.ellipse(wx, wy - wh, ww + 6 * s * k, ww + 6 * s * k, surround)
            glass = self.lit((42, 50, 62), nrm) + self.amb * 30
            wl = self.windows_lit
            glass = glass * (1 - wl) + np.array([255, 190, 112], np.float32) * wl
            L.poly([(wx - ww, wy + wh), (wx + ww, wy + wh), (wx + ww, wy - wh), (wx - ww, wy - wh)], glass)
            L.ellipse(wx, wy - wh, ww, ww, glass)
            mull = self.lit((60, 52, 44), nrm)
            L.line([(wx, wy - wh - ww), (wx, wy + wh)], mull, 2.2 * s)
            L.line([(wx - ww, wy + 2 * s), (wx + ww, wy + 2 * s)], mull, 2.2 * s)
            L.poly([(wx - ww - 8 * s * k, wy + wh + 4 * s), (wx + ww + 8 * s * k, wy + wh + 4 * s),
                    (wx + ww + 8 * s * k, wy + wh + 9 * s), (wx - ww - 8 * s * k, wy + wh + 9 * s)], surround * 1.08)
            wins.append((wx, wy))
        # a small plant on the left sill, a silhouette when the lamp is lit inside
        wx, wy = wins[0]
        plant = np.array([30, 40, 26], np.float32) * (0.4 + 0.6 * (1 - self.windows_lit)) + self.amb * 20
        L.poly([(wx - 7 * s, wy + 40 * s), (wx + 5 * s, wy + 40 * s), (wx + 4 * s, wy + 31 * s), (wx - 6 * s, wy + 31 * s)], plant)
        for a in (-0.9, -0.4, 0.1, 0.6):
            L.ellipse(wx - 1 * s + 9 * s * math.sin(a), wy + 25 * s - 6 * s * math.cos(a), 4 * s, 7 * s, plant)
        # clock
        self.clock(L, cx, CLOCK["y"] * H, CLOCK["R"] * s)
        # door
        dw, dh = 34 * s, 128 * s
        dyb = yb + 12 * s
        arch = self.lit((190, 182, 164), front, cx, dyb - dh)
        L.poly([(cx - dw - 12 * s, dyb), (cx + dw + 12 * s, dyb), (cx + dw + 12 * s, dyb - dh + dw), (cx - dw - 12 * s, dyb - dh + dw)], arch)
        L.ellipse(cx, dyb - dh + dw, dw + 12 * s, dw + 12 * s, arch)
        for a in np.linspace(0.15, math.pi - 0.15, 7):
            L.line([(cx + (dw + 1 * s) * math.cos(a), dyb - dh + dw - (dw + 1 * s) * math.sin(a)),
                    (cx + (dw + 12 * s) * math.cos(a), dyb - dh + dw - (dw + 12 * s) * math.sin(a))], arch * 0.75, 1.2 * s)
        wood = self.lit((96, 58, 36), front, cx, dyb - dh * 0.5)
        L.poly([(cx - dw, dyb), (cx + dw, dyb), (cx + dw, dyb - dh + dw), (cx - dw, dyb - dh + dw)], wood)
        L.ellipse(cx, dyb - dh + dw, dw, dw, wood)
        for i in range(1, 6):
            x = cx - dw + i * 2 * dw / 6
            L.line([(x, dyb), (x, dyb - dh + dw - math.sqrt(max(0, dw * dw - (x - cx) ** 2)) + 2 * s)], wood * 0.62, 1.4 * s)
        iron = self.lit((34, 32, 32), front)
        for yy in (dyb - 0.25 * dh, dyb - 0.7 * dh):
            L.line([(cx - dw, yy), (cx + dw * 0.7, yy)], iron, 3.2 * s)
            L.poly([(cx + dw * 0.7, yy - 3.5 * s), (cx + dw * 0.86, yy), (cx + dw * 0.7, yy + 3.5 * s)], iron)
            for k in range(6):
                L.ellipse(cx - dw + (k + 0.5) * 1.6 * dw / 6, yy, 1.2 * s, 1.2 * s, iron * 1.8 + 20)
        for i in range(3):
            for j in range(5):
                L.ellipse(cx - dw * 0.6 + i * dw * 0.6, dyb - dh * (0.15 + 0.17 * j), 1.0 * s, 1.0 * s, iron * 1.6 + 15)
        L.ellipse(cx + dw * 0.55, dyb - 0.47 * dh, 5 * s, 5 * s, iron)
        L.ellipse(cx + dw * 0.55, dyb - 0.47 * dh, 3 * s, 3 * s, wood)
        step = self.lit((176, 168, 150), [0, 0.5, 0.9], cx, dyb)
        L.poly([(cx - 50 * s, dyb + 9 * s), (cx + 50 * s, dyb + 9 * s), (cx + 46 * s, dyb - 1 * s), (cx - 46 * s, dyb - 1 * s)], step)
        mat = self.lit((104, 80, 52), [0, 0.3, 1], cx, dyb)
        L.poly([(cx - 27 * s, dyb + 7 * s), (cx + 27 * s, dyb + 7 * s), (cx + 25 * s, dyb + 1 * s), (cx - 25 * s, dyb + 1 * s)], mat)
        L.line([(cx - 25 * s, dyb + 4 * s), (cx + 25 * s, dyb + 4 * s)], mat * 0.75, 0.8 * s)
        if self.wx.snow_cover > 0.1:
            L.poly([(cx - 50 * s, dyb - 1 * s), (cx + 50 * s, dyb - 1 * s), (cx + 48 * s, dyb + 3 * s), (cx - 48 * s, dyb + 3 * s)],
                   self.lit((236, 240, 246), [0, 0.3, 1]), a=min(1.0, self.wx.snow_cover * 1.5))
        # a terracotta pot by the door with whatever is in season
        px, py = cx - 62 * s, dyb + 6 * s
        terracotta = self.lit((168, 86, 52), front, px, py)
        L.poly([(px - 9 * s, py - 16 * s), (px + 9 * s, py - 16 * s), (px + 7 * s, py), (px - 7 * s, py)], terracotta)
        L.poly([(px - 10 * s, py - 19 * s), (px + 10 * s, py - 19 * s), (px + 10 * s, py - 15 * s), (px - 10 * s, py - 15 * s)], terracotta * 1.1)
        se = self.season
        rp = np.random.default_rng(57)
        bloom = None
        if 60 <= se.doy < 125:
            leafc, bloom = (70, 110, 50), (238, 206, 52)      # daffodils
        elif 125 <= se.doy < 275:
            leafc, bloom = (58, 96, 44), (212, 46, 40)        # geraniums
        elif 275 <= se.doy < 320:
            leafc, bloom = (70, 84, 56), (176, 106, 172)      # heather
        else:
            leafc = (40, 70, 44)                              # a little box tree
        for k in range(14):
            a = rp.uniform(-1.2, 1.2)
            ln = rp.uniform(8, 18) * s
            L.line([(px + rp.normal(0, 3) * s, py - 18 * s), (px + math.sin(a) * ln, py - 18 * s - math.cos(a) * ln)],
                   self.lit(leafc, front, px, py), 2.0 * s)
        if bloom:
            for k in range(9):
                L.ellipse(px + rp.normal(0, 7) * s, py - rp.uniform(24, 36) * s, 2.6 * s, 2.2 * s, self.lit(bloom, front, px, py))
        else:
            L.ellipse(px, py - 30 * s, 10 * s, 13 * s, self.lit(leafc, front, px, py))
        # a brass plaque, and a boot scraper by the step
        pl = self.lit((180, 140, 70), front) + 25 * self.sun_str
        L.poly([(cx + dw + 20 * s, dyb - 70 * s), (cx + dw + 34 * s, dyb - 70 * s), (cx + dw + 34 * s, dyb - 60 * s), (cx + dw + 20 * s, dyb - 60 * s)], pl)
        L.line([(cx + 54 * s, dyb + 6 * s), (cx + 54 * s, dyb - 2 * s), (cx + 66 * s, dyb - 2 * s), (cx + 66 * s, dyb + 6 * s)], iron, 1.4 * s)
        # a cast-iron downpipe from the gutter under the cornice
        dpx = cx + 0.86 * r
        dp = self.lit((52, 58, 64), normalize([-0.86, 0.5, 0.1]))
        L.line([(dpx, yt + 10 * s), (dpx, yb + 6 * s)], dp, 4.2 * s)
        L.poly([(dpx - 6 * s, yt + 8 * s), (dpx + 6 * s, yt + 8 * s), (dpx + 3 * s, yt + 18 * s), (dpx - 3 * s, yt + 18 * s)], dp)
        for yy in np.arange(yt + 60 * s, yb, 70 * s):
            L.line([(dpx - 4 * s, yy), (dpx + 4 * s, yy)], dp * 0.7, 2.0 * s)
        L.line([(dpx, yb + 2 * s), (dpx + 8 * s, yb + 8 * s)], dp, 4.2 * s)
        # the lintel: carved over the door, for whoever looks closely
        ly = dyb - dh - 30 * s
        L.poly([(cx - 72 * s, ly - 12 * s), (cx + 72 * s, ly - 12 * s), (cx + 72 * s, ly + 12 * s), (cx - 72 * s, ly + 12 * s)], stone_hi)
        font = ImageFont.truetype(FONT, max(8, int(14 * s * SS)))
        txt = "L O O K   C L O S E R"
        L.text(cx, ly + 1.0 * s, txt, font, stone_hi * 1.15)
        L.text(cx, ly, txt, font, stone_hi * 0.45)
        # wall lantern
        lx, lyy = cx + 62 * s, yb - 92 * s
        L.line([(cx + dw + 13 * s, lyy - 14 * s), (lx, lyy - 14 * s)], iron, 2.5 * s)
        L.poly([(lx - 6 * s, lyy - 10 * s), (lx + 6 * s, lyy - 10 * s), (lx + 5 * s, lyy + 8 * s), (lx - 5 * s, lyy + 8 * s)],
               self.lit((150, 150, 140), front) * (1 - on) + np.array([255, 205, 130]) * on)
        L.poly([(lx - 8 * s, lyy - 10 * s), (lx + 8 * s, lyy - 10 * s), (lx, lyy - 17 * s)], iron)
        # ivy up the lower left of the tower
        rg = np.random.default_rng(51)
        t = np.linspace(0, 1, 90)
        vx = cx - r * (0.97 - 0.30 * t + 0.05 * np.sin(t * 14))
        vy = yb + 8 * s - t * (0.105 * H)
        L.line(list(zip(vx, vy)), self.lit((60, 48, 36), front), 2.0 * s)
        for i in range(300):
            j = rg.integers(0, len(t))
            lx2, ly2 = vx[j] + rg.normal(0, 14 * s), vy[j] + rg.normal(0, 8 * s)
            sv = float(np.clip((lx2 - cx) / r, -0.99, 0.99))
            nrm = normalize([-sv + rg.normal(0, 0.3), math.sqrt(1 - sv * sv), rg.uniform(0, 0.6)])
            c = self.lit(np.array([48, 84, 36]) * rg.uniform(0.75, 1.25), nrm, lx2, ly2)
            L.ellipse(lx2, ly2, rg.uniform(3.0, 5.5) * s, rg.uniform(2.2, 4.0) * s, c)
        L.composite()
        self.win_pos = wins
        self.door_lantern = (lx, lyy)

    def clock(self, L, x, y, R):
        s, h = self.s, self.h
        on = self.lights_on
        front = normalize([0, 1, 0.1])
        L.ellipse(x, y, R * 1.2, R * 1.2, self.lit((196, 188, 170), front, x, y))
        L.ellipse(x, y, R * 1.07, R * 1.07, self.lit((170, 128, 58), front))
        L.ellipse(x, y, R * 0.99, R * 0.99, self.lit((120, 90, 40), front))
        face = self.lit((234, 226, 204), front) * (1 - 0.6 * on) + np.array([255, 238, 200], np.float32) * 0.92 * on
        # twice a year the sun passes right behind the dial, and the glass glows
        az_c, alt_c = 180 + (x / self.W - 0.5) * AZ_SPAN, (VH - y / self.H) / VH * ALT_TOP
        off = math.hypot((self.sun_az - az_c) * math.cos(math.radians(alt_c)), self.sun_alt - alt_c)
        back = sm(1.6, 0.3, off) * self.sun_vis
        if back > 0:
            face = face * (1 - back) + np.array([255, 246, 220], np.float32) * back
            self.backlit = (x, y, R, back)
        L.ellipse(x, y, R * 0.96, R * 0.96, face)
        ink = np.array([38, 32, 28], np.float32) * (0.6 + 0.4 * self.amb.mean() / 0.5)
        for i in range(60):
            a = math.radians(i * 6)
            if i % 5:
                px, py = x + R * 0.88 * math.sin(a), y - R * 0.88 * math.cos(a)
                L.ellipse(px, py, 1.1 * s, 1.1 * s, ink)
            else:
                L.line([(x + R * 0.80 * math.sin(a), y - R * 0.80 * math.cos(a)),
                        (x + R * 0.92 * math.sin(a), y - R * 0.92 * math.cos(a))], ink, 3.0 * s)
        font = ImageFont.truetype(FONT, max(6, int(R * 0.21 * SS)))
        for i, numeral in enumerate(["XII", "I", "II", "III", "IIII", "V", "VI", "VII", "VIII", "IX", "X", "XI"]):
            a = math.radians(i * 30)
            L.text(x + R * 0.64 * math.sin(a), y - R * 0.64 * math.cos(a), numeral, font, ink)

        def hand(angle, length, width, tail):
            a = math.radians(angle)
            ux, uy = math.sin(a), -math.cos(a)
            px, py = -uy, ux
            pts = [(x - ux * tail + px * width, y - uy * tail + py * width), (x + ux * length * 0.82 + px * width * 0.6, y + uy * length * 0.82 + py * width * 0.6),
                   (x + ux * length, y + uy * length), (x + ux * length * 0.82 - px * width * 0.6, y + uy * length * 0.82 - py * width * 0.6),
                   (x - ux * tail - px * width, y - uy * tail - py * width)]
            L.poly(pts, ink * 0.8)
        hh, mins = h, self.m % 60
        if self.day.mysteries.clock_stopped and 213 <= self.m < 246:
            hh, mins = 3, 33
        hand((hh % 12) * 30 + mins * 0.5, R * 0.52, R * 0.055, R * 0.12)
        hand(mins * 6, R * 0.80, R * 0.035, R * 0.14)
        L.ellipse(x, y, R * 0.065, R * 0.065, self.lit((180, 140, 64), front) + 30 * on)
