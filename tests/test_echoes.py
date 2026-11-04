#!/usr/bin/env python3
"""Tests for the echoes of the shore (v3 phase 5, part 3): the listener's boat answering the shore's history, in
story.py (echoes, pennant_at), shore.py (History) and props.py (the pennant, the washing).

usage: ./venv/bin/python -m unittest tests.test_echoes      (from the repo root; about a minute)

Offline. Every ledger here is synthetic, made at run time in a temporary folder in the kit's layout, against the
kit's own synthetic reference set (shorekit/tests/support.py): no shore data ever sits in this repository.
"""
import datetime as dt
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "renderers", "procedural"), os.path.join(ROOT, "shorekit", "tests"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)
import listening_point as lp  # noqa: E402
import shore as shore_mod  # noqa: E402
import story as S  # noqa: E402
import support as K  # noqa: E402  (the kit's synthetic reference set)
from core import MOORED  # noqa: E402
from day import Day  # noqa: E402
from shorekit.ledger import Shore, ledger_bytes  # noqa: E402
from shorekit.manifest import manifest_from_obj  # noqa: E402

D = dt.date
DAY = dt.timedelta(days=1)
TMP = tempfile.mkdtemp(prefix="echoes-")
SCALE = 0.25
# paints that stand out from the synthetic shingle (rules 2 and 7: the synthetic palette's own albedos); one per object, in turn
PAINTS = ((210, 60, 48), (40, 52, 84), (196, 132, 46), (34, 34, 38), (240, 236, 222), (52, 94, 36))


def tearDownModule():
    shutil.rmtree(TMP, True)


class Ledger:
    """A synthetic shore, built event by event the way the carrier would: adds from two worlds (one maker each,
    one object a day each), vetoes, and storms when the shore is full (Shore.accept). Written as a local cache."""

    def __init__(self):
        self.shore = Shore(K.reference())
        self.x = 1700
        self.n = 0
        self.ids = []

    def add(self, lands, world=0, paint=None, size=4):
        """An object from world 0 or 1 landing at `lands` (UTC, YYYY-MM-DDTHH:MM:SSZ): a block of one paint, put on
        the first free spot of the dry band from the left."""
        ref, day = self.shore.ref, lands[:10]
        rgb = PAINTS[self.n % len(PAINTS)] if paint is None else paint
        for _ in range(2000):
            d = ref.dry(self.x)
            self.x += 3
            if self.x > 2870:
                self.x = 1700
            if not d:
                continue
            obj = K.make_object("%s-e%03d" % (day, self.n), "maker-%d" % world, K.block(size, size), {"a": rgb}, "shingle",
                                self.x, (d[0] + d[1]) >> 1)
            m = manifest_from_obj(obj)
            if not self.shore.judge(m, day)[0]:
                self.shore.accept(m, lands, lands, "world-%d" % world, "0" * 40)
                break
        else:
            raise AssertionError("no spot for %s" % obj["id"])
        self.ids.append(obj["id"])
        self.n += 1
        return obj["id"]

    def veto(self, oid, at):
        self.shore.veto(oid, at)

    def write(self, name):
        path = os.path.join(TMP, name)
        os.makedirs(os.path.join(path, "objects"), exist_ok=True)
        os.makedirs(os.path.join(path, "reference"), exist_ok=True)
        shutil.copytree(K.reference_dir(), os.path.join(path, "reference", "r1"), dirs_exist_ok=True)
        with open(os.path.join(path, "ledger.json"), "wb") as f:
            f.write(ledger_bytes(self.shore.events))
        for oid, m in self.shore.manifests.items():
            with open(os.path.join(path, "objects", oid + ".json"), "wb") as f:
                f.write(m.canonical)
        return path


def utc(date, hhmm, tz="Europe/Budapest"):
    """A local clock time on `date` as the kit writes UTC times."""
    from zoneinfo import ZoneInfo
    t = dt.datetime.combine(date, dt.time(int(hhmm[:2]), int(hhmm[3:])), ZoneInfo(tz))
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def instants(day):
    return [u.timestamp() for u in day.utc]


