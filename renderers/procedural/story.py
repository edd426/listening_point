"""The story over weeks (v3 phase 5, part 1): what the days before a date have left on the land.

Work on the land is done offstage, by no one you ever see: a length of wall that a winter gale or a thaw
brought down is rebuilt course by course in early spring, and the garden is dug, planted and cleared as
phase 3 drew its year, but only on days fit for work. The weather leaves marks: a branch blown down from
the tree lies under it until it is cleared and cut into logs by the shed, driftwood thrown up by an
onshore gale lies on the shingle until a higher tide takes it back or it is taken for the fire, and lying
snow drifts against the lee of the walls.

Everything is decided by the date and by the weather of that day and the days before it, as the
mysteries are, so a given day always renders the same. Changes land overnight: the state is per date,
from the days before it. The weather of earlier days comes from the same source as the day's own:
synthetic and fair weather from their own generators (so previews repeat), real weather only from the
forecasts already in the weather cache, never from the network. A day the cache does not cover is a day
on which nothing happened: no storm and no work.

Every random choice here has its own generator, seeded [STORY + strand, ...], disjoint from every other
generator in the renderer, so no existing draw moves. In reference mode there is no story (NoStory).
"""
import datetime as dt
import functools
import json
import math
import os
import re
from typing import NamedTuple
from zoneinfo import ZoneInfo

import numpy as np

import astro
import weather as wxmod
from hillside import DIG_ORDER, GardenStage, WallStage, garden_stage
from season import ramp

DAY = dt.timedelta(days=1)
STORY = 5500          # the story's seeds are [STORY + strand, ...]

# ------------------------------------------------------------- thresholds --
# A day fit for work outside: none of these (m/s, mm, m, deg C).
WORK_GUST = 15.0      # a gale
WORK_WIND = 11.0
WORK_RAIN = 3.0       # rain-soaked: this much rain in the day ...
SOAK_RAIN = 12.0      # ... or this much the day before
WORK_SNOW = 0.01      # snowbound: this much snow lying
WORK_TMAX = 2.0       # frozen: the day never got above this
# The tree loses a branch in a gale: gusts of GALE give a chance of one, GALE_SURE always do.
GALE, GALE_SURE, BRANCH_P = 20.0, 24.0, 0.5
BRANCH_CLEAR = (2, 4)   # it is cleared on this many'th workable day after it fell (seeded)
BRANCH_BACK = 75        # days looked back for branches and their logs
LOGS = (4, 7)           # logs a cleared branch adds to the pile by the shed
LOG_KEEP, LOG_BURN = 10, 4    # they all stay this many days, then one goes on the fire every LOG_BURN days
# A winter wall: weak in some winters, it comes down in the first gale of WALL_GALE, or the first thaw (a day
# above THAW within three days of a hard frost), between mid November and the end of February.
WALL_P, WALL_GALE, HARD_FROST, THAW = 0.7, 18.0, -6.0, 3.0
# where it is weak: (stretch, range of the gap's middle along it), and half the fallen length (frame widths)
SITES = (("garden-front", 0.30, 0.66), ("wall-upper", 0.42, 0.80), ("wall-lower", 0.30, 0.66))
GAP_HALF = (0.010, 0.014)
# Rebuilding, in workable days from March: the gap is stripped to its footings and the stones sorted into
# a pile (1), the second and third courses are laid (5 each), the coping (4), and the leftover stones go (1).
STRIP, ROW, COPE, TIDY = 1, 5, 4, 1
WALL_DONE = STRIP + 2 * ROW + COPE           # the wall is whole after this many workable days
# The garden's work (phase 3's ramps), stepping only on workable days. A field keeps up with phase 3's
# calendar when at least WORK_RATE of its days are workable, and never runs ahead of it. Unlike the wall,
# the garden already has a year of its own, so a day with no weather on record does not hold it back.
GARDEN_WORK = (("dug", 0, 40), ("sown", 36, 116), ("cleared", 176, 262), ("rough", 236, 286))
WORK_RATE, GARDEN_GRACE = 0.55, 45
# Driftwood: thrown up by an onshore blow, onto the shingle a little above that day's high water.
ONSHORE_FROM = 210.0  # where the open sea lies from the beach (deg): a wind from there blows straight in
ONSHORE, DRIFT_P = 8.0, 0.85     # m/s of wind blowing in from the sea
SURGE = (0.03, 0.06)             # how far above the day's high water it is left (fractions of the beach)
DRIFT_TOP = 0.515                # never higher than this: the dry band above is the shore kit's (shore.py)
DRIFT_WASH = 0.015               # the sea takes it when its edge comes this close
DRIFT_FIRE = (2, 6)              # or it is taken for the fire on this many'th workable day (seeded)
DRIFT_BACK = 21
# Snow drifts: the snow that fell in the current spell of lying snow, pushed by the wind above SNOW_PUSH
SNOW_PUSH, SNOW_BACK = 3.0, 21


