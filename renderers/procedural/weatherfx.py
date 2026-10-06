"""Weather you can see: fog that thickens with distance, rain and snow falling across the scene,
lightning out at sea, and a rainbow when the sun shines into a shower."""
import math

import numpy as np

from core import *  # noqa: F401,F403
from sky import sky_grid

UNIT_M = 15.0   # one world unit (the camera's height above the sea) in metres


class WeatherFxMixin:
    def fog_colour(self):
        day = np.array([206, 210, 214], np.float32) * (0.35 + 0.65 * min(1.0, self.amb.mean() / 0.45))
        return day * (1 - 0.5 * self.night) + self.hor_col * 0.25

    def fog_far(self):
        """Fog over the sky, the sea and the far shore: the farther, the thicker (Koschmieder)."""
        wx = self.wx
        if wx.fog < 0.02 and wx.visibility_m > 15000:
            return
        W, H, hz = self.W, self.H, self.hz
        k = 3.9 / max(wx.visibility_m, 60.0)
        fc = self.fog_colour()
        # below the horizon: distance to the sea surface in each row
        rows = np.arange(hz, H, dtype=np.float32) + 0.5
        ad = np.maximum((rows - VH * H) / (VH * H) * ALT_TOP, 0.05)
        D = UNIT_M / np.tan(np.radians(ad))
        a_sea = (1 - np.exp(-k * D))[:, None, None]
        self.c[hz:] = self.c[hz:] * (1 - a_sea) + fc * a_sea
        # the sky near the horizon is seen through the most fog; dense fog hides it altogether
        alt = (VH - (np.arange(hz, dtype=np.float32) + 0.5) / H) / VH * ALT_TOP
        thick = sm(1500, 150, wx.visibility_m)      # in thick fog the sky overhead goes too
        a_sky = np.clip(wx.fog * (0.35 + 0.65 * np.exp(-alt / 10)) + thick * 0.8 + (1 - np.exp(-k * 4000)) * np.exp(-alt / 6), 0, 1)[:, None, None]
        self.c[:hz] = self.c[:hz] * (1 - a_sky) + fc * a_sky

    def fog_near(self, C, A):
        """Fog over the near scenery (premultiplied colour C, coverage A) by distance down the frame."""
        wx = self.wx
        if wx.fog < 0.05 and wx.visibility_m > 4000:
            return C
        H = self.H
        k = 3.9 / max(wx.visibility_m, 60.0)
        # the near things stand on the hill: nothing is farther than the tower's foot, so every row above
        # it counts as that far, and the ground below it gets nearer toward the bottom of the frame
        rows = np.maximum(np.arange(H, dtype=np.float32) + 0.5, TOWER["yb"] * H)
        ad = (rows - VH * H) / (VH * H) * ALT_TOP
        D = UNIT_M / np.tan(np.radians(ad))
        a = (1 - np.exp(-k * D))[:, None, None]
        return C * (1 - a) + self.fog_colour() * a * A[..., None]

    def fog_object(self, metres):
        """Fog fraction in front of something this far away (for the tower and things on the hill)."""
        return 1 - math.exp(-3.9 / max(self.wx.visibility_m, 60.0) * metres)

    def rainbow(self):
        """Primary and faint secondary bows around the antisolar point, when the sun shines into rain."""
        wx = self.wx
        wetness = max(wx.rain, wx.drizzle, self.day.rain_near(self.m))
        k = wetness * sm(0.3, 0.7, self.sun_vis) * sm(1, 4, self.sun_alt) * sm(42, 30, self.sun_alt) * (1 - wx.fog)
        if k < 0.03:
            return
        W, H, hz = self.W, self.H, self.hz
        alt, az, e, n, u = sky_grid(W, H, 2)
        anti = -self.sunv
        ang = np.degrees(np.arccos(np.clip(e * anti[0] + n * anti[1] + u * anti[2], -1, 1)))
        col = np.zeros(alt.shape + (3,), np.float32)
        bands = [(42.2, (255, 60, 40)), (41.6, (255, 150, 40)), (41.0, (240, 230, 60)), (40.4, (70, 210, 90)),
                 (39.8, (60, 120, 255)), (39.2, (130, 70, 220))]
        for r_, c in bands:
            col += np.exp(-((ang - r_) / 0.45) ** 2)[..., None] * np.array(c, np.float32)
            col += 0.3 * np.exp(-((ang - (93.0 - r_)) / 0.55) ** 2)[..., None] * np.array(c, np.float32)   # secondary, reversed
        inside = sm(40, 30, ang)[..., None] * 0.06 * np.array([255, 255, 255], np.float32)   # brighter inside the bow
        col = (col * 0.22 + inside) * k * sm(0, 3, alt)[..., None]
        self.c[:hz] += upsample(col, (hz, W))

    def lightning(self):
        """A flash and, sometimes, a bolt over the sea in a thunderstorm."""
        if self.wx.thunder < 0.5:
            return
        r = np.random.default_rng([self.day.date.toordinal(), self.m, 91])
        if r.random() > 0.35:
            return
        s, W, H, hz = self.s, self.W, self.H, self.hz
        flash = r.uniform(0.25, 0.7)
        self.c[:hz] += np.array([150, 160, 190], np.float32) * flash * 0.35
        if r.random() < 0.6:
            x = r.uniform(0.1, 0.95) * W
            y = r.uniform(0.12, 0.3) * H
            L = Layer(self, x - 0.08 * W, y - 10, x + 0.08 * W, hz + 2)
            pts = [(x, y)]
            while pts[-1][1] < hz:
                px, py = pts[-1]
                pts.append((px + r.normal(0, 14 * s), py + r.uniform(12, 30) * s))
                if r.random() < 0.18:   # a branch
                    bx, by = pts[-1]
                    L.line([(bx, by), (bx + r.normal(0, 30 * s), by + r.uniform(20, 50) * s)], (225, 230, 255), 1.0 * s, a=0.6)
            L.line(pts, (240, 244, 255), 2.2 * s)
            L.composite()
            self.glow(x, (y + hz) / 2, 120 * s, (180, 190, 255), 0.25 * flash, tail=0.4)

    def falling_leaves(self):
        se = self.season
        if se.autumn < 0.3 or not 0.02 < se.drop < 0.97:
            return
        s, W, H = self.s, self.W, self.H
        r = self.rng
        n = int(4 + 22 * se.drop * (1 - se.drop) * 4 * min(1.0, 0.4 + self.wx.wind_ms / 6))
        lean = math.sin(math.radians(self.wx.wind_dir_deg - 90)) * min(1.0, self.wx.wind_ms / 8)
        L = Layer(self, 0.25 * W, 0.3 * H, 0.75 * W, 0.8 * H)
        cols = [(210, 164, 50), (218, 124, 42), (186, 72, 38), (156, 100, 50)]
        for _ in range(n):
            fy = r.uniform(0.38, 0.72)
            fx = CANOPY[0] + r.normal(0, 0.06) + lean * (fy - 0.4) * 0.25
            x, y = fx * W, fy * H
            ls = r.uniform(3.5, 6) * s
            a = r.uniform(0, math.pi)
            ca, sa_ = math.cos(a), math.sin(a)
            c = self.lit(cols[int(r.integers(4))], normalize([r.normal(0, 0.5), 0.6, 0.6]), x, y)
            L.poly([(x + ls * ca, y + ls * sa_ * 0.5), (x - 0.4 * ls * sa_, y + 0.4 * ls * ca * 0.5),
                    (x - 0.6 * ls * ca, y - 0.6 * ls * sa_ * 0.5), (x + 0.4 * ls * sa_, y - 0.4 * ls * ca * 0.5)], c)
        L.composite()

    def light_shafts(self, cover):
        """Crepuscular rays: smear the bright, unblocked sky toward the sun, so the beams show where the
        tree, the tower or a cloud's edge breaks the light."""
        sa = self.sun_alt
        if sa < -1 or sa > 35 or self.sun_vis < 0.2 or self.wx.fog > 0.6:
            return
        W, H, hz = self.W, self.H, self.hz
        sx, sy = to_screen(sa, self.sun_az)
        if not (-0.15 < sx < 1.15):
            return
        k = 4
        src = self.c[:hz:k, ::k].mean(-1)
        src = np.clip(src - 150, 0, None) / 105 * (1 - cover[:hz:k, ::k])
        h, w = src.shape
        cy, cx = sy * H / k, sx * W / k
        Y, X = np.mgrid[0:h, 0:w].astype(np.float32)
        acc = np.zeros_like(src)
        n = 28
        for i in range(n):
            f = 1 - 0.035 * i
            acc += ndi.map_coordinates(src, [cy + (Y - cy) * f, cx + (X - cx) * f], order=1, mode="constant") * (1 - i / n)
        acc /= n / 2
        strength = 0.35 * sm(-1, 3, sa) * sm(35, 15, sa) * self.sun_vis * (1 - 0.6 * self.overcast)
        rays = upsample(acc, (hz, W))[..., None] * keys(GLOW_COL, max(sa, 0)) * strength
        self.c[:hz] += rays

    def precipitation(self):
        """Rain streaks or snowflakes over everything, slanted by the wind, more and bigger near you."""
        wx = self.wx
        rain, snow = max(wx.rain, 0.6 * wx.drizzle), wx.snow
        if rain < 0.03 and snow < 0.03:
            return
        s, W, H = self.s, self.W, self.H
        r = np.random.default_rng([self.day.date.toordinal(), self.m, 92])
        lean = math.sin(math.radians(wx.wind_dir_deg - 90)) * min(1.0, wx.wind_ms / 12) * 0.6
        L = Layer(self, 0, 0, W, H)
        light = 0.35 + 0.65 * min(1.0, self.amb.mean() / 0.45) + self.lights_on * 0.15
        if rain >= 0.03:
            n = int(2500 * rain * (W * H) / (2880 * 1800))
            for _ in range(n):
                depth = r.random() ** 2           # most drops are far and faint
                x, y = r.uniform(0, W), r.uniform(0, H)
                ln = (8 + 34 * depth) * s * (0.6 + 0.4 * rain)
                c = np.array([200, 206, 214], np.float32) * light
                L.line([(x, y), (x + lean * ln, y + ln)], c, (0.6 + 1.0 * depth) * s, a=0.10 + 0.25 * depth)
        if snow >= 0.03:
            n = int(1800 * snow * (W * H) / (2880 * 1800))
            for _ in range(n):
                depth = r.random() ** 2
                x, y = r.uniform(0, W), r.uniform(0, H)
                rr = (0.8 + 3.2 * depth) * s
                c = np.array([240, 242, 246], np.float32) * (0.5 + 0.5 * light)
                L.ellipse(x, y, rr, rr, c, a=0.35 + 0.5 * depth)
        L.composite()