# a winter week: the boat does not go out on its own (boating season), and fair weather lets it sail and dry washing
W0 = D(2027, 1, 11)


def week_ledger():
    """Objects from both worlds through a winter week, one a day each at the morning pass, with a veto of the newest
    on the 13th at 13:00, a late one on the 14th, and quiet from then on."""
    lg = Ledger()
    for k in range(4):                                  # the 11th to the 14th
        d = W0 + k * DAY
        lg.add(utc(d, "03:30"), 0)
        lg.add(utc(d, "04:28"), 1)
        if k == 2:
            lg.veto(lg.ids[5], utc(d, "13:00"))         # the newest then (the 13th's second)
    lg.add(utc(W0 + 3 * DAY, "11:17"), 2, paint=(196, 156, 70))  # a late one on the 14th, from a third maker
    return lg


class History(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lg = week_ledger()
        cls.cache = cls.lg.write("week")

    def test_history_is_plain_numbers_in_seq_order(self):
        """load_shore hands the story the ledger as numbers: each add's landing, seq, colour and when the sea took
        it; the sea events' times. No ids, names or worlds."""
        day = Day(W0 + 3 * DAY, weather="fair", shore=self.cache)
        h = day.shore.history
        self.assertEqual(len(h.adds), 9)
        self.assertEqual([a[1] for a in h.adds], sorted(a[1] for a in h.adds))
        self.assertEqual(len(h.seas), 1)
        taken = [a for a in h.adds if a[3] is not None]
        self.assertEqual(len(taken), 1)
        self.assertEqual(taken[0][3], h.seas[0])
        for a in h.adds:
            self.assertEqual(len(a), 4)
            for v in (a[0], a[1], a[3]):
                self.assertTrue(v is None or isinstance(v, (int, float)), a)
            self.assertTrue(all(isinstance(c, int) for c in a[2]), a)
        self.assertEqual(h.adds[0][2], PAINTS[0])

    def test_main_colour_leans_to_the_saturated_paint_and_skips_the_label(self):
        ref = K.reference()
        sh = Shore(ref)
        x = 1800
        d = ref.dry(x)
        rows = ["gggggggg", "gggggggg", "ggggrrgg", "gggggggg"]
        obj = K.make_object("2027-01-01-mix", "maker-0", rows, {"g": (120, 118, 112), "r": (200, 40, 30)}, "shingle", x,
                            (d[0] + d[1]) >> 1, label="AB")
        from shorekit.geometry import place
        p = place(manifest_from_obj(obj), ref, None, 1)
        self.assertEqual(shore_mod.main_colour(p), (120, 118, 112))      # 28 grey cells against 4 red: grey still wins
        rows2 = ["gggggggg", "ggrrrrgg", "ggrrrrgg", "gggggggg"]
        obj2 = dict(obj, rows=rows2, id="2027-01-01-mix2")
        p2 = place(manifest_from_obj(obj2), ref, None, 1)
        self.assertEqual(shore_mod.main_colour(p2), (200, 40, 30))       # 8 red against 24 grey: red leads


class Pennant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lg = week_ledger()
        cls.cache = cls.lg.write("week-p")
        cls.days = {d: Day(d, weather="fair", shore=cls.cache) for d in (W0 - DAY, W0, W0 + 2 * DAY, W0 + 3 * DAY,
                                                                           W0 + 6 * DAY, W0 + 7 * DAY)}

    def colour_of(self, oid):
        return tuple(self.lg.shore.manifests[oid].palette["a"])

    def test_up_from_the_first_landing(self):
        self.assertIsNone(self.days[W0 - DAY].story.pennant)
        day = self.days[W0]
        first = next(m for m, t in enumerate(instants(day)) if t >= shore_mod.seconds(utc(W0, "03:30")))
        self.assertIsNone(day.story.pennant_at(first - 1))
        self.assertEqual(day.story.pennant_at(first), self.colour_of(self.lg.ids[0]))
        self.assertEqual(day.story.pennant_at(12 * 60), self.colour_of(self.lg.ids[1]))     # the newest by then

    def test_falls_back_when_the_sea_takes_the_newest(self):
        day = self.days[W0 + 2 * DAY]
        self.assertEqual(day.story.pennant_at(12 * 60), self.colour_of(self.lg.ids[5]))
        self.assertEqual(day.story.pennant_at(13 * 60), self.colour_of(self.lg.ids[4]))     # vetoed at 13:00
        day = self.days[W0 + 3 * DAY]
        self.assertEqual(day.story.pennant_at(11 * 60 + 17), self.colour_of(self.lg.ids[8]))  # the late one

    def test_down_after_three_quiet_days(self):
        last = shore_mod.seconds(utc(W0 + 3 * DAY, "11:17"))
        for d in (W0 + 6 * DAY, W0 + 7 * DAY):
            day = self.days[d]
            for m, t in enumerate(instants(day)):
                if t - last >= S.PENNANT_QUIET:
                    self.assertIsNone(day.story.pennant_at(m), (d, m))
                else:
                    self.assertIsNotNone(day.story.pennant_at(m), (d, m))

    def test_down_when_nothing_is_left(self):
        lg = Ledger()
        a = lg.add(utc(W0, "03:30"), 0)
        lg.veto(a, utc(W0, "09:00"))
        day = Day(W0, weather="fair", shore=lg.write("gone"))
        self.assertEqual(day.story.pennant_at(8 * 60), PAINTS[0])
        self.assertIsNone(day.story.pennant_at(9 * 60))


class Anticipation(unittest.TestCase):
    """What shows at a minute depends only on the ledger's events at or before that minute's moment (an add's lands,
    a sea event's at): tools/nightly.py re-renders only from a new event's moment on."""

    def check(self, lg, name, dates, weather="fair"):
        cache = lg.write(name)
        for d in dates:
            day = Day(d, weather=weather, shore=cache)
            bare = Day(d, weather=weather)                    # the schedule's own trip, and the instants
            hist = day.shore.history
            own = bare.events.trip
            for m, t in enumerate(instants(day)):
                e = S.echoes(bare, hist.upto(t))
                self.assertEqual(day.story.pennant_at(m), e.pennant_at(m), (d, m))
                self.assertEqual(day.story.washing_at(m), e.washing_at(m), (d, m))
                bare.events.trip = own or e.sail
                self.assertEqual(day.events.boat(m / 60), bare.events.boat(m / 60), (d, m))
                bare.events.trip = own

    def test_a_week_and_the_day_after(self):
        lg = week_ledger()
        self.check(lg, "ant-week", (W0 + 2 * DAY, W0 + 3 * DAY))

    def test_a_storm_and_a_veto_on_one_day_and_the_day_after(self):
        lg = Ledger()
        d0 = W0 - 30 * DAY
        for k in range(24):                                   # 48 live by the 24th day
            lg.add(utc(d0 + k * DAY, "03:30"), 0)
            lg.add(utc(d0 + k * DAY, "04:28"), 1)
        day = d0 + 24 * DAY
        lg.add(utc(day, "03:31"), 0)                          # a storm makes room first
        lg.veto(lg.ids[-3], utc(day, "16:42"))
        lg.add(utc(day, "22:05"), 1)
        self.assertGreaterEqual(sum(ev["event"] == "sea" for ev in lg.shore.events), 2)
        self.check(lg, "ant-storm", (day, day + DAY))


class Sail(unittest.TestCase):
    def test_out_the_day_after_the_sea_takes_things(self):
        """A veto, or a storm, on a date sends the boat out the next day on the schedule's own times, in winter (when
        it would not go on its own) and whatever was taken; not the same day."""
        trips = []
        for kind in ("veto", "storm"):
            lg = Ledger()
            d0 = W0 - 24 * DAY
            for k in range(24):
                lg.add(utc(d0 + k * DAY, "03:30"), 0)
                lg.add(utc(d0 + k * DAY, "04:28"), 1)
            if kind == "veto":
                lg.veto(lg.ids[-1], utc(W0, "10:00"))
            else:
                lg.add(utc(W0, "10:00"), 0, size=4)
                self.assertEqual(lg.shore.events[-2]["event"], "sea")
                self.assertGreater(len(lg.shore.events[-2]["takes"]), 1)
            cache = lg.write("sail-" + kind)
            same, nxt, after = (Day(W0 + k * DAY, weather="fair", shore=cache) for k in (0, 1, 2))
            for d in (same, nxt, after):
                self.assertIsNone(Day(d.date, weather="fair").events.trip, d.date)      # none of its own in January
            self.assertIsNone(same.events.trip)
            self.assertIsNotNone(nxt.events.trip)
            self.assertEqual(nxt.events.trip, nxt.events.window)
            self.assertIsNone(after.events.trip)
            trips.append(nxt.events.trip)
            # it is home again half an hour before sunset, so the lamp is as it was
            self.assertLessEqual(nxt.events.trip[1], nxt.events.sunset - 0.5 + 1e-9)
        self.assertEqual(trips[0], trips[1])

    def test_not_in_weather_unfit_to_sail(self):
        lg = Ledger()
        a = lg.add(utc(W0, "03:30"), 0)
        lg.veto(a, utc(W0, "12:00"))
        cache = lg.write("sail-wx")
        for k in (2, 3, 6):
            d = W0 + k * DAY
            day = Day(d, weather="synthetic", shore=cache)
            self.assertIsNone(day.story.sail, d)              # only the day after
        day = Day(W0 + DAY, weather="synthetic", shore=cache)
        bare = Day(W0 + DAY, weather="synthetic")
        ok = bare.events.trip is None and bare.events.fit_to_sail(*bare.events.window)
        self.assertEqual(day.story.sail is not None, ok)


class Washing(unittest.TestCase):
    def test_on_a_quiet_day_only(self):
        lg = week_ledger()
        cache = lg.write("wash")
        hung = []
        for k in range(0, 9):
            d = W0 + k * DAY
            day = Day(d, weather="fair", shore=cache)
            w = day.story.washing
            if w:
                hung.append(d)
                self.assertLessEqual(w[1] / 60, day.events.sunset - 0.5 + 1e-9)
                self.assertIsNone(day.events.trip)
        # the last landed on the 14th at 11:17: quiet from the 16th
        self.assertEqual(hung, [W0 + k * DAY for k in range(5, 9)])

    def test_never_with_an_empty_ledger(self):
        day = Day(W0, weather="fair", shore=Ledger().write("empty-w"))
        self.assertIsNone(day.story.washing)

    def test_taken_in_at_the_rain(self):
        """In synthetic weather: washing never hangs through a rainy minute, and never with the wind over WASH_BLOW."""
        lg = Ledger()
        lg.add(utc(D(2027, 3, 1), "03:30"), 0)
        cache = lg.write("wash-rain")
        seen = 0
        for k in range(3, 120):
            d = D(2027, 3, 1) + k * DAY
            day = Day(d, weather="synthetic", shore=cache)
            w = day.story.washing
            if not w:
                continue
            seen += 1
            wx = day.wx
            sl = slice(w[0], w[1])
            self.assertLessEqual(float(wx.rain[sl].max()), 0.05, d)
            self.assertLessEqual(float(wx.wind_ms[sl].max()), S.WASH_BLOW, d)
        self.assertGreater(seen, 10)


class Off(unittest.TestCase):
    def test_reference_mode_has_no_echoes(self):
        lg = week_ledger()
        cache = lg.write("ref")
        for d in (W0 + 2 * DAY, W0 + 3 * DAY, W0 + 6 * DAY):
            day = Day(d, weather="clear", reference=True, shore=cache)
            self.assertIsInstance(day.story, S.NoStory)
            self.assertNotIsInstance(day.story, S.Story)
            self.assertIsNone(day.events.trip)
            for m in range(0, 1440, 7):
                self.assertIsNone(day.story.pennant_at(m))
                self.assertIsNone(day.story.washing_at(m))

    def test_no_shore_and_an_empty_ledger_have_no_echoes(self):
        empty = Ledger().write("empty")
        for d in (W0, W0 + 5 * DAY, D(2027, 7, 3)):
            a, b = Day(d, weather="fair"), Day(d, weather="fair", shore=empty)
            for day in (a, b):
                self.assertIsNone(day.story.pennant)
                self.assertIsNone(day.story.washing)
                self.assertIsNone(day.story.sail)
            self.assertEqual(a.events.trip, b.events.trip)
            for m in (0, 600, 900):
                fa = lp.Frame(a, m, SCALE).render(lp.Frame(a, m, SCALE).foreground() + (None,))
                fb = lp.Frame(b, m, SCALE).render(lp.Frame(b, m, SCALE).foreground() + (None,))
                self.assertTrue(np.array_equal(np.asarray(fa), np.asarray(fb)), (d, m))


class Drawing(unittest.TestCase):
    def frames(self, day, m):
        """The frame at minute m, and the same with the story's echoes taken away."""
        fg = lp.Frame(day, m, SCALE).foreground() + (None,)
        a = np.asarray(lp.Frame(day, m, SCALE).render(fg), np.int16)
        keep = (day.story.pennant, day.story.washing)
        day.story.pennant = day.story.washing = None
        try:
            b = np.asarray(lp.Frame(day, m, SCALE).render(fg), np.int16)
        finally:
            day.story.pennant, day.story.washing = keep
        return a, b

    def test_pennant_and_washing_only_on_the_boat(self):
        """The echoes change only pixels on and just about the moored boat, and none of a shore object's."""
        lg = week_ledger()
        cache = lg.write("draw")
        day = Day(W0 + 5 * DAY, weather="fair", shore=cache)       # quiet: washing, and the pennant still up at noon
        m = 12 * 60
        self.assertIsNotNone(day.story.pennant_at(m))
        self.assertIsNotNone(day.story.washing_at(m))
        a, b = self.frames(day, m)
        diff = np.abs(a - b).max(-1) > 0
        self.assertTrue(diff.any())
        ys, xs = np.nonzero(diff)
        W, H = a.shape[1], a.shape[0]
        size = 170 * W / 3840
        cx, cy = MOORED[0] * W, MOORED[1] * H
        self.assertGreaterEqual(xs.min(), cx - 0.8 * size)
        self.assertLessEqual(xs.max(), cx + 0.8 * size)
        self.assertGreaterEqual(ys.min(), cy - 1.35 * size)
        self.assertLessEqual(ys.max(), cy + 0.3 * size)
        st = day.shore.at(m)
        k = W / day.shore.frame[0]
        ox, oy = (st["sx"] * k).astype(int), (st["sy"] * k).astype(int)
        self.assertFalse(diff[oy, ox].any())

    def test_the_pennant_flies_downwind(self):
        """In a wind from the east the pennant streams to the right of the mast, from the west to the left."""
        lg = Ledger()
        lg.add(utc(W0, "03:30"), 0, paint=(210, 60, 48))
        day = Day(W0, weather="fair", shore=lg.write("wind"))
        m = 12 * 60
        W = int(round(3840 * SCALE))
        top = MOORED[0] * W - 0.05 * 170 * SCALE        # the mast (the boat faces left)
        sides = []
        for frm in (90.0, 270.0):
            day.wx.wind_dir_deg[m] = frm
            day.wx.wind_ms[m] = 7.0
            a, b = self.frames(day, m)
            ys, xs = np.nonzero(np.abs(a - b).max(-1) > 0)
            sides.append(float(xs.mean()) - top)
        self.assertGreater(sides[0], 1.0)
        self.assertLess(sides[1], -1.0)


if __name__ == "__main__":
    unittest.main()