# ---------------------------------------------------------------- weather --
class DaySum(NamedTuple):
    """One day's weather as the story needs it (from the hours of that local day)."""
    known: bool
    gust: float = 0.0       # the strongest gust, m/s
    gust_dir: float = 0.0   # where the wind came from then, deg
    wind: float = 0.0       # the strongest mean wind, m/s
    onshore: float = 0.0    # the strongest wind blowing in from the sea, m/s
    rain: float = 0.0       # rain and showers, mm
    snow: float = 0.0       # snowfall, cm
    snow_e: float = 0.0     # where the falling snow was blown: snowfall x (wind - SNOW_PUSH) along the
    snow_n: float = 0.0     #   downwind direction (east, north), cm m/s
    depth: float = 0.0      # the most snow lying, m
    tmin: float = 0.0
    tmax: float = 0.0


UNKNOWN = DaySum(False)
CALM = DaySum(True, 4.0, 250.0, 3.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 6.0, 14.0)   # fair and fixed weather
BLOCK = 32            # synthetic weather is made a block of days at a time, each block on its own


def summarise(th, hv, t0):
    """The DaySum of the local day starting at UTC second t0, from hourly values (Open-Meteo names): the
    hours ending in it, as Open-Meteo's sums are over the hour before their time."""
    k = (th > t0 + 1) & (th <= t0 + 86401)
    if k.sum() < 20:
        return UNKNOWN
    g, ws, wd = hv["wind_gusts_10m"][k], hv["wind_speed_10m"][k], np.radians(hv["wind_direction_10m"][k])
    j = int(np.argmax(g))
    sf = hv["snowfall"][k]
    push = sf * np.maximum(ws - SNOW_PUSH, 0.0)
    temp = hv["temperature_2m"][k]
    return DaySum(True, float(g[j]), float(np.degrees(wd[j]) % 360), float(ws.max()),
                  float(max(0.0, (ws * np.cos(wd - math.radians(ONSHORE_FROM))).max())),
                  float((hv["rain"][k] + hv["showers"][k]).sum()), float(sf.sum()),
                  float((push * -np.sin(wd)).sum()), float((push * -np.cos(wd)).sum()),
                  float(hv["snow_depth"][k].max()), float(temp.min()), float(temp.max()))


@functools.lru_cache(maxsize=48)
def synthetic_block(b, tz, lat, lon):
    """The DaySums of synthetic weather for the days of block b (ordinals BLOCK*b .. BLOCK*b + BLOCK-1),
    made in one go from a month before the block, so lying snow is spun up. The same whichever date asks."""
    last = dt.date.fromordinal(BLOCK * b + BLOCK - 1)
    th, hv = wxmod._synthetic_hourly(last, tz, lat, lon, back=BLOCK + 15)
    return {dt.date.fromordinal(BLOCK * b + i): summarise(th, hv, wxmod._midnight(dt.date.fromordinal(BLOCK * b + i), tz))
            for i in range(BLOCK)}


@functools.lru_cache(maxsize=32)
def cached_hours(path):
    """A cached Open-Meteo response as hourly arrays, or None if it cannot be read."""
    try:
        with open(path) as f:
            return wxmod._hourly(json.load(f))
    except Exception:
        return None


CACHE_RE = re.compile(r"open-meteo-(\d{4}-\d\d-\d\d)-(\d{4}-\d\d-\d\d)-(\d{8}T\d{6}Z)\.json$")


