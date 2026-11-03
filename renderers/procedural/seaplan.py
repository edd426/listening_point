"""The sea's boats and animals (v3 phase 4, part 2): who is out on the bay, and where, minute by minute.

- the creel boat working the string of pot floats on some mornings (a weekly rhythm, by the weather);
- an extra yacht or two on fair days with a sailing breeze, few in winter;
- the island ferry on its timetable, keeping the channel beacon to port on the way in;
- seals hauled out on the skerry at low water, one pale cow always on her own knob, and now and then a head
  in the water;
- a cormorant drying its wings on the skerry's top knob while it is dry;
- gannets diving offshore in season, and a rare pod of dolphins passing across the bay.

Everything is decided by the date, the clock, the weather and the tide, each from its own seeded generator
(90-99, or the low water's own count for the seals), so nothing that was already scheduled moves and a given
minute always renders the same. The seals' haul-outs are keyed to the low water itself, so one that spans
midnight is the same on both days. sealife.py draws all of it. In reference mode (day.py) the plan is empty.

Positions are world units (core.FrameBase.proj: the camera stands 1 unit, about 15 m, above the sea; x to
the right (west), z ahead (south), y up) or frame fractions, as noted. Boats move slower than life (as the
sailing boat always has), so nothing jumps from one minute to the next.
"""
import math

import numpy as np

from core import ALT_TOP, AZ_SPAN, VH
from events import catmull, smoothstep, vnoise
from season import bump
from water import BEACON, POTS, SKERRY, SKERRY_HALF, TR, sea_point, skerry_field

T_M2 = 12.4206012 / 24                 # the tide's half-day, in days
JD0 = 2461000.0 - 0.335 * T_M2         # a low water: low waters are counted from it (seals)

# --------------------------------------------------------------- the ferry --
# The island ferry's way, mainland to island, as frame fractions of its waterline: in from beyond the right
# edge (the mainland slip is just out of sight), across the bay, past the channel beacon on its far side
# (keeping it to port), then a turn to starboard and away to the island's harbour on the horizon.
FERRY_WAY = [(1.075, 0.5912), (0.95, 0.5955), (0.84, 0.5995), (0.73, 0.6035), (0.645, 0.6085), (0.597, 0.6105),
             (0.5855, 0.6005)]
FERRY_HARBOUR = (0.5812, 0.5817)
FERRY_L, FERRY_B = 36.0, 9.0           # length and beam, metres
FERRY_OMEGA = (0.10, 0.25)             # its pace: radians a minute across the view, then the fraction of its
                                       # distance it runs off each minute once it is heading for the island
# timetables (local clock, minutes): (first day of year, last, mainland departures, island departures)
FERRY_TABLES = (
    (152, 258, (8 * 60, 13 * 60, 19 * 60), (9 * 60 + 45, 14 * 60 + 45, 20 * 60 + 45)),        # summer
    (91, 151, (8 * 60 + 30, 13 * 60 + 30, 17 * 60 + 30), (10 * 60 + 15, 15 * 60 + 15, 19 * 60)),   # spring
    (259, 304, (8 * 60 + 30, 13 * 60 + 30, 17 * 60 + 30), (10 * 60 + 15, 15 * 60 + 15, 19 * 60)),  # autumn
    (305, 366, (9 * 60, 15 * 60 + 30), (10 * 60 + 45, 17 * 60)),                               # winter
    (1, 90, (9 * 60, 15 * 60 + 30), (10 * 60 + 45, 17 * 60)),
)

# ------------------------------------------------------------ the creel boat --
CREEL_L, CREEL_B = 7.5, 2.8
CREEL_FROM = (0.556, 0.733)            # out of sight behind the point (the hill), where it comes and goes
CREEL_DAYS = (1, 3, 5)                 # Tuesday, Thursday, Saturday in the season; Saturday in winter

