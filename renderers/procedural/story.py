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

Part 3, the echoes: the listener, who lives aboard the boat moored at the end of the pier and is never seen,
answers what reaches the shore (its ledger, shore.py's History): a pennant at the masthead in the colours of the
newest thing still on the shore, a trip out on the bay the day after the sea takes things, and washing hung out
on a quiet day. They read only the ledger's events at or before the moment they show (tools/nightly.py re-renders
from each new event's moment on), and nothing at all without a shore cache or with an empty ledger.

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
LOG_KEEP, LOG_BURN = 7, 3     # they all stay this many days, then one goes on the fire every LOG_BURN days
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
SURGE = (0.02, 0.05)             # how far above the high waters it is left (fractions of the beach)
DRIFT_TOP = 0.515                # never higher than this: the dry band above is the shore kit's (shore.py)
DRIFT_WASH = 0.015               # the sea takes it when its edge comes this close
DRIFT_FIRE = (2, 6)              # or it is taken for the fire on this many'th workable day (seeded)
DRIFT_BACK = 21
# Snow drifts: the snow that fell in the current spell of lying snow, pushed by the wind above SNOW_PUSH
SNOW_PUSH, SNOW_BACK = 3.0, 21

# ----------------------------------------------------------- animal lives --
# (part 2) The lives are told from the spring of LIVES_FROM: before it the flock is phase 3's four ewes and the cat
# has no kittens. The pale seal's year needs no start: each year's is its own.
LIVES_FROM = 2027
# The flock: four blackface ewes, each keeping her place in the schedule's draws (her slot, events.Schedule.sheep).
EWES = 4
LAMBING, LAMBING_LATE, LAMBING_SPAN = (3, 25), 21, 18   # the first lambs come 25 March + 0..21 days (the year's
                                                        # tupping), and every ewe has lambed within 18 days of them
TUP_AGE = 2                    # a ewe lambs first the spring she is two (a kept ewe lamb is a hogg her first year)
BARREN_P, TWIN_P, MAX_LAMBS = 0.1, 0.2, 3               # a small flock: three lambs at most
SALE, SALE_LATE, SALE_GRACE = (8, 25), 24, 21  # weaned and sold: the first day fit for work (or with no weather on
                                               # record) from 25 August + 0..24 days, at the latest 21 days on
KEEP_P = 0.8                   # a ewe lamb is kept back that year (if there is one), and the oldest ewe goes with the lambs
ADULT = 540                    # days old: a kept ewe lamb is a grown ewe from then
# The cat's kittens: in some years a litter, born indoors; they come out from four weeks old and go to new homes
# at ten to twelve weeks, each on its own day. Once, one of a litter stays and grows into a second cat.
LITTER_P, LITTER, LITTER_LATE, LITTER_N = 0.5, (4, 1), 69, (2, 4)    # born 1 April + 0..69 days, 2-4 of them
KIT_OUT, KIT_HOME, KIT_GROWN = 28, (70, 84), 300   # days old: out, gone to a new home, grown
KIT_STAY_P = 0.4
KIT_WET = (8.0, 3.0)           # kept in: this much rain the day before, or this much on each of the two days before
COATS = (("black", 0.2), ("bicolour", 0.3), ("grey", 0.15), ("tabby", 0.2), ("ginger", 0.15))
# The pale cow (seaplan's seal 0) goes to a breeding colony in most autumns: west Scotland's grey seals pup from
# September to late November; she nurses her pup about 18 days, fasting, mates and leaves it, and comes back thin.
SEAL_GO_P = 0.85
SEAL_LEAVE, SEAL_LEAVE_LATE, SEAL_AWAY = (9, 15), 30, (30, 46)   # she leaves 15 September + 0..30 days, for 30-46 days
SEAL_SURE, SEAL_LEAN = 3, 35   # back, she comes to every low water for 3 days, and is thin for 35

# ----------------------------------------------------------------- echoes --
# (part 3) The listener's boat answers the shore's history. The pennant flies the colour of the newest object still
# on the shore, and comes down once nothing new has landed for PENNANT_QUIET seconds.
PENNANT_QUIET = 3 * 86400
# Washing hangs on a line from the mast to the stern on a quiet day (nothing new landed since the start of the day
# before), hung at WASH_HANG and taken in at WASH_IN (hours, seeded), or at the first rain or a blow; only on a dry
# day (WASH_DRY: no rain for its first hour), not cold (WASH_TEMP C), with the wind under WASH_WIND m/s, moored all day.
WASH_HANG, WASH_IN, WASH_DRY = (9.0, 10.5), (14.5, 16.0), 60
WASH_TEMP, WASH_WIND, WASH_BLOW = 3.0, 10.0, 12.0


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


# ------------------------------------------------------------------ lives --
def lamb_size(age):
    """A lamb's (or a hogg's) size against a grown ewe's, by its age in days: about half at birth, filling out."""
    return 1.0 - 0.52 * math.exp(-age / 130.0)


def kit_size(age):
    """A kitten's size against the cat's, by its age in days: 0.45 at four weeks, 0.7 at twelve, grown at KIT_GROWN."""
    if age <= KIT_HOME[1]:
        return 0.45 + 0.25 * min(1.0, max(0.0, (age - KIT_OUT) / (KIT_HOME[1] - KIT_OUT)))
    return 0.7 + 0.3 * min(1.0, (age - KIT_HOME[1]) / (KIT_GROWN - KIT_HOME[1]))


@functools.lru_cache(maxsize=16)
def flock_years(last):
    """The flock's years from LIVES_FROM to `last`: {year: the ewes as they stand at lambing ((id, birth date or None
    for phase 3's grown ewes, birth year)), the lambs born, the date the sale is due, the kept ewe lamb's id and the
    slot she takes}. Decided by the years alone; the weather moves only the day of the sale."""
    r0 = rng(9, 0)
    years = [int(LIVES_FROM - TUP_AGE - r0.integers(0, 4)) for _ in range(EWES)]    # phase 3's ewes: 2 to 5 years old
    ids, born = [f"ewe{k}" for k in range(EWES)], [None] * EWES
    out = {}
    for Y in range(LIVES_FROM, last + 1):
        r = rng(10, Y)
        start = dt.date(Y, *LAMBING) + int(r.integers(0, LAMBING_LATE + 1)) * DAY
        draws = [(r.random(), r.random(), int(r.integers(0, LAMBING_SPAN + 1)), r.random(2), r.integers(1 << 30, size=2),
                  r.random()) for _ in range(EWES)]
        due = dt.date(Y, *SALE) + int(r.integers(0, SALE_LATE + 1)) * DAY
        keep, pick = r.random() < KEEP_P, r.random()
        lambs = []
        for k, (barren, twin, off, sex, seeds, side) in enumerate(draws):
            if years[k] > Y - TUP_AGE or barren < BARREN_P:
                continue
            n = min(2 if twin < TWIN_P else 1, MAX_LAMBS - len(lambs))
            s0 = 1 if side < 0.5 else -1
            for j in range(n):
                lambs.append(dict(id=f"{Y}-{k}{'ab'[j]}", mother=k, born=start + off * DAY, ewe=bool(sex[j] < 0.5),
                                  seed=int(seeds[j]), side=s0 if j == 0 else -s0, twin=n == 2))
        st = dict(ewes=tuple(zip(ids, born, years)), lambs=tuple(lambs), due=due, kept=None, place=None)
        ewe_lambs = [lb for lb in lambs if lb["ewe"]]
        if keep and ewe_lambs:
            kept = ewe_lambs[int(pick * len(ewe_lambs))]
            place = min(range(EWES), key=lambda k: (years[k], k))       # the oldest ewe goes to the sale with the lambs
            st.update(kept=kept["id"], place=place)
            ids[place], born[place], years[place] = kept["id"], kept["born"], Y
        out[Y] = st
    return out


@functools.lru_cache(maxsize=16)
def litters(last):
    """The cat's years from LIVES_FROM to `last`: {year: (the litter: (kittens, each with its birth date, coat, the
    age it goes to a new home, whether it stays), or None; the kitten of an earlier litter that stayed, or None)}."""
    out, stayed = {}, None
    for Y in range(LIVES_FROM, last + 1):
        r = rng(13, Y)
        go = r.random() < LITTER_P
        born = dt.date(Y, *LITTER) + int(r.integers(0, LITTER_LATE + 1)) * DAY
        n = int(r.integers(LITTER_N[0], LITTER_N[1] + 1))
        kits = []
        for j in range(LITTER_N[1]):
            coat = COATS[int(r.choice(len(COATS), p=[p for _, p in COATS]))][0]
            kits.append(dict(id=f"{Y}-k{j}", born=born, coat=coat, home=int(r.integers(KIT_HOME[0], KIT_HOME[1] + 1)),
                             seed=int(r.integers(1 << 30)), stays=False))
        stays, pick = r.random() < KIT_STAY_P, r.random()
        litter = None
        if go:
            kits = kits[:n]
            if stays and stayed is None:
                # one that does not look like her, if the litter has one, so the two can be told apart
                pool = [k for k in kits if k["coat"] != "black"] or kits
                pool[int(pick * len(pool))]["stays"] = True
            litter = tuple(kits)
        out[Y] = (litter, stayed)
        if litter and stayed is None:
            stayed = next((k for k in litter if k["stays"]), None)
    return out


def seal_year(Y):
    """The pale cow's autumn of year Y: (the day she is gone from, the day she is back), or None if she stays."""
    r = rng(17, Y)
    go = r.random() < SEAL_GO_P
    left = dt.date(Y, *SEAL_LEAVE) + int(r.integers(0, SEAL_LEAVE_LATE + 1)) * DAY
    back = left + int(r.integers(SEAL_AWAY[0], SEAL_AWAY[1] + 1)) * DAY
    return (left, back) if go else None


# ------------------------------------------------------------------ story --
class EchoView:
    """Reading the echoes (part 3) at a clock minute, from `pennant` and `washing` (see Story)."""
    pennant = washing = sail = None

    def pennant_at(self, m):
        """The pennant's colour (an albedo) at clock minute m, or None when none flies."""
        c = None
        for m0, col in self.pennant or ():
            if m0 > m:
                break
            c = col
        return c

    def washing_at(self, m):
        """The washing's seed while it hangs at clock minute m, else None."""
        w = self.washing
        return w[2] if w and w[0] <= m < w[1] else None


class Echo(EchoView):
    """The echoes on one date (echoes())."""

    def __init__(self, pennant=None, sail=None, washing=None):
        self.pennant, self.sail, self.washing = pennant, sail, washing


class NoStory(EchoView):
    """Reference mode: nothing has happened."""
    garden = None
    walls = {}
    wall = branch = scar = drift = spade = None
    logs = 0
    driftwood = ()
    # the animal lives (part 2): no lambs, the ewes phase 3's, no kittens, the pale seal as phase 4 has her
    lambs = kittens = ()
    ewes = pale = pale_before = sold = None
    kittens_in = False
    # the echoes (part 3): no pennant, no washing, no trip sent by the shore (EchoView)
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

    The animal lives (part 2):
    - lambs: this spring's lambs while they are on the hill, each with its mother's slot, its age and size, the side
      of her it keeps to and a seed for its look (the same every day); sold: the day they went, once gone;
    - ewes: per slot, None for a grown ewe or the record of a kept ewe lamb not yet grown (a hogg: smaller); None
      when all four are grown;
    - kittens: the cat's kittens that are out (four weeks old and not yet gone to new homes), and the one that stayed,
      each with its age, size, coat and seed; kittens_in: a wet spell keeps the young ones indoors today;
    - pale: the pale seal while she is away, or for a while after she is back (her knob, seaplan.seals_at); else None;
      pale_before: the same for the day before (a low water that began before midnight keeps that day's state).

    The echoes (part 3), from the shore's history (day.shore.history), all None without one:
    - pennant: ((from minute, colour or None), ...) through the day: what flies at the masthead (pennant_at);
    - sail: (dep, ret) when the sea took things yesterday and the boat goes out today (Story.apply sets the trip);
    - washing: (from minute, to minute, seed) while washing hangs on the moored boat (washing_at).
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
        self._flock(D)
        self._kittens(D)
        self._seal(D)
        self._echoes(day)
        self.lookback = len(self.hist.memo)
        del self.hist                    # not needed by the workers
        self.cost_ms = (time.perf_counter() - t0) * 1000

    def apply(self, day):
        """Hang the stages on the Day, where the hillside (phase 3's interface) draws them from."""
        day.garden_stage = self.garden
        day.wall_stages = dict(self.walls)
        if self.sail:                   # the echoes: out on the bay the day after the sea took things
            day.events.trip = self.sail

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
        mid, half = float(lo + (hi - lo) * u[2]), float(GAP_HALF[0] + (GAP_HALF[1] - GAP_HALF[0]) * u[3])
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
                # the storm's water stood above the high waters of that day and the two after it
                base = 0.5 * max(float(tide(d + i * DAY).max()) for i in range(3)) + r.uniform(*SURGE)
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

    # ------------------------------------------------------------ lambs --
    def _flock(self, D):
        Y = D.year
        if Y < LIVES_FROM:
            return
        st = flock_years(Y)[Y]
        self.sold = self._sale(st["due"], D)
        ewes = list(st["ewes"])
        if self.sold and st["kept"]:
            kept = next(lb for lb in st["lambs"] if lb["id"] == st["kept"])
            ewes[st["place"]] = (kept["id"], kept["born"], Y)
        hoggs = tuple(None if b is None or (D - b).days >= ADULT else
                      dict(id=i, slot=k, age=(D - b).days, size=lamb_size((D - b).days)) for k, (i, b, _) in enumerate(ewes))
        self.ewes = hoggs if any(hoggs) else None
        if not self.sold:
            self.lambs = tuple(dict(lb, age=(D - lb["born"]).days, size=lamb_size((D - lb["born"]).days),
                                    kept=lb["id"] == st["kept"])
                               for lb in st["lambs"] if lb["born"] <= D)

    def _sale(self, due, D):
        """The day the lambs were taken to the sale, if it was before D: the first day from `due` fit for work
        outside (gathering the hill), or with no weather on record, and SALE_GRACE days on whatever the weather."""
        h, d = self.hist, due
        while d < D:
            if h.workable(d) or not h(d).known or d >= due + SALE_GRACE * DAY:
                return d
            d += DAY
        return None

    # ---------------------------------------------------------- kittens --
    def _kittens(self, D):
        Y = D.year
        if Y < LIVES_FROM:
            return
        litter, stayed = litters(Y)[Y]
        out = []
        if stayed:
            out.append(stayed)
        for k in litter or ():
            age = (D - k["born"]).days
            if age >= KIT_OUT and (k["stays"] or age < k["home"]):
                out.append(k)
        self.kittens = tuple(dict(k, age=(D - k["born"]).days, size=kit_size((D - k["born"]).days)) for k in out)
        if any(k["age"] < KIT_HOME[1] for k in self.kittens):      # (the one that stayed goes out in any weather)
            h = self.hist
            p1, p2 = h(D - DAY), h(D - 2 * DAY)
            self.kittens_in = bool(p1.known and (p1.rain >= KIT_WET[0] or (p2.known and min(p1.rain, p2.rain) >= KIT_WET[1])))

    # ------------------------------------------------------------- seal --
    def _seal(self, D):
        self.pale, self.pale_before = pale_state(D), pale_state(D - DAY)

    # ----------------------------------------------------------- echoes --
    def _echoes(self, day):
        hist = getattr(getattr(day, "shore", None), "history", None)
        if hist is None or not hist.adds:
            return
        e = echoes(day, hist)
        self.pennant, self.sail, self.washing = e.pennant, e.sail, e.washing


def pennant_at(hist, t):
    """The pennant's colour at UTC second t (an albedo), or None: the colour of the newest object on the shore then
    (landed, and not yet taken by the sea), unless nothing new has landed for PENNANT_QUIET. Reads only the events at
    or before t."""
    newest, best = None, None
    for lands, seq, colour, gone in hist.adds:
        if lands > t:
            continue
        newest = lands if newest is None else max(newest, lands)
        if gone is not None and gone <= t:
            continue
        if best is None or (lands, seq) > best[:2]:
            best = (lands, seq, colour)
    if best is None or t - newest >= PENNANT_QUIET:
        return None
    return tuple(best[2])


def echoes(day, hist):
    """The echoes on day's date from the shore's history (shore.History), as an Echo. Reads the schedule's own trip
    (day.events.trip before Story.apply).

    - pennant: ((from minute, colour or None), ...), evaluated at each minute an add lands, the sea takes something or
      an arrival turns PENNANT_QUIET old; None if nothing flies all day;
    - sail: the schedule's own sailing times, when the sea took things on the date before (local), the schedule has no
      trip of its own, and its own test finds the day fit to sail; else None. It is the same whatever the sea took and
      whenever it did;
    - washing: (hung, taken in, seed) in clock minutes, on a quiet day (see WASH_*), else None."""
    ts = np.array([u.timestamp() for u in day.utc])
    marks = sorted({x for lands, _, _, gone in hist.adds for x in (lands, lands + PENNANT_QUIET, gone) if x is not None})
    starts = sorted({0} | {int(i) for i in np.searchsorted(ts, marks, side="left") if 0 < i <= 1440})
    pennant = []
    for m in starts:
        c = pennant_at(hist, float(ts[m]))
        if not pennant or pennant[-1][1] != c:
            pennant.append((m, c))
    pennant = tuple(pennant) if any(c for _, c in pennant) else None

    D, ev = day.date, day.events
    t0 = float(ts[0])
    t_1 = dt.datetime.combine(D - DAY, dt.time(0, 0), ZoneInfo(day.tzname)).timestamp()
    sail = None
    if ev.trip is None and any(t_1 <= at < t0 for at in hist.seas) and ev.fit_to_sail(*ev.window):
        sail = tuple(ev.window)

    washing = None
    r = rng(18, D.toordinal())
    hang, take = r.uniform(*WASH_HANG), r.uniform(*WASH_IN)
    m0, m1 = int(hang * 60), int(min(take, ev.sunset - 0.5) * 60)
    th = float(ts[m0])
    landed = [lands for lands, _, _, _ in hist.adds if lands <= th]
    quiet = bool(landed) and max(landed) < t_1
    if quiet and ev.trip is None and sail is None and m1 - m0 > 2 * WASH_DRY:
        wx = day.wx

        def wet(a, b):
            return bool(wx.rain[a:b].max() > 0.05 or wx.drizzle[a:b].max() > 0.15 or wx.snow[a:b].max() > 0.05
                        or wx.thunder[a:b].max() > 0)
        if not wet(m0, m0 + WASH_DRY) and wx.wind_ms[m0:m0 + WASH_DRY].max() < WASH_WIND and wx.temp_c[m0] >= WASH_TEMP:
            for m in range(m0 + WASH_DRY, m1):      # taken in at the first rain, or a blow
                if wet(m, m + 1) or wx.wind_ms[m] > WASH_BLOW:
                    m1 = m
                    break
            washing = (m0, m1, D.toordinal())
    return Echo(pennant, sail, washing)


def pale_state(D):
    """The pale cow on date D: away (at the breeding colony), or lately back (sure: she comes to every low water;
    lean: how thin she still is, 1 the day she is back), or None (as phase 4 has her)."""
    trip = seal_year(D.year)
    if trip is None:
        return None
    left, back = trip
    if left <= D < back:
        return dict(away=True, left=left, back=back, since=None, sure=False, lean=0.0)
    if back <= D < back + SEAL_LEAN * DAY:
        since = (D - back).days
        return dict(away=False, left=left, back=back, since=since, sure=since < SEAL_SURE, lean=1.0 - since / SEAL_LEAN)
    return None
