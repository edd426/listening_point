"""Things that happen rarely, or can't be explained. What, where and when is in docs/SPOILERS.md;
everything is decided by the date, so a given day always shows the same things."""
import datetime as dt
import math

import numpy as np
from scipy import ndimage as ndi

import astro
from core import *  # noqa: F401,F403


def rng_for(*key):
    return np.random.default_rng([int(k) for k in key])


class Mysteries:
    """The day's schedule of the uncanny."""

    def __init__(self, day):
        d = day.date
        y, doy = d.year, d.timetuple().tm_yday
        self.day = day
        # a comet every year (some years two), for a run of nights, low in the evening or morning twilight
        self.comet = None
        r = rng_for(7741, y)
        for c in range(1 + int(r.random() < 0.4)):
            first, n, evening = int(r.integers(15, 340)), int(r.integers(7, 12)), r.random() < 0.6
            alt0, off, drift = r.uniform(15, 26), r.uniform(-12, 14), r.uniform(-1.2, 1.2)
            if first <= doy < first + n:
                k = (doy - first + 0.5) / n
                self.comet = self.place_comet(day, evening, alt0 * (0.6 + 0.4 * math.sin(math.pi * k)), off + drift * (doy - first), k)
        r = rng_for(7742, d.toordinal())
        u = r.random(12)       # every chance is drawn up front, so one thing never shifts another
        wx = day.wx
        # foggy nights may bring the ship that isn't there
        foggy = float(np.r_[wx.fog[:300], wx.fog[1320:]].max())
        self.ghost = 0.6 + 3.6 * u[1] if foggy > 0.4 and u[0] < 0.5 else None
        # a light in the empty cottage on the islet
        self.cottage = (1.6 + 1.6 * u[3], 0.2 + 0.5 * u[4]) if u[2] < 1 / 20 else None
        # someone walking the far shore with a lantern, a little after three
        self.lantern = (3.0 + 0.25 * u[6], 1 if u[7] < 0.5 else -1) if u[5] < 1 / 12 else None
        # footprints that go out into the snow and stop
        self.prints = int(30 + 270 * u[9]) if wx.snow_cover.max() > 0.5 and u[8] < 0.35 else None
        # a whale in the bay, a few days a year
        rw = rng_for(7743, y)
        whale_days = set(int(v) for v in rw.integers(150, 300, 3))
        self.whale = (int(9 * 60 + 8 * 60 * u[10]), 0.62 + 0.2 * u[11]) if doy in whale_days else None
        # a bottle comes ashore and lies on the beach for a few days
        rb = rng_for(7744, y)
        arrive, stay = int(rb.integers(60, 300)), int(rb.integers(2, 6))
        bx = rb.uniform(0.74, 0.96)
        self.bottle = (bx, doy == arrive) if arrive <= doy < arrive + stay else None
        # a book left open on the bench after a night out there
        rk = rng_for(7746, d.toordinal()).random(2)
        self.book = int(6 * 60 + 330 * rk[1]) if rk[0] < 1 / 15 else None
        # one night a year the tower clock stops at 3:33, for thirty-three minutes
        rc = rng_for(7745, y)
        self.stop_night = int(rc.integers(1, 366))
        self.clock_stopped = doy == self.stop_night
        # one minute a year: the anniversary of the scene's first morning
        self.door = (d.month, d.day) == (9, 27)


    @staticmethod
    def place_comet(day, evening, alt, off, k):
        """Fix tonight's comet on the sky: at the end of evening twilight (or the start of morning
        twilight) it stands `alt` degrees up, `off` degrees round from the sun toward the south."""
        ev = day.sun_events
        when = (ev.get("astronomical_dusk") or ev.get("nautical_dusk") or ev.get("sunset")) if evening else \
               (ev.get("astronomical_dawn") or ev.get("nautical_dawn") or ev.get("sunrise"))
        if when is None:
            return None
        m = min(1439, when.hour * 60 + when.minute)
        saz = float(day.sun_az[m])
        # near the sun's side of the sky, but kept inside the view and clear of the tower
        az = min(saz, 282) - 8 - off if evening else max(saz, 92) + off
        if 125 < az < 150:
            az = 124 if az < 137 else 151
        jd, lst, lat = float(day.jd[m]), float(day.lst[m]), math.radians(day.lat)
        a, z = math.radians(alt), math.radians(az)
        dec = math.asin(math.sin(a) * math.sin(lat) + math.cos(a) * math.cos(lat) * math.cos(z))
        ha = math.atan2(-math.sin(z) * math.cos(a), math.sin(a) * math.cos(lat) - math.cos(a) * math.sin(lat) * math.cos(z))
        return dict(ra=(lst - math.degrees(ha) / 15) % 24, dec=math.degrees(dec), peak=math.sin(math.pi * k), jd=jd)


