"""The sea: reflections, glitter paths, light reflections, mist, and foam at the shore."""
import functools
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

from core import *  # noqa: F401,F403


@functools.lru_cache(None)
def sea_fields(W, H):
    """Per-pixel distance on the water and two independent wave and ripple fields, made once per process."""
    hz = int(round(VH * H))
    rows = np.arange(hz, H, dtype=np.float32) + 0.5
    ad = (rows - VH * H) / (VH * H) * ALT_TOP
    Z = 1.0 / np.tan(np.radians(np.maximum(ad, 0.05)))
    xa = ((np.arange(W, dtype=np.float32) + 0.5) / W - 0.5) * math.radians(AZ_SPAN)
    R, C = np.repeat(Z[:, None] * 30.0, W, 1), (Z[:, None] * xa[None, :] * 30.0).astype(np.float32)
    fade = sm(0.2, 3.0, ad)[:, None]
    tw, tr = fnoise(512, 2048, 2.6, 5.0, 9), fnoise(512, 2048, 1.4, 2.5, 10)
    wa, wb = sample(tw, R, C) * fade, sample(tw, R + 173.0, C + 911.0) * fade
    ra, rb = sample(tr, R * 3.6, C * 3.6) * fade, sample(tr, R * 3.6 + 251.0, C * 3.6 + 677.0) * fade
    return rows, ad, R, C, fade, wa, wb, ra, rb


