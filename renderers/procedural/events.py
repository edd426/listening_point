"""The day's schedule: who is where at each minute.

Everything moving is a smooth, seeded function of the minute, so consecutive frames differ by a
little and the same date always renders the same way.
"""
import math

import numpy as np

import astro

# the sailing boat's round trip on the bay, as fractions of the frame, starting and ending at the mooring
MOORED = (0.886, 0.789)
ROUTE = [MOORED, (0.885, 0.795), (0.930, 0.740), (0.930, 0.680), (0.860, 0.645), (0.780, 0.628), (0.690, 0.624),
         (0.615, 0.636), (0.600, 0.665), (0.680, 0.700), (0.790, 0.750), (0.870, 0.785), MOORED]

# annual meteor showers: (peak day of year, half-width in days, zenithal hourly rate, radiant RA h, Dec deg)
SHOWERS = [(3, 1.0, 80, 15.33, 49.5), (112, 1.5, 18, 18.07, 33.3), (125, 3.0, 30, 22.5, -1.0),
           (224, 3.0, 100, 3.2, 58.0), (294, 3.0, 20, 6.33, 15.6), (321, 1.5, 15, 10.27, 21.6),
           (348, 2.0, 120, 7.47, 32.2)]


def smoothstep(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def vnoise(seed, t, period):
    """Smooth 1-D value noise in [-1, 1]: knots every `period` minutes."""
    k = math.floor(t / period)
    f = smoothstep(t / period - k)
    a, b = (np.random.default_rng([seed % 2 ** 32, (k + j) % 2 ** 32]).uniform(-1, 1) for j in (0, 1))
    return a + (b - a) * f


def catmull(pts, u):
    """Point and tangent on a Catmull-Rom spline through pts, u in [0, 1]."""
    n = len(pts) - 1
    x = min(u * n, n - 1e-6)
    i = int(x)
    t = x - i
    p = [np.array(pts[max(0, min(n, j))], float) for j in (i - 1, i, i + 1, i + 2)]
    a = 2 * p[1]
    b = p[2] - p[0]
    c = 2 * p[0] - 5 * p[1] + 4 * p[2] - p[3]
    d = -p[0] + 3 * p[1] - 3 * p[2] + p[3]
    pos = 0.5 * (a + b * t + c * t * t + d * t ** 3)
    tan = 0.5 * (b + 2 * c * t + 3 * d * t * t)
    return pos, tan


class Schedule:
    def __init__(self, day):
        self.day = day
        d = day.date
        self.seed = d.toordinal()
        rng = np.random.default_rng([self.seed, 1])
        ev = day.sun_events
        hours = lambda k, dflt: (ev[k].hour + ev[k].minute / 60) if ev.get(k) else dflt
        self.sunrise, self.sunset = hours("sunrise", 6.0), hours("sunset", 18.0)
        # the boat goes out on fair days in the sailing season
        wx = day.wx
        self.trip = None
        go = rng.random() < 0.85 * day.season.boating
        dep = rng.uniform(max(8.0, self.sunrise + 1.0), 10.5)
        ret = min(rng.uniform(16.0, 18.5), self.sunset - 0.5)
        if go and ret - dep > 3:
            i0, i1 = int(dep * 60), int(ret * 60)
            bad = (wx.rain[i0:i1].max() > 0.3 or wx.thunder[i0:i1].max() > 0 or wx.fog[i0:i1].max() > 0.5
                   or wx.wind_ms[i0:i1].max() > 10 or wx.snow[i0:i1].max() > 0.1)
            if not bad:
                self.trip = (dep, ret)
        # gulls wheeling over the bay by day: (start h, duration h, centre x, y, radius, speed, phase)
        self.gulls = []
        for k in range(int(rng.integers(5, 10))):
            t0 = rng.uniform(self.sunrise + 0.5, self.sunset - 1.5)
            self.gulls.append((t0, rng.uniform(0.5, 2.5), rng.uniform(0.5, 0.95), rng.uniform(0.15, 0.40),
                               rng.uniform(0.02, 0.07), rng.uniform(0.3, 1.0) * rng.choice([-1, 1]), rng.uniform(0, 6.28)))
        self.meteors = self._meteors(np.random.default_rng([self.seed, 2]))
        # the observer's evening and morning: lamps off at bedtime, on again at waking if it is still dark
        self.bedtime = rng.uniform(22.7, 24.8)
        self.wake = rng.uniform(6.0, 7.4)
        r2 = np.random.default_rng([self.seed, 4])
        se = day.season
        # a heron fishes the shallows on some mornings; an owl sits in the tree on some nights
        self.heron = r2.random() < 0.55
        self.heron_x = r2.uniform(0.74, 0.95)
        self.owl = r2.random() < 0.45
        self.owl_from, self.owl_to = r2.uniform(20.5, 23.5), r2.uniform(2.5, 5.0)
        # ships along the horizon: (start h, hours to cross, direction, kind)
        self.ships = []
        for _ in range(int(r2.choice([0, 1, 1, 2, 2, 3]))):
            self.ships.append((r2.uniform(-1, 24), r2.uniform(0.9, 2.2), int(r2.choice([-1, 1])),
                               str(r2.choice(["cargo", "ferry", "tall"], p=[0.6, 0.3, 0.1]))))
        # geese passing over in the migration months: (start h, direction, height on screen)
        self.geese = [(r2.uniform(self.sunrise + 0.5, self.sunset - 0.5), int(r2.choice([-1, 1])), r2.uniform(0.08, 0.3))
                      for _ in range(int(r2.integers(1, 4) if r2.random() < se.geese else 0))]
        self.cat = self._cat_plan(np.random.default_rng([self.seed, 5]))

    # ------------------------------------------------------------------ cat --
    def _cat_plan(self, r):
        """Where the cat spends each stretch of the day: [(start minute, spot)], spot in
        wall, step, bench, grass, lamp, inside."""
        wx, day = self.day.wx, self.day
        plan, m = [], 0
        while m < 1440:
            t = m / 60
            sun = float(day.sun_alt[m])
            wet = wx.rain[m] > 0.1 or wx.snow[m] > 0.1 or wx.drizzle[m] > 0.4
            cold, warm = wx.temp_c[m] < 1, wx.temp_c[m] > 11
            if wet or (sun < -6 and cold):
                spot = "inside" if r.random() < 0.8 or wet else "step"
            elif sun < -6:
                spot = str(r.choice(["lamp", "step", "grass", "inside"], p=[0.35, 0.25, 0.2, 0.2]))
            elif t < 10:
                spot = str(r.choice(["step", "wall", "grass"], p=[0.3, 0.35, 0.35]))
            elif t < 16:
                spot = str(r.choice(["bench", "grass", "wall", "step"], p=[0.5 if warm else 0.2, 0.2, 0.15, 0.15 if warm else 0.45]))
            else:
                spot = str(r.choice(["wall", "bench", "grass", "step"], p=[0.45, 0.2, 0.15, 0.2]))
            plan.append((m, spot, r.uniform(0, 1), r.uniform(0, 1)))
            m += int(r.integers(35, 120))
        return plan

    def cat_at(self, m):
        """(spot, previous spot, minutes since arriving, two seeds for the spot, two for the last one)."""
        i = max(k for k, p in enumerate(self.cat) if p[0] <= m)
        cur, prev = self.cat[i], self.cat[i - 1] if i else self.cat[i]
        return cur[1], prev[1], m - cur[0], cur[2:], prev[2:]

    # --------------------------------------------------------------- others --
    def ship_positions(self, t):
        """Ships on the horizon now: [(x, direction, kind)], x as a fraction of the frame."""
        out = []
        for (t0, dur, d, kind) in self.ships:
            for tt in (t, t + 24, t - 24):
                u = (tt - t0) / dur
                if 0 <= u <= 1:
                    x = -0.05 + 0.65 * u if d > 0 else 0.60 - 0.65 * u
                    out.append((x, d, kind))
        return out

    # ----------------------------------------------------------------- boat --
    def boat(self, t):
        """(x, y, facing) of the sailing boat at clock time t (hours), or None when it is moored."""
        if not self.trip:
            return None
        dep, ret = self.trip
        if not dep <= t <= ret:
            return None
        u = (t - dep) / (ret - dep)
        u = u + 0.03 * vnoise(self.seed + 7, t * 60, 37) * math.sin(math.pi * u)
        u = 0.5 - 0.5 * math.cos(math.pi * min(1.0, max(0.0, u)))
        pos, tan = catmull(ROUTE, u)
        return pos[0], pos[1], (1 if tan[0] >= 0 else -1)

    # ---------------------------------------------------------------- birds --
    def sky_gulls(self, t):
        """Gulls in the air at time t: list of (x, y, size, wing)."""
        out = []
        for i, (t0, dur, cx, cy, rad, spd, ph) in enumerate(self.gulls):
            if not t0 <= t <= t0 + dur:
                continue
            a = ph + spd * (t - t0) * 2 * math.pi
            x = cx + rad * math.cos(a) + 0.02 * (t - t0)
            y = cy + rad * 0.45 * math.sin(a)
            wing = math.sin(t * 60 * 1.7 + i)
            out.append((x, y, 0.8 + 0.4 * ((i * 7) % 5) / 4, wing))
        return out

    def pier_gulls(self, m):
        """Which of four perches on the pier are taken at minute m (by day)."""
        t = m / 60
        if not self.sunrise + 0.5 < t < self.sunset - 0.3:
            return []
        return [k for k in range(4) if np.random.default_rng([self.seed, 3, k, m // (11 + 4 * k)]).random() < 0.45]

    # -------------------------------------------------------------- meteors --
    def _meteors(self, rng):
        """A few sporadic meteors a night, many more on shower peaks: {minute: (ra, dec, length, angle, bright)}."""
        out = {}
        doy = self.day.date.timetuple().tm_yday
        for m in range(1440):
            t = m / 60
            if self.sunset + 1.2 < t or t < self.sunrise - 1.2:
                rate = 0.06
                for (peak, wid, zhr, ra, dec) in SHOWERS:
                    dd = min(abs(doy - peak), 365 - abs(doy - peak))
                    rate += zhr / 60 * 0.05 * math.exp(-(dd / wid) ** 2)
                if rng.random() < rate:
                    shower = [s for s in SHOWERS if min(abs(doy - s[0]), 365 - abs(doy - s[0])) < 2 * s[1]]
                    out[m] = (shower[0] if shower and rng.random() < 0.7 else None, rng.uniform(0, 1, 4))
        return out

    def meteor(self, m):
        """Screen-space streak for minute m, as ((x0, y0), (x1, y1), brightness), or None."""
        if m not in self.meteors:
            return None
        shower, r = self.meteors[m]
        day = self.day
        x0, y0 = 0.08 + 0.84 * r[0], 0.05 + 0.33 * r[1]
        if shower:
            ra, dec = shower[3], shower[4]
            alt, az = astro.altaz(np.array([ra]), np.array([dec]), np.array([day.jd[m]]), day.lat, day.lon)
            rx, ry = 0.5 + (az[0] - 180) / 220, 0.58 - alt[0] / 70 * 0.58
            ang = math.atan2(y0 - ry, x0 - rx)
        else:
            ang = r[2] * 2 * math.pi
        ln = 0.04 + 0.08 * r[3]
        return (x0, y0), (x0 + ln * math.cos(ang), y0 + ln * math.sin(ang) * 1.6), 0.5 + 0.5 * r[3]

    # ---------------------------------------------------------------- sheep --
    def sheep(self, t, lambs=False):
        """Positions and poses of the flock: list of (x, y, facing, grazing, size)."""
        night = (t < self.sunrise - 0.4) or (t > self.sunset + 0.6)
        fold = [(0.050, 0.772), (0.078, 0.782), (0.064, 0.790), (0.100, 0.797), (0.088, 0.776)]
        # how far into the night-fold walk the flock is (they drift over at dusk, spread out after dawn)
        k = smoothstep((t - (self.sunset + 0.1)) / 0.6) if t > 12 else 1 - smoothstep((t - (self.sunrise - 0.2)) / 0.8)
        out = []
        n = 4 + (2 if lambs else 0)
        for i in range(n):
            lamb = i >= 4
            mother = i - 4 if lamb else i
            bx = 0.05 + 0.2 * np.random.default_rng([self.seed, 50, mother]).random()
            by = 0.71 + 0.12 * np.random.default_rng([self.seed, 51, mother]).random()
            gx = bx + 0.035 * vnoise(self.seed * 10 + mother, t * 60, 47)
            gy = by + 0.018 * vnoise(self.seed * 10 + mother + 5, t * 60, 53)
            if lamb:
                gx += 0.018 + 0.006 * vnoise(self.seed + 60 + i, t * 60, 9)
                gy += 0.006
            fx, fy = fold[mother % len(fold)]
            if lamb:
                fx, fy = fx + 0.012, fy + 0.004
            x, y = gx + (fx - gx) * k, gy + (fy - gy) * k
            dx = vnoise(self.seed * 10 + mother, t * 60 + 1, 47) - vnoise(self.seed * 10 + mother, t * 60 - 1, 47)
            facing = 1 if dx >= 0 else -1
            grazing = (not night) and k < 0.5 and np.random.default_rng([self.seed, 52, i, int(t * 60) // 3]).random() < 0.6
            out.append((x, y, facing, grazing, 0.55 if lamb else 1.0))
        return sorted(out, key=lambda p: p[1])

    def awake(self, t):
        bt = self.bedtime
        return (t < bt) and (t > self.wake) if bt <= 24 else (t > self.wake or t < bt - 24)

    # ----------------------------------------------------------- lighthouse --
    def beam_angle(self, m):
        return math.radians((m * 137.508 + 30) % 360)