class MysteryMixin:
    def mysteries(self):
        return self.day.mysteries

    # ------------------------------------------------------------- the sky --
    def comet(self, col):
        c = self.mysteries().comet
        if not c or self.limiting_mag() < 0.5:
            return
        day = self.day
        alt, az = astro.altaz(np.array([c["ra"]]), np.array([c["dec"]]), np.array([self.jd]), day.lat, day.lon)
        alt, az = float(alt[0]), float(az[0])
        if alt < 2:
            return
        W, H, s = self.W, self.H, self.s
        x, y = to_screen(alt, az)
        x, y = x * W, y * H
        bright = c["peak"] * sm(-8, -14, self.sun_alt) * sm(2, 10, alt)
        # the tail streams away from the sun
        dx, dy = self.sky_dir(-self.sunv, alt, az)
        ln = (120 + 140 * c["peak"]) * s
        hz = self.hz
        L = Layer(self, x - ln - 20 * s, y - ln - 20 * s, x + ln + 20 * s, min(hz, y + ln + 20 * s))
        for i in range(60):
            u0, u1 = i / 60, (i + 1) / 60
            curve = 0.18 * u0 * u0 * ln
            p0 = (x + dx * ln * u0 - dy * curve, y + dy * ln * u0 + dx * curve)
            p1 = (x + dx * ln * u1 - dy * 0.18 * u1 * u1 * ln, y + dy * ln * u1 + dx * 0.18 * u1 * u1 * ln)
            L.line([p0, p1], (236, 238, 222), (3 + 40 * u0) * s, a=0.40 * (1 - u0) ** 1.2)
            L.line([(x + dx * ln * 1.25 * u0, y + dy * ln * 1.25 * u0), (x + dx * ln * 1.25 * u1, y + dy * ln * 1.25 * u1)],
                   (170, 200, 255), (1.5 + 6 * u0) * s, a=0.28 * (1 - u0))
        rgb, al = L.arrays()
        al = ndi.gaussian_filter(al, (2.5 * s, 2.5 * s, 0)) * bright
        reg = col[L.y0:L.y1, L.x0:L.x1]
        reg += rgb * al * 0.9
        self._add(col, x, y, 5 * s, np.array([235, 240, 225], np.float32), 1.0 * bright)
        self._add(col, x, y, 16 * s, np.array([190, 225, 205], np.float32), 0.35 * bright)

    # ------------------------------------------------------------- the bay --
    def ghost_ship(self):
        g = self.mysteries().ghost
        if not g:
            return
        t = self.t if self.t < 12 else self.t - 24
        u = (t - g) / 0.75
        if not 0 <= u <= 1 or self.wx.fog < 0.25:
            return
        s, W, H = self.s, self.W, self.H
        x, y = (0.60 + 0.26 * u) * W, 0.652 * H
        a = math.sin(math.pi * u) ** 0.5 * min(1.0, self.wx.fog * 1.5) * 0.55
        pale = np.array([196, 222, 210], np.float32) * (0.55 + 0.45 * min(1.0, self.amb.mean() / 0.3))
        L = Layer(self, x - 90 * s, y - 140 * s, x + 90 * s, y + 10 * s)
        L.poly([(x - 70 * s, y - 14 * s), (x + 64 * s, y - 14 * s), (x + 52 * s, y), (x - 58 * s, y)], pale * 0.8)
        L.poly([(x - 70 * s, y - 14 * s), (x - 78 * s, y - 30 * s), (x - 52 * s, y - 22 * s)], pale * 0.8)
        for mx, mh in ((-34, 110), (6, 128), (42, 96)):
            L.line([(x + mx * s, y - 14 * s), (x + mx * s, y - mh * s)], pale * 0.7, 1.6 * s)
            for k in range(3):
                w0, y0 = (26 - 5 * k) * s, y - (26 + 30 * k) * s
                if y0 < y - mh * s + 8 * s:
                    continue
                rag = [(x + mx * s - w0, y0), (x + mx * s + w0, y0), (x + mx * s + w0 * 0.8, y0 - 22 * s), (x + mx * s - w0 * 0.85, y0 - 22 * s)]
                L.poly(rag, pale, a=0.8)
        L.line([(x - 70 * s, y - 14 * s), (x - 104 * s, y - 40 * s)], pale * 0.7, 1.2 * s)
        rgb, al = L.arrays()
        # not quite there: soft-edged, and fainter toward the waterline
        al = ndi.gaussian_filter(al, (1.6 * s, 1.6 * s, 0))
        rows = np.arange(L.y0, L.y1, dtype=np.float32)[:, None, None]
        al = al * (0.55 + 0.45 * np.clip((y - rows) / (90 * s), 0, 1))
        self.c[L.y0:L.y1, L.x0:L.x1] += rgb * al * a * 0.7
        self.glow(x, y - 50 * s, 120 * s, (150, 200, 180), 0.06 * a / 0.55, tail=0.5)
        self.glow(x + 58 * s, y - 22 * s, 2.2 * s, (170, 255, 200), 0.9 * a / 0.55)

    def far_lights(self):
        """The lantern on the far shore, and the window on the islet where no one lives."""
        my = self.mysteries()
        s, W, H = self.s, self.W, self.H
        if my.lantern and self.sun_alt < -8:
            t0, d = my.lantern
            u = (self.t - t0) / 0.67
            if 0 <= u <= 1:
                xn = 0.20 + 0.27 * (u if d > 0 else 1 - u)
                x, y = xn * W, (VH - 0.0012) * H
                flick = 0.75 + 0.25 * math.sin(self.m * 2.3)
                self.glow(x, y, 1.3 * s, (255, 196, 110), 1.3 * flick)
                self.glow(x, y, 7 * s, (255, 170, 80), 0.10 * flick)
                self.emitters.append((x, y, np.array([255, 190, 100], np.float32), 0.35 * flick, self.hz))
        if my.cottage and self.sun_alt < -8 and hasattr(self, "cottage"):
            t0, dur = my.cottage
            if t0 <= self.t <= t0 + dur:
                x, y = self.cottage
                flick = 0.6 + 0.4 * abs(math.sin(self.m * 1.7))
                self.glow(x, y, 1.1 * s, (255, 200, 120), 1.4 * flick)
                self.emitters.append((x, y, np.array([255, 190, 110], np.float32), 0.25 * flick, self.hz))

    def whale(self):
        w = self.mysteries().whale
        if not w:
            return
        m0, xn = w
        k = self.m - m0
        if not 0 <= k <= 4:
            return
        s, W, H = self.s, self.W, self.H
        x, y = xn * W, 0.646 * H
        p = 1.8 * (0.35 + 1.3 * max(0.0, (y / H - 0.6) / 0.4))
        dark = self.lit((44, 46, 52), [0, 0.6, 0.8])
        L = Layer(self, x - 80 * s, y - 90 * s, x + 80 * s, y + 10 * s)
        if k in (0, 2):     # the blow
            for i in range(14):
                a = (i / 13 - 0.5) * 0.7
                L.line([(x, y - 2 * s), (x + math.sin(a) * 26 * s * p, y - math.cos(a) * (48 + 10 * k) * s * p)],
                       self.lit((236, 240, 244), [0, 0.6, 0.8]), 3.5 * s * p, a=0.25)
        if k in (1, 2):     # the back rolling through
            L.poly([(x - 40 * s * p, y), (x - 10 * s * p, y - 9 * s * p), (x + 30 * s * p, y - 5 * s * p), (x + 44 * s * p, y)], dark)
            L.poly([(x + 8 * s * p, y - 8 * s * p), (x + 14 * s * p, y - 15 * s * p), (x + 18 * s * p, y - 7 * s * p)], dark)
        if k == 3:          # the flukes, going down
            L.line([(x, y), (x + 2 * s * p, y - 16 * s * p)], dark, 5 * s * p)
            L.poly([(x + 2 * s * p, y - 16 * s * p), (x - 18 * s * p, y - 26 * s * p), (x - 4 * s * p, y - 18 * s * p),
                    (x + 2 * s * p, y - 20 * s * p), (x + 8 * s * p, y - 18 * s * p), (x + 22 * s * p, y - 26 * s * p)], dark)
        if k == 4:          # only the slick it leaves
            L.ellipse(x, y, 40 * s * p, 4 * s * p, self.lit((120, 150, 170), [0, 0.3, 1]), a=0.3)
        L.composite()

    # ------------------------------------------------------------ the hill --
    def footprints(self):
        my = self.mysteries()
        if not my.prints or self.wx.snow_cover < 0.3 or self.m < my.prints:
            return
        # fresh snow after they were made slowly fills them in
        fill = float(self.day.wx.snowfall_cmph[my.prints:self.m + 1].sum()) / 60 if self.m > my.prints else 0.0
        a = max(0.0, 1 - fill / 2.0) * min(1.0, self.wx.snow_cover * 1.5)
        if a < 0.05:
            return
        s, W, H = self.s, self.W, self.H
        L = Layer(self, 0, 0.6 * H, 0.4 * W, H)
        p0, p1 = np.array([0.205 * W, 0.83 * H]), np.array([0.075 * W, 0.70 * H])
        dent = self.lit((150, 160, 180), [0, 0.2, 1])
        for i in range(26):
            u = i / 25
            x, y = p0 + (p1 - p0) * u
            side = 1 if i % 2 else -1
            pp = 0.35 + 1.3 * max(0.0, (y / H - 0.6) / 0.4)
            nx, ny = -(p1 - p0)[1], (p1 - p0)[0]
            nn = math.hypot(nx, ny)
            x += side * nx / nn * 4 * s * pp
            y += side * ny / nn * 4 * s * pp
            L.ellipse(x, y, 2.6 * s * pp, 1.3 * s * pp, dent, a=0.55 * a)
        L.composite()

    def bottle(self):
        b = self.mysteries().bottle
        if not b:
            return
        xn, arriving = b
        if arriving and self.m < 600:
            return
        s, W, H = self.s, self.W, self.H
        y = (hill_edge_y(np.array([xn]))[0] + 0.62 * shore_band(np.array([xn]))[0]) * H
        x = xn * W
        L = Layer(self, x - 12 * s, y - 8 * s, x + 12 * s, y + 6 * s)
        glass = self.lit((60, 120, 80), [0.3, 0.6, 0.7])
        L.poly([(x - 6 * s, y), (x + 3 * s, y - 2.5 * s), (x + 4 * s, y + 0.5 * s), (x - 5 * s, y + 2.5 * s)], glass)
        L.line([(x + 3.5 * s, y - 1 * s), (x + 7 * s, y - 2.2 * s)], glass * 1.2, 1.4 * s)
        L.ellipse(x + 7.3 * s, y - 2.3 * s, 0.9 * s, 0.9 * s, self.lit((150, 110, 70), [0, 0.6, 0.8]))
        L.line([(x - 4 * s, y + 0.5 * s), (x + 1 * s, y - 1 * s)], self.lit((236, 230, 210), [0, 0.6, 0.8]), 1.0 * s)
        L.composite()
        if self.sun_str > 0.3:
            self.glow(x - 1 * s, y - 1 * s, 1.2 * s, (255, 255, 240), 0.8 * self.sun_str * (0.5 + 0.5 * math.sin(self.m)))

    def book(self):
        b = self.mysteries().book
        if not b or not (b - 360 <= self.m <= b) or self.wx.rain > 0.05:
            return
        s, W, H = self.s, self.W, self.H
        x, y = BENCH[0] * W + 46 * s, BENCH[1] * H - 42 * s
        L = Layer(self, x - 16 * s, y - 12 * s, x + 16 * s, y + 6 * s)
        cover = self.lit((110, 40, 36), [0, 0.6, 0.8], x, y)
        page = self.lit((238, 232, 214), [0, 0.6, 0.8], x, y)
        L.poly([(x - 11 * s, y + 1 * s), (x + 11 * s, y + 1 * s), (x + 10 * s, y - 2 * s), (x - 10 * s, y - 2 * s)], cover)
        L.poly([(x - 10 * s, y - 1 * s), (x, y - 2 * s), (x, y - 6 * s), (x - 9 * s, y - 4 * s)], page)
        lift = 2 + 4 * abs(math.sin(self.m * 0.9)) * min(1.0, self.wx.wind_ms / 5)
        L.poly([(x, y - 2 * s), (x + 10 * s, y - 1 * s), (x + 9 * s, y - (4 + lift) * s), (x, y - 6 * s)], page * 0.95)
        L.composite()

    def door_light(self):
        """The one minute a year."""
        if not self.mysteries().door or self.m != 8 * 60 + 57:
            return
        s = self.s
        cx, yb = self.tw["cx"], self.tw["yb"]
        dw, dh = 34 * s, 128 * s
        dyb = yb + 12 * s
        L = Layer(self, cx - 120 * s, dyb - dh - 10 * s, cx + 120 * s, dyb + 120 * s)
        L.poly([(cx - dw + 6 * s, dyb), (cx + dw * 0.2, dyb), (cx + dw * 0.2, dyb - dh + dw), (cx - dw + 6 * s, dyb - dh + dw)], (255, 214, 140))
        L.composite()
        L = Layer(self, cx - 120 * s, dyb - 4 * s, cx + 120 * s, dyb + 140 * s)
        L.poly([(cx - dw + 6 * s, dyb), (cx + dw * 0.2, dyb), (cx + 70 * s, dyb + 130 * s), (cx - 90 * s, dyb + 130 * s)], (255, 210, 130), a=0.35)
        L.composite()
        self.glow(cx - 0.3 * dw, dyb - dh * 0.4, 50 * s, (255, 200, 120), 0.35, tail=0.4)