class SeaMixin:
    def plan_emitters(self):
        s, W, H = self.s, self.W, self.H
        if self.lights_on > 0:
            px, py = self.pier_lantern()
            self.emitters.append((px, py, np.array([255, 196, 120], np.float32), 1.2 * self.lights_on, self.pier_water_y()))
        if self.day.events.boat(self.t) is None:
            bx, by = MOORED[0] * W, MOORED[1] * H
            sz = 170 * s
            if self.night > 0:
                self.emitters.append((bx + 0.05 * sz, by - 1.22 * sz, np.array([230, 235, 255], np.float32), 0.5 * self.night, by + 0.1 * sz))

    def pier_lantern(self):
        x, y = self.pproj(*self.pier_pt(1.0, 0.06, PIER3["deck"] + 0.112))
        return float(x), float(y)

    def pier_water_y(self):
        return float(self.pproj(*self.pier_pt(1.0, -0.1, 0.0))[1])

    def sea(self):
        W, H, hz, s = self.W, self.H, self.hz, self.s
        rows, ad, R, C, fade, wa, wb, ra, rb = sea_fields(W, H)
        wx = self.wx
        rough = 0.7 + 0.06 * wx.wind_ms + 0.4 * self.season.sea_winter * min(1.0, wx.wind_ms / 8)
        # the waves change a little each minute: two fixed wave fields mixed in a slowly turning ratio
        p1, p2 = 2 * math.pi * self.m / 37.0, 2 * math.pi * self.m / 23.0
        w = (wa * math.cos(p1) + wb * math.sin(p1)) * rough
        rp = ra * math.cos(p2) + rb * math.sin(p2)
        spark = np.clip(rp - 0.9, 0, None) ** 1.5 * 2.0
        off = w * (1.0 + ad[:, None] * 2.0) * s * 1.5
        xj = np.clip((np.arange(W)[None, :] + (w * 2 + rp * (1 + ad[:, None] * 0.25)) * s * 2).astype(np.int32), 0, W - 1)
        refl = 0
        for k in (0.5, 1.0, 1.7):
            ri = np.clip((2 * VH * H - rows[:, None] - off * k).astype(np.int32), 0, hz - 1)
            refl = refl + self.c[ri, xj] / 3
        f = (0.1 + 0.85 * np.exp(-ad / 5.5))[:, None, None] * (1 - 0.3 * max(wx.rain, 0.5 * wx.drizzle)) * (1 - 0.25 * sm(6, 14, wx.wind_ms))
        body = WATER * (self.amb + 0.35 * self.sun_col * self.sun_str + 0.2 * MOON_COL * self.moon_str)
        sea = refl * f * 0.95 + body * (1 - f)
        sea *= (1 + 0.10 * w)[..., None]
        spark = np.clip(rp - 0.9, 0, None) ** 1.5 * 2.0
        Xs = np.arange(W, dtype=np.float32)[None, :]

        def path(src_alt, src_x, colr, k, wm):
            sig = (5 + ad[:, None] * 2.8) * s * wm * (1 + max(src_alt, 0) / 18)
            horiz = np.exp(-((Xs - src_x) / sig) ** 2)
            ctr, spread = max(src_alt, 0.6), 2.5 + 0.55 * max(src_alt, 0)
            vert = np.exp(-((ad[:, None] - ctr) / spread) ** 2) + 0.25 * np.exp(-ad[:, None] / (3 + ctr))
            return (horiz * vert * (0.25 + spark) * k)[..., None] * np.asarray(colr, np.float32)

        if self.sun_alt > -1:
            sx = to_screen(self.sun_alt, self.sun_az)[0] * W
            sea += path(self.sun_alt, sx, keys(SUN_DISK, self.sun_alt),
                        1.2 * sm(-1, 3, self.sun_alt) * (1.2 - 0.5 * sm(10, 40, self.sun_alt)) * self.sun_vis ** 1.5, 1.0)
        if self.moon_alt > -1 and self.night > 0:
            mx = to_screen(self.moon_alt, self.moon_az)[0] * W
            sea += path(self.moon_alt, mx, (225, 230, 245), 0.65 * self.night * sm(-1, 6, self.moon_alt) * self.moon_bright ** 0.5 * (1 - 0.9 * self.overcast), 0.8)
        for (ex, ey, ecol, es, wy) in self.emitters:
            r0 = int(wy) - hz
            length = max(12 * s, (wy - ey) * 1.8) + 30 * s
            c0, c1 = int(max(0, ex - 60 * s)), int(min(W, ex + 60 * s))
            ra, rb = max(0, r0), int(min(H - hz, r0 + length * 5))
            if c0 >= c1 or ra >= rb:
                continue
            rr = np.arange(ra, rb, dtype=np.float32)[:, None] - r0
            prof = np.exp(-rr / length)
            sigx = 2.5 * s + rr * 0.03
            hx = np.exp(-((np.arange(c0, c1, dtype=np.float32)[None, :] - ex) / sigx) ** 2)
            sea[ra:rb, c0:c1] += (prof * hx * (0.35 + spark[ra:rb, c0:c1] * 1.5) * es)[..., None] * ecol
        # whitecaps when the wind gets up
        caps = sm(7, 14, wx.wind_ms)
        if caps > 0:
            wc = sample(fnoise(256, 1024, 1.8, 3.0, 12), R * 1.6 + self.m * 0.7, C * 1.6) * fade
            foam = (sm(1.6 - 0.5 * caps, 2.6 - 0.5 * caps, wc) * caps * 0.8)[..., None]
            sea = sea * (1 - foam) + np.array([215, 222, 226], np.float32) * (self.amb + 0.4 * self.sun_col * self.sun_str) * foam
        # rain dimples the water
        rr = max(wx.rain, 0.6 * wx.drizzle)
        if rr > 0.03:
            dots = self.rng.random(sea.shape[:2]) < 0.004 * rr
            sea[dots] = sea[dots] * 0.7 + 60 * (self.amb.mean() + 0.2)
        # shallow water over the shingle: greener, and you can almost see the stones
        xn = (np.arange(W, dtype=np.float32) + 0.5) / W
        wl = water_line(xn, self.tide) * H
        dist = (wl[None, :] - rows[:, None]) / (s * (0.35 + 1.3 * np.clip((rows[:, None] / H - 0.6) / 0.4, 0, 1)))
        tint = (np.exp(-np.maximum(dist, 0) / 14) * (dist > -2) * sm(0.56, 0.6, xn)[None, :] * 0.45)[..., None]
        shallow = np.array([62, 104, 100], np.float32) * (self.amb + 0.45 * self.sun_col * self.sun_str + 0.2 * MOON_COL * self.moon_str)
        sea = sea * (1 - tint) + shallow * tint
        self.c[hz:] = sea
        self.wave = w

    def mist(self):
        ev, wx = self.day.events, self.wx
        damp = sm(0.55, 0.92, wx.rh) * sm(6, 1, wx.wind_ms)
        m = (0.9 * math.exp(-((self.t - ev.sunrise - 0.2) / 1.3) ** 2) + 0.4 * math.exp(-((self.t - ev.sunset - 1.5) / 1.0) ** 2)) * damp
        m = min(1.0, m + 0.8 * wx.fog)
        if m < 0.03:
            return
        H, W, hz = self.H, self.W, self.hz
        y0, y1 = int(hz - 0.05 * H), int(min(H, hz + 0.09 * H))
        rows = np.arange(y0, y1, dtype=np.float32)[:, None]
        prof = np.exp(-((rows - hz) / (0.025 * H)) ** 2)
        tex = fnoise(256, 2048, 2.2, 4.0, 31)
        n = sample(tex, np.repeat((rows - y0) * 256 / (y1 - y0), W, 1), np.repeat(np.arange(W, dtype=np.float32)[None, :] * 2048 / W, y1 - y0, 0))
        a = (prof * sm(-0.8, 1.2, n) * 0.55 * m)[..., None]
        mc = self.hor_col * 0.6 + np.array([225, 225, 235], np.float32) * 0.4 * (0.4 + 0.6 * self.amb.mean() / 0.5)
        reg = self.c[y0:y1]
        reg[:] = reg * (1 - a) + mc * a

    def foam(self):
        """Swash and a small breaking wavelet along the waterline, shifting a little every minute."""
        W, H, s = self.W, self.H, self.s
        L = Layer(self, 0.55 * W, 0.6 * H, W, H)
        fc = self.lit((228, 234, 236), (0, 0.3, 1))
        ph = self.m * 0.9
        xs = np.arange(0.565 * W, W + 4 * s, 2 * s)
        yw = water_line(xs / W, self.tide) * H
        p = 0.35 + 1.3 * np.clip((yw / H - 0.6) / 0.4, 0, 1)
        u = xs / s
        rough = np.interp(xs / W, np.linspace(0, 1, 1024), fnoise(4, 1024, 1.6, 1, 42)[1])
        for k, (off, amp, gap, a) in enumerate(((1.2, 1.4, 0.15, 0.75), (6.5, 3.5, 0.45, 0.4))):
            wave = np.sin(u * 0.010 + ph + k * 2.1) * 0.6 + np.sin(u * 0.023 - ph * 0.7 + k) * 0.4
            y = yw - (off + amp * wave) * s * p
            show = np.interp(xs / W, np.linspace(0, 1, 512), fnoise(4, 512, 1.4, 1, 43 + k)[(self.m // 3) % 4]) + 0.4 * rough > gap
            alpha = a * (0.55 + 0.45 * np.clip(0.5 + 0.5 * wave, 0, 1))
            i = 0
            while i < len(xs) - 1:
                if not show[i]:
                    i += 1
                    continue
                j = i
                while j < len(xs) - 1 and show[j] and j - i < 40:
                    j += 1
                if j > i:
                    L.line(list(zip(xs[i:j + 1], y[i:j + 1])), fc, (1.4 - 0.4 * k) * s * float(p[i]), a=float(alpha[i]))
                i = j + 1
        L.composite()