# ------------------------------------------------------------------ yachts --
# lanes for extra sails, as frame fractions of the waterline (from, to): far out along the left of the bay
# in front of the far coast (behind the tower and the tree), and across the outer bay right of the beacon
YACHT_LANES = {"far": ((-0.07, 0.5915), (0.565, 0.5958)), "bay": ((0.625, 0.6175), (1.07, 0.6125))}

# ------------------------------------------------------------------- seals --
# spots on the skerry (a across, b along it, as skerry_field): the pale cow's knob first; the cormorant has
# the top knob (a -0.29, b 0.15)
SEAL_SPOTS = ((0.23, 0.08), (0.65, 0.22), (-0.56, -0.08), (-0.09, -0.29))
SEAL_P = (0.85, 0.55, 0.45, 0.35)      # how often each comes to a low water
CORMORANT_KNOB = (-0.29, 0.15)


def to_frame(X, Y, Z):
    """World point to frame fractions (as FrameBase.proj)."""
    az = math.degrees(math.atan2(X, Z))
    alt = math.degrees(math.atan2(Y - 1.0, math.hypot(X, Z)))
    return 0.5 + az / AZ_SPAN, VH - alt / ALT_TOP * VH


def skerry_point(a, b):
    """World (X, Z) and the rock's height at skerry field point (a, b)."""
    X0, Z0, _ = sea_point(*SKERRY)
    az = math.atan2(X0, Z0)
    fx, fz = math.sin(az), math.cos(az)
    lx, lz = math.cos(az), -math.sin(az)
    ha, hb = SKERRY_HALF
    h, _ = skerry_field()
    nb, na = h.shape
    i = int(round((a + 1) / 2 * (na - 1)))
    j = int(round((b + 1) / 2 * (nb - 1)))
    return X0 + a * ha * lx + b * hb * fx, Z0 + a * ha * lz + b * hb * fz, float(h[j, i])


def heading_of(dx, dz):
    """A unit heading in world (x, z) from a step."""
    n = math.hypot(dx, dz) or 1.0
    return dx / n, dz / n


def box_of(x, y, half_w, up, down=0.0):
    """A frame-fraction box (x0, y0, x1, y1) round a thing standing at (x, y)."""
    return (x - half_w, y - up, x + half_w, y + down)


def boxes_meet(a, b, pad=0.006):
    return a[0] - pad < b[2] and b[0] - pad < a[2] and a[1] - pad < b[3] and b[1] - pad < a[3]


class FerryWay:
    """The ferry's way as a dense polyline in world units, with the time (minutes) it takes to reach each
    point: slow across the near bay (as if just off its slip), faster once it has turned for the island."""

    def __init__(self):
        pts = [sea_point(*p)[:2] for p in FERRY_WAY]
        near = [catmull(pts, u)[0] for u in np.linspace(0, 1, 160)]
        Xh, Zh, _ = sea_point(*FERRY_HARBOUR)
        last = np.array(near[-1])
        far = [last + (np.array([Xh, Zh]) - last) * u for u in np.linspace(0, 1, 200)[1:]]
        P = np.array(near + far, np.float64)
        seg = np.hypot(*np.diff(P, axis=0).T)
        s = np.concatenate([[0.0], np.cumsum(seg)])
        D = np.hypot(P[:, 0], P[:, 1])
        # where it passes the beacon (nearest to it), and where it has turned for the island
        bx, bz, _ = sea_point(*BEACON)
        k_turn = len(near) - 1
        w = smoothstep_arr((s - s[k_turn] + 4.0) / 10.0)
        omega = FERRY_OMEGA[0] * (1 - w) + FERRY_OMEGA[1] * w
        v = omega * D                                   # world units a minute
        dt = seg / (0.5 * (v[1:] + v[:-1]))
        self.P, self.s, self.t = P, s, np.concatenate([[0.0], np.cumsum(dt)])
        self.T = float(self.t[-1])
        self.beacon_pass = int(np.argmin(np.hypot(P[:, 0] - bx, P[:, 1] - bz)))

    def at(self, tau, back=False):
        """Where the ferry is tau minutes into a crossing, its heading (world unit vector), its speed (units a
        minute) and how far in (0..1) it is; None outside the crossing. back: island to mainland."""
        if not 0 <= tau <= self.T:
            return None
        u = self.T - tau if back else tau
        x = float(np.interp(u, self.t, self.P[:, 0]))
        z = float(np.interp(u, self.t, self.P[:, 1]))
        k = int(min(len(self.t) - 2, max(0, np.searchsorted(self.t, u) - 1)))
        dx, dz = self.P[k + 1] - self.P[k]
        if back:
            dx, dz = -dx, -dz
        h = heading_of(dx, dz)
        sp = float(np.hypot(*(self.P[k + 1] - self.P[k])) / max(1e-6, self.t[k + 1] - self.t[k]))
        return x, z, h, sp, u / self.T