def cache_index(cache_dir, cutoff):
    """{date: [paths, newest fetch first]} of the cached forecasts fetched before `cutoff` (a UTC stamp,
    YYYYmmddTHHMMSSZ), by the dates each was asked to cover."""
    try:
        names = os.listdir(cache_dir)
    except (OSError, TypeError):
        return {}
    idx = {}
    for n in names:
        m = CACHE_RE.match(n)
        if not m or m[3] >= cutoff:
            continue
        a, b = dt.date.fromisoformat(m[1]), dt.date.fromisoformat(m[2])
        d = a
        while d <= b:
            idx.setdefault(d, []).append((m[3], n))
            d += DAY
    return {d: [os.path.join(cache_dir, n) for _, n in sorted(v, reverse=True)] for d, v in idx.items()}


class History:
    """The weather of the days before a date, a DaySum per day, from the same source as the day's own."""

    def __init__(self, mode, cache_dir, tz, lat, lon, before):
        self.mode, self.tz, self.lat, self.lon = mode, tz, lat, lon
        self.memo = {}
        self.index = None
        if mode not in ("synthetic", "fair") and mode not in wxmod.FIXED:
            # real weather: the cache only, as it stood when the date began
            cut = dt.datetime.combine(before, dt.time(), ZoneInfo(tz)).astimezone(dt.timezone.utc)
            self.index = cache_index(cache_dir, cut.strftime("%Y%m%dT%H%M%SZ"))

    def __call__(self, d):
        s = self.memo.get(d)
        if s is None:
            if self.mode == "synthetic":
                s = synthetic_block(d.toordinal() // BLOCK, self.tz, self.lat, self.lon)[d]
            elif self.index is None:
                s = CALM
            else:
                s = UNKNOWN
                for path in self.index.get(d, ()):
                    hours = cached_hours(path)
                    if hours is not None:
                        s = summarise(*hours, wxmod._midnight(d, self.tz))
                        if s.known:
                            break
            self.memo[d] = s
        return s

    def workable(self, d):
        """A day fit for work outside: known, and not a gale, rain-soaked, snowbound or frozen."""
        s = self(d)
        if not s.known:
            return False
        p = self(d - DAY)
        soaked = s.rain >= WORK_RAIN or (p.known and p.rain >= SOAK_RAIN)
        return (s.gust < WORK_GUST and s.wind < WORK_WIND and not soaked and s.depth < WORK_SNOW
                and s.tmax >= WORK_TMAX)

    def count(self, a, b, unknown=False):
        """The workable days from a up to (not including) b, and the last of them (or None). With `unknown`,
        a day with no weather on record counts as workable too."""
        n, last, d = 0, None, a
        while d < b:
            if self.workable(d) or (unknown and not self(d).known):
                n, last = n + 1, d
            d += DAY
        return n, last


@functools.lru_cache(maxsize=64)
def tide_samples(date, tz, lat, lon):
    """The tide every ten minutes of a local day (145 samples, 00:00 to 24:00), by day.py's own formula."""
    z = ZoneInfo(tz)
    mid = dt.datetime.combine(date, dt.time(0, 0), z)
    ts = np.array([(mid + dt.timedelta(minutes=10 * i)).timestamp() for i in range(145)])
    jd = astro.jd_from_unix(ts)
    ra, dec, dist = astro.moon_radec(jd)
    ra, dec = astro.topocentric(ra, dec, dist, jd, lat, lon)
    ha = np.radians((astro.lst_hours(jd, lon) - ra) * 15)
    spring = 0.72 + 0.28 * np.cos(2 * np.radians(np.asarray(astro.moon_illumination(jd)["elongation_deg"], np.float64)))
    return 0.5 + 0.5 * spring * np.cos(2 * (ha - np.radians(45)))


def rng(strand, *key):
    return np.random.default_rng([STORY + strand] + [int(k) for k in key])


# ------------------------------------------------------------------ story --
class NoStory:
    """Reference mode: nothing has happened."""
    garden = None
    walls = {}
    wall = branch = scar = drift = spade = None
    logs = 0
    driftwood = ()
    cost_ms = 0.0

    def apply(self, day):
        pass


class Story(NoStory):
    """What the days before `day` have left on the land. Plain data, cheap to hand to the render workers:

    - garden: the GardenStage (phase 3's year, stepping with the work); spade: (bed, how far dug) while
      a bed is being dug, where the spade is left standing;
    - walls: {stretch: WallStage} with the fallen length (`gap`) while it is down or being rebuilt; wall: the
      marks round it (where, how far the work has gone, the stones in the grass or in a pile, the line);
    - branch: the branch lying under the tree, or None; scar: days since the tree last lost one; logs: how
      many logs are stacked by the shed;
    - driftwood: the pieces lying on the shingle, each with the minute today the sea takes it (or None);
    - drift: where the snow of the current spell was blown (east, north, cm m/s), for drifts by the walls.
    """

    def __init__(self, day, weather="auto", cache_dir=None):
        import time
        t0 = time.perf_counter()
        D = day.date
        self.date = D
        self.hist = History(weather, cache_dir, day.tzname, day.lat, day.lon, D)
        self.walls = {}
        self._garden(D)
        self._wall(D)
        self._branch(D)
        self._driftwood(day, D)
        self._drift(D)
        self.lookback = len(self.hist.memo)
        del self.hist                    # not needed by the workers
        self.cost_ms = (time.perf_counter() - t0) * 1000

    def apply(self, day):
        """Hang the stages on the Day, where the hillside (phase 3's interface) draws them from."""
        day.garden_stage = self.garden
        day.wall_stages = dict(self.walls)

    # ----------------------------------------------------------- garden --
    def _garden(self, D):
        doy = D.timetuple().tm_yday
        base = garden_stage(doy)
        c = (doy - 50) % 365
        h = self.hist
        work = {}
        for name, c0, c1 in GARDEN_WORK:
            if c <= c0 or c >= c1 + GARDEN_GRACE:
                work[name] = getattr(base, name)
                continue
            # (a day with no weather on record holds nothing up: the garden keeps to its calendar)
            n, last = h.count(D - (c - c0) * DAY, D, unknown=True)
            if last is None:
                work[name] = 0.0
                continue
            # as far as the calendar had got on the last day of work, and no further than the work done
            work[name] = min(ramp(c - (D - last).days + 1, c0, c1), n / (WORK_RATE * (c1 - c0)))
        self.garden = GardenStage(dug=work["dug"], sown=work["sown"], growth=base.growth, ripe=base.ripe,
                                  cleared=work["cleared"], rough=work["rough"])
        dug = self.garden.dug
        if 0.0 < dug < 1.0:              # the spade stands where digging stopped, in the bed being dug
            k = DIG_ORDER.index(min(3, int(dug * 4)))
            self.spade = (k, float(np.clip(dug * 4 - DIG_ORDER[k], 0.0, 1.0)))

    # ------------------------------------------------------------- wall --
    def _wall(self, D):
        if (D.month, D.day) >= (11, 15):
            Y = D.year
        elif D.month <= 6:
            Y = D.year - 1
        else:
            return
        u = rng(1, Y).random(4)
        if u[0] >= WALL_P:
            return
        site, lo, hi = SITES[int(u[1] * len(SITES))]
        mid, half = lo + (hi - lo) * u[2], GAP_HALF[0] + (GAP_HALF[1] - GAP_HALF[0]) * u[3]
        h = self.hist
        d, end, fell = dt.date(Y, 11, 15), dt.date(Y + 1, 3, 1), None
        while d < D and d < end:
            s = h(d)
            if s.known and (s.gust >= WALL_GALE or (s.tmax >= THAW and any(
                    h(d - i * DAY).known and h(d - i * DAY).tmin <= HARD_FROST for i in (0, 1, 2, 3)))):
                fell = d
                break
            d += DAY
        if fell is None:
            return
        start = max(dt.date(Y + 1, 3, 1), fell + 5 * DAY)
        work, _ = h.count(start, D) if D > start else (0, None)
        if work >= WALL_DONE + TIDY:
            return
        if work == 0:
            gap = (mid, half, "fallen", 0.0)
        else:
            built = 1.0 + min(1.0, (work - STRIP) / ROW) + min(1.0, max(0.0, (work - STRIP - ROW) / ROW)) \
                + min(1.0, max(0.0, (work - STRIP - 2 * ROW) / COPE))
            gap = (mid, half, "built", float(min(4.0, built)))
        self.walls[site] = WallStage(4.0, gap=gap)
        self.wall = dict(site=site, mid=mid, half=half, seed=Y, fell=fell, work=work, state=gap[2], built=gap[3],
                         line=0 < work < WALL_DONE,
                         # stones lying where they fell (before the work), then in a pile by the gap: what is left
                         pile=0.0 if work == 0 else (0.12 if work >= WALL_DONE else 1.0 - 0.88 * (gap[3] - 1.0) / 3.0))

    # ----------------------------------------------------------- branch --
    def _branch(self, D):
        h = self.hist
        down, batches, last_fall = None, [], None
        d = D - BRANCH_BACK * DAY
        while d < D:
            s = h(d)
            if down is not None:
                if h.workable(d):
                    down["work"] += 1
                    if down["work"] >= down["need"]:
                        r = rng(6, down["fell"].toordinal())
                        batches.append((d, int(r.integers(LOGS[0], LOGS[1] + 1))))
                        down = None
            elif s.known and s.gust >= GALE and (s.gust >= GALE_SURE or rng(3, d.toordinal()).random() < BRANCH_P):
                r = rng(7, d.toordinal())
                down = dict(fell=d, work=0, need=int(r.integers(BRANCH_CLEAR[0], BRANCH_CLEAR[1] + 1)),
                            wind_from=s.gust_dir, gust=s.gust)
                last_fall = d
            d += DAY
        if down is not None:
            self.branch = dict(fell=down["fell"], age=(D - down["fell"]).days, wind_from=down["wind_from"],
                               seed=down["fell"].toordinal(), doy=down["fell"].timetuple().tm_yday)
        if last_fall is not None:
            self.scar = (D - last_fall).days
        logs = 0
        for when, n in batches:
            age = (D - when).days - 1
            logs += max(0, n - max(0, age - LOG_KEEP) // LOG_BURN)
        self.logs = logs

    # -------------------------------------------------------- driftwood --
    def _driftwood(self, day, D):
        h = self.hist
        here, d = None, D - DRIFT_BACK * DAY
        tide = lambda x: tide_samples(x, day.tzname, day.lat, day.lon)
        while d < D:
            s = h(d)
            if here is not None:
                if 0.5 * float(tide(d).max()) >= here["low"] - DRIFT_WASH:
                    here = None                       # a higher tide has taken it back
                elif h.workable(d):
                    here["work"] += 1
                    if here["work"] >= here["need"]:
                        here = None                   # taken for the fire
            elif s.known and s.onshore >= ONSHORE and rng(5, d.toordinal()).random() < DRIFT_P:
                r = rng(8, d.toordinal())
                base = 0.5 * float(tide(d).max()) + r.uniform(*SURGE)
                n = 1 + int(r.random() < 0.5) + int(r.random() < 0.2)
                pieces = []
                for i in range(n):
                    pieces.append(dict(v=float(min(DRIFT_TOP, base + r.uniform(-0.004, 0.006))), slot=int(r.integers(0, 1 << 30)),
                                       seed=d.toordinal() * 4 + i))
                here = dict(arrived=d, work=0, need=int(r.integers(DRIFT_FIRE[0], DRIFT_FIRE[1] + 1)), pieces=pieces,
                            low=min(p["v"] for p in pieces))
            d += DAY
        if here is None:
            return
        # the sea takes them all together today if it reaches the lowest: from that ten minutes on
        hit = np.nonzero(0.5 * tide(D) >= here["low"] - DRIFT_WASH)[0]
        gone = int(hit[0]) * 10 if len(hit) else None
        self.driftwood = tuple(dict(p, gone=gone, arrived=here["arrived"]) for p in here["pieces"])

    # ------------------------------------------------------------ drifts --
    def _drift(self, D):
        h = self.hist
        e = n = 0.0
        d = D - DAY
        for _ in range(SNOW_BACK):
            s = h(d)
            if not s.known or (s.depth < 0.005 and s.snow < 0.05):
                break
            e, n = e + s.snow_e, n + s.snow_n
            d -= DAY
        self.drift = (e, n)