def smoothstep_arr(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


FERRY = None


def ferry_way():
    global FERRY
    if FERRY is None:
        FERRY = FerryWay()
    return FERRY


class SeaPlan:
    """The day's plan for the boats and animals of the bay."""

    def __init__(self, day):
        self.day = day
        self.seed = day.date.toordinal()
        self.doy = day.season.doy
        ev = day.events
        self.sunrise, self.sunset = ev.sunrise, ev.sunset
        # the spoiler's waters are left to it: nothing new on the bay while it is there (docs/SPOILERS.md)
        w = day.mysteries.whale
        self.quiet = (w[0] - 20, w[0] + 25) if w else None
        self.ferry = self._ferry()
        self.creel = self._creel()
        self.yachts = self._yachts()
        self.gannets = self._gannets()
        self.dolphins = self._dolphins()
        self.cormorant = self._cormorant()
        self.seal_swims = self._seal_swims()

    # ------------------------------------------------------------ helpers --
    def wx_ok(self, m0, m1, wind=99.0, gust=99.0, fog=1.0, vis=0.0, rain=1.0):
        wx = self.day.wx
        a, b = max(0, int(m0)), min(1440, int(m1) + 1)
        if b <= a:
            return False
        return bool(wx.wind_ms[a:b].max() <= wind and wx.gust_ms[a:b].max() <= gust and wx.fog[a:b].max() <= fog
                    and wx.visibility_m[a:b].min() >= vis and max(wx.rain[a:b].max(), 0.6 * wx.drizzle[a:b].max()) <= rain
                    and wx.thunder[a:b].max() == 0 and wx.snow[a:b].max() <= max(rain, 0.05))

    def is_quiet(self, m0, m1):
        q = self.quiet
        return bool(q and m0 < q[1] and q[0] < m1)

    def sail_box(self, m):
        """The sailing boat's box now (frame fractions), or None when it is moored."""
        b = self.day.events.boat(m / 60)
        if not b:
            return None
        x, y, _ = b
        sz = 170 / 3840 * (y - VH) / (0.789 - VH)
        return box_of(x, y, 0.6 * sz, 1.25 * sz * 1.6, 0.2 * sz * 1.6)

    def ship_boxes(self, m):
        out = []
        for xn, _, kind in self.day.events.ship_positions(m / 60):
            out.append(box_of(xn, VH, 0.011, 0.018, 0.003))
        return out

    def clear_of(self, boxes_at, m0, m1, others):
        """Whether a thing whose boxes (a function of the minute) keep clear of every box in `others` (functions
        of the minute returning a box, a list of boxes or None) from minute m0 to m1."""
        for m in range(int(m0), int(m1) + 1, 2):
            mine = boxes_at(m)
            if not mine:
                continue
            for f in others:
                theirs = f(m)
                if theirs is None:
                    continue
                if isinstance(theirs, tuple):
                    theirs = [theirs]
                for a in mine:
                    for b in theirs:
                        if b is not None and boxes_meet(a, b):
                            return False
        return True

    # --------------------------------------------------------------- ferry --
    def _ferry(self):
        """The crossings of the day: [(start minute, back, late)]: back is island to mainland. A fixed timetable
        by the season, one round trip fewer on Sundays, none in a gale; a crossing runs a few minutes late
        when that keeps it clear of the sailing boat and the ships on the horizon."""
        r = np.random.default_rng([self.seed, 90])
        way = ferry_way()
        out = []
        table = next(t for t in FERRY_TABLES if t[0] <= self.doy <= t[1])
        sunday = self.day.date.weekday() == 6
        legs = [(m, False) for m in table[2]] + [(m, True) for m in table[3]]
        if sunday:
            legs = [l for l in legs if l[0] not in (table[2][0], table[3][0])]
        for m0, back in sorted(legs):
            jitter = int(r.integers(0, 4))
            if not self.wx_ok(m0, m0 + way.T, wind=15.0, gust=22.0):
                continue                     # a gale: the crossing is cancelled
            for late in range(jitter, jitter + 27, 3):
                start = m0 + late
                if self.is_quiet(start, start + way.T):
                    continue
                if self.clear_of(lambda m: self._ferry_boxes(m, [(start, back, late)]), start, start + way.T,
                                 [self.sail_box, self.ship_boxes]):
                    out.append((start, back, late))
                    break
        return out

    def ferry_at(self, m, crossings=None):
        """The ferry now: (X, Z, heading, speed, how far in, back), or None."""
        way = ferry_way()
        for start, back, _ in (self.ferry if crossings is None else crossings):
            f = way.at(m - start, back)
            if f:
                return f + (back,)
        return None

    def _ferry_boxes(self, m, crossings=None):
        f = self.ferry_at(m, crossings)
        if not f:
            return None
        X, Z = f[0], f[1]
        x, y = to_frame(X, 0, Z)
        D = math.hypot(X, Z)
        k = 1 / math.radians(AZ_SPAN) / D / 15           # frame widths per metre at that distance
        kv = VH / math.radians(ALT_TOP) / D / 15         # frame heights per metre
        return [box_of(x, y, 0.5 * FERRY_L * k, 13 * kv, 1.5 * kv)]

    # ---------------------------------------------------------- creel boat --
    def _creel(self):
        """The creel boat's morning at the pots, or None: (start minute, plan) where plan is a list of
        (minute from start, what, pot): it comes round the point, hauls each pot of the string from the dahn
        in toward the shore (alongside, hauling with the float aboard, setting the pot again, on to the next),
        and goes back round the point. Tuesdays, Thursdays and Saturdays in the season (Saturdays in winter),
        three weeks in four, by the morning's weather."""
        r = np.random.default_rng([self.seed, 91])
        go, u, haul = r.random(), r.random(), r.integers(2, 4, 5)
        season = bump(self.doy, 75, 100, 310, 335)
        wd = self.day.date.weekday()
        days = CREEL_DAYS if season > 0.3 else (5,)
        if wd not in days or go > 0.75:
            return None
        plan, t = [("come", 0, 0)], 7
        for i in range(5):
            plan.append(("alongside", i, t))
            t += 1
            plan.append(("haul", i, t))
            t += int(haul[i])
            plan.append(("set", i, t))
            t += 1
            if i < 4:
                plan.append(("next", i, t))
                t += 1
        plan.append(("turn", 4, t))
        t += 3
        plan.append(("go", 4, t))
        t += 7
        plan.append(("gone", 4, t))
        lo = max(self.sunrise + 0.5, 6.0) * 60
        hi = 10.5 * 60
        if hi <= lo:
            return None
        base = int(lo + (hi - lo) * u)
        for shift in (0, 25, -25, 50, -50, 75):
            m0 = base + shift
            if m0 < lo - 1 or m0 + t > 12.5 * 60:
                continue
            if not self.wx_ok(m0, m0 + t, wind=10.0, gust=15.0, fog=0.3, vis=2000, rain=0.3):
                return None
            if self.is_quiet(m0, m0 + t):
                continue
            box = lambda m, m0=m0: [box_of(0.69, 0.745, 0.075, 0.06, 0.02)] if m0 <= m <= m0 + t else None
            if self.clear_of(box, m0, m0 + t, [self.sail_box]):
                return (m0, plan, t)
        return None

    def creel_at(self, m):
        """The creel boat's state now: (what, pot, fraction through it, minutes in) or None."""
        if not self.creel:
            return None
        m0, plan, total = self.creel
        k = m - m0
        if not 0 <= k < total:
            return None
        for j in range(len(plan) - 1):
            what, pot, t0 = plan[j]
            t1 = plan[j + 1][2]
            if t0 <= k < t1:
                return what, pot, (k - t0 + 0.5) / (t1 - t0), k
        return None

    def pot_aboard(self, m):
        """Which pot's float is aboard the creel boat now (hauled with its pot), or None."""
        c = self.creel_at(m)
        return c[1] if c and c[0] == "haul" else None

    # -------------------------------------------------------------- yachts --
    def _yachts(self):
        """Extra sails: on some fair days with a sailing breeze, one or two yachts pass along a lane of the bay,
        on whichever course the wind allows. [dict(lane, back, m0, m1, hull, sails, seed)]."""
        r = np.random.default_rng([self.seed, 92])
        season = max(bump(self.doy, 95, 125, 270, 300), 0.12)
        p, two = r.random(), r.random()
        picks = [(str(r.choice(["far", "bay"])), float(r.random()), float(r.random()), int(r.integers(4)),
                  int(r.integers(4)), int(r.integers(1 << 30))) for _ in range(2)]
        if p > 0.6 * season:
            return []
        n = 2 if two < 0.35 else 1
        out = []
        for lane, u, dur_u, hull, sails, seed in picks[:n]:
            dur = int((80 + 40 * dur_u) if lane == "far" else (55 + 30 * dur_u))
            base = int((10.0 + 6.5 * u) * 60)
            ok = None
            for shift in (0, 20, -20, 40, -40, 60):
                m0 = base + shift
                m1 = m0 + dur
                if m0 < (self.sunrise + 1.5) * 60 or m1 > (self.sunset - 0.5) * 60:
                    continue
                if not self.wx_ok(m0, m1, wind=9.5, gust=14.0, fog=0.2, vis=8000, rain=0.1):
                    break
                if float(self.day.wx.wind_ms[m0:m1].min()) < 2.8:
                    break                    # no wind to sail with
                if self.is_quiet(m0, m1):
                    continue
                back = self._yacht_back(lane, m0, m1, seed)
                y = dict(lane=lane, back=back, m0=m0, m1=m1, hull=hull, sails=sails, seed=seed)
                mine = lambda m, y=y: [self._yacht_box(y, m)] if self.yacht_pos(y, m) else None
                others = [self.sail_box, self.ship_boxes, self._ferry_boxes,
                          lambda m: [self._yacht_box(o, m) for o in out if self.yacht_pos(o, m)] or None,
                          lambda m: [box_of(0.69, 0.745, 0.075, 0.06, 0.02)] if self.creel_at(m) else None]
                if self.clear_of(mine, m0, m1, others):
                    ok = y
                    break
            if ok:
                out.append(ok)
        return out

    def _yacht_back(self, lane, m0, m1, seed):
        """Which way along its lane a yacht goes: one that is not straight into the wind (no closer than 50
        degrees to it), chosen by its seed when both will do."""
        (x0, y0), (x1, y1) = YACHT_LANES[lane]
        X0, Z0, _ = sea_point(x0, y0)
        X1, Z1, _ = sea_point(x1, y1)
        wx = self.day.wx
        th = np.radians(np.asarray(wx.wind_dir_deg[m0:m1], np.float64))
        # where the wind comes from, in world (x, z): x is west, z south
        fx, fz = -float(np.mean(np.sin(th))), -float(np.mean(np.cos(th)))
        n = math.hypot(fx, fz) or 1.0
        fx, fz = fx / n, fz / n
        dx, dz = heading_of(X1 - X0, Z1 - Z0)
        c = dx * fx + dz * fz                         # cos of the angle between the course and the wind's source
        if c > math.cos(math.radians(50)):
            return True
        if -c > math.cos(math.radians(50)):
            return False
        return bool(seed % 2)

    def yacht_pos(self, y, m):
        """A yacht now: (X, Z, heading, speed units/min), or None."""
        if not y["m0"] <= m < y["m1"]:
            return None
        (x0, y0), (x1, y1) = YACHT_LANES[y["lane"]]
        if y["back"]:
            x0, y0, x1, y1 = x1, y1, x0, y0
        u = (m - y["m0"]) / (y["m1"] - y["m0"])
        u = u + 0.012 * vnoise(y["seed"], m, 23)
        xn, yn = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
        X, Z, _ = sea_point(xn, yn)
        Xb, Zb, _ = sea_point(x1, y1)
        Xa, Za, _ = sea_point(x0, y0)
        h = heading_of(Xb - Xa, Zb - Za)
        return X, Z, h, math.hypot(Xb - Xa, Zb - Za) / (y["m1"] - y["m0"])

    def _yacht_box(self, y, m):
        p = self.yacht_pos(y, m)
        X, Z = p[0], p[1]
        x, yy = to_frame(X, 0, Z)
        D = math.hypot(X, Z)
        k = 1 / math.radians(AZ_SPAN) / D / 15
        kv = VH / math.radians(ALT_TOP) / D / 15
        return box_of(x, yy, 6.5 * k, 15 * kv, 1 * kv)

    def yachts_at(self, m):
        return [(y, self.yacht_pos(y, m)) for y in self.yachts if self.yacht_pos(y, m)]

    # ------------------------------------------------------------- gannets --
    def _gannets(self):
        """Gannets fishing offshore in season (spring to autumn): on some days a bout or two of a few birds
        circling high over the outer bay right of the island and folding into the sea after fish.
        [dict(m0, m1, X, Z, n, seed)]: the bout's patch of sea, in world units."""
        r = np.random.default_rng([self.seed, 93])
        season = bump(self.doy, 80, 110, 280, 310)
        p, nb = r.random(), int(r.choice([1, 1, 2]))
        bouts = [(float(r.random()), float(r.random()), float(r.random()), float(r.random()), int(r.integers(3, 8)),
                  int(r.integers(1 << 30))) for _ in range(2)]
        if p > 0.45 * season:
            return []
        out = []
        for u, v, w, d, n, seed in bouts[:nb]:
            m0 = int((max(self.sunrise + 1.0, 7.0) + (min(self.sunset - 1.5, 18.5) - max(self.sunrise + 1.0, 7.0)) * u) * 60)
            m1 = m0 + int(15 + 22 * d)
            xn, yn = 0.835 + 0.13 * v, 0.6125 + 0.0105 * w
            X, Z, _ = sea_point(xn, yn)
            b = dict(m0=m0, m1=m1, X=X, Z=Z, x=xn, y=yn, n=n, seed=seed)
            if not self.wx_ok(m0, m1, wind=12.0, fog=0.3, vis=5000, rain=0.3) or self.is_quiet(m0, m1):
                continue
            box = lambda m, b=b: [box_of(b["x"], b["y"], 0.05, 0.05, 0.01)] if b["m0"] <= m < b["m1"] else None
            others = [self.sail_box, self.ship_boxes, self._ferry_boxes,
                      lambda m: [self._yacht_box(y, m) for y in self.yachts if self.yacht_pos(y, m)] or None]
            if self.clear_of(box, m0, m1, others) and not any(o["m0"] < m1 + 20 and m0 < o["m1"] + 20 for o in out):
                out.append(b)
        return out

    def gannets_at(self, m):
        return [b for b in self.gannets if b["m0"] <= m < b["m1"]]

    # ------------------------------------------------------------ dolphins --
    def _dolphins(self):
        """A rare pod passing across the bay beyond the skerry: a few days a year, most in summer and autumn,
        never on a day of the bay's rare visitor. dict(m0, m1, back, n, seed) or None."""
        r = np.random.default_rng([self.seed, 94])
        p, u, d, back, n, seed = r.random(), r.random(), r.random(), r.random() < 0.5, int(r.integers(4, 9)), int(r.integers(1 << 30))
        if self.day.mysteries.whale or p > 0.012 + 0.05 * bump(self.doy, 130, 170, 270, 310):
            return None
        m0 = int((8.5 + 8.0 * u) * 60)
        m1 = m0 + int(26 + 16 * d)
        if not (self.sunrise + 0.5) * 60 < m0 and m1 < (self.sunset - 0.3) * 60:
            return None
        if not self.wx_ok(m0, m1, wind=10.0, fog=0.3, vis=4000, rain=0.4):
            return None
        pod = dict(m0=m0, m1=m1, back=back, n=n, seed=seed)
        box = lambda m: [box_of(self.dolphin_x(pod, m), 0.656, 0.05, 0.02, 0.02)] if m0 <= m < m1 else None
        others = [self.sail_box, self._ferry_boxes,
                  lambda m: [box_of(0.69, 0.745, 0.075, 0.06, 0.02)] if self.creel_at(m) else None,
                  lambda m: [self._yacht_box(y, m) for y in self.yachts if self.yacht_pos(y, m)] or None,
                  lambda m: [box_of(b["x"], b["y"], 0.05, 0.05, 0.01) for b in self.gannets if b["m0"] <= m < b["m1"]] or None]
        if not self.clear_of(box, m0, m1, others):
            return None
        return pod

    @staticmethod
    def dolphin_x(pod, m):
        """The pod's middle across the frame (fraction) at minute m: it crosses from one side to the other."""
        u = (m - pod["m0"]) / (pod["m1"] - pod["m0"])
        a, b = 1.04, 0.6
        if pod["back"]:
            a, b = b, a
        return a + (b - a) * u

    def dolphins_at(self, m):
        p = self.dolphins
        return p if p and p["m0"] <= m < p["m1"] else None

    # ------------------------------------------------------------ cormorant --
    def _cormorant(self):
        """The cormorant's visits to the skerry's top knob by day: [(m0, m1, seed)], each cut short when the
        tide covers the knob (cormorant_at)."""
        r = np.random.default_rng([self.seed, 95])
        n = int(r.choice([0, 0, 1, 1, 1, 2, 2, 3]))
        visits = [(float(r.random()), float(r.random()), int(r.integers(1 << 30))) for _ in range(3)]
        out = []
        lo, hi = (self.sunrise + 0.6) * 60, (self.sunset - 0.4) * 60
        for u, d, seed in visits[:n]:
            m0 = int(lo + (hi - lo) * u)
            m1 = int(m0 + 25 + 65 * d)
            if m1 > hi or not self.wx_ok(m0, m1, wind=14.0, rain=0.5) or self.is_quiet(m0, m1):
                continue
            if any(a < m1 + 30 and m0 < b + 30 for a, b, _ in out):
                continue
            out.append((m0, m1, seed))
        return out

    def cormorant_at(self, m, wl):
        """The cormorant's pose now (spread, fold, preen, facing), or None. wl: the water level (world units)."""
        X, Z, h = skerry_point(*CORMORANT_KNOB)
        if h - wl < 0.004:
            return None
        for m0, m1, seed in self.cormorant:
            if m0 <= m < m1:
                k = m - m0
                q = np.random.default_rng([seed, k // 5]).random()
                # just in from fishing it hangs its wings out to dry; later it folds them and preens
                spread = 0.85 - 0.5 * min(1.0, k / (m1 - m0))
                pose = "spread" if q < spread else "preen" if q > 0.88 else "fold"
                f = 1 if np.random.default_rng([seed, 7, k // 13]).random() < 0.5 else -1
                return pose, f
        return None

    # --------------------------------------------------------------- seals --
    def low_water(self, m):
        """The count of the low water this minute belongs to (from high water to high water), and how far from
        it (-0.5 .. 0.5 of the tide's cycle; negative while the tide falls)."""
        mm = min(int(m), 1440)
        f = float(self.day.tide_phase[mm])
        g = f if f < 0.5 else f - 1
        n = int(round((float(self.day.jd[mm]) - JD0) / T_M2 - g))
        return n, g

    def seals_at(self, m, wl):
        """The seals now: [(which, where, pose, facing, a, b)] where is 'rock' (hauled out at its spot) or 'water'
        (a head near its spot, waiting for the rock to dry, or just slipped off it). Seal 0 is the pale cow, who
        comes to her own knob most low waters. wl: the water level (world units)."""
        n, g = self.low_water(m)
        wind = float(self.day.wx.wind_ms[min(int(m), 1439)])
        out = []
        for j, (a, b) in enumerate(SEAL_SPOTS):
            r = np.random.default_rng([n % 2 ** 32, 96, j])
            comes, thr, face, wait = r.random(), r.uniform(0.004, 0.016), r.random() < 0.5, r.uniform(0.002, 0.005)
            if comes > SEAL_P[j] * (1.0 if wind < 11 else 0.4 if wind < 15 else 0.0):
                continue
            _, _, h = skerry_point(a, b)
            margin = h - wl
            f = 1 if face else -1
            if margin > thr:
                q = np.random.default_rng([n % 2 ** 32, 97, j, int(m) // 6]).random()
                pose = "flat" if q < 0.45 else "banana" if q < 0.75 else "head" if q < 0.92 else "scratch"
                out.append((j, "rock", pose, f, a, b))
            elif margin > thr - wait:
                out.append((j, "water", "wait" if g < 0 else "off", f, a, b))
        return out

    def _seal_swims(self):
        """A seal's head up in the water near the skerry now and then (not one that is hauled out): [(m0, m1,
        which, X, Z, seed)]."""
        r = np.random.default_rng([self.seed, 98])
        out = []
        for _ in range(int(r.integers(2, 7))):
            m0 = int(r.uniform(5 * 60, 21 * 60))
            m1 = m0 + int(r.integers(3, 8))
            j = int(r.integers(len(SEAL_SPOTS)))
            ang, dist, seed = r.uniform(0, 2 * math.pi), r.uniform(0.75, 1.6), int(r.integers(1 << 30))
            X0, Z0, _ = sea_point(*SKERRY)
            X, Z = X0 + dist * math.cos(ang), Z0 + 0.55 * dist * math.sin(ang)
            if self.is_quiet(m0, m1) or any(o[0] < m1 + 10 and m0 < o[1] + 10 for o in out):
                continue
            out.append((m0, m1, j, X, Z, seed))
        return out

    def seal_swim_at(self, m, wl):
        """A seal's head in the water now: (which, X, Z, seed, minutes in) or None (not while that seal is out
        on the rock)."""
        for m0, m1, j, X, Z, seed in self.seal_swims:
            if m0 <= m < m1:
                if any(s[0] == j for s in self.seals_at(m, wl)):
                    return None
                return j, X, Z, seed, m - m0
        return None


class NoPlan:
    """The reference mode's plan: nothing on the bay."""
    ferry, creel, yachts, gannets, dolphins, cormorant, seal_swims = [], None, [], [], None, [], []

    def ferry_at(self, m, crossings=None):
        return None

    def creel_at(self, m):
        return None

    def pot_aboard(self, m):
        return None

    def yachts_at(self, m):
        return []

    def gannets_at(self, m):
        return []

    def dolphins_at(self, m):
        return None

    def cormorant_at(self, m, wl):
        return None

    def seals_at(self, m, wl):
        return []

    def seal_swim_at(self, m, wl):
        return None
