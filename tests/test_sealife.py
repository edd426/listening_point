#!/usr/bin/env python3
"""Tests for the bay's boats and animals (renderers/procedural/seaplan.py and sealife.py).

usage: ./venv/bin/python -m unittest tests.test_sealife      (from the repo root; about a minute)

Offline: fair, synthetic or fixed weather and small frames.
"""
import datetime as dt
import math
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "renderers", "procedural"))
sys.path.insert(1, os.path.join(ROOT, "tools"))
import listening_point as lp  # noqa: E402
import seaplan as spm  # noqa: E402
import water as wt  # noqa: E402
from core import VH  # noqa: E402
from day import Day  # noqa: E402

D = dt.date
SCALE = 0.25
YEAR = [D(2027, 1, 1) + dt.timedelta(k) for k in range(0, 365, 4)]


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


class Plan(unittest.TestCase):
    def test_plan_is_decided_by_the_date(self):
        for d in (D(2027, 6, 10), D(2027, 5, 20), D(2027, 8, 15)):
            a, b = Day(d, weather="fair").sea, Day(d, weather="fair").sea
            self.assertEqual(a.ferry, b.ferry)
            self.assertEqual(a.creel, b.creel)
            self.assertEqual(a.yachts, b.yachts)
            self.assertEqual(a.gannets, b.gannets)
            self.assertEqual(a.dolphins, b.dolphins)
            self.assertEqual(a.cormorant, b.cormorant)
            self.assertEqual(a.seal_swims, b.seal_swims)

    def test_reference_mode_has_an_empty_bay(self):
        day = Day(D(2027, 6, 10), weather="clear", reference=True)
        self.assertIsInstance(day.sea, spm.NoPlan)
        for m in range(0, 1440, 7):
            self.assertIsNone(day.sea.ferry_at(m))
            self.assertIsNone(day.sea.creel_at(m))
            self.assertEqual(day.sea.seals_at(m, 0.0), [])


class Ferry(unittest.TestCase):
    def test_timetable_by_season_and_sundays(self):
        n = lambda d, wx="fair": len(Day(d, weather=wx).sea.ferry)
        self.assertEqual(n(D(2027, 7, 7)), 6)          # a summer Wednesday
        self.assertEqual(n(D(2027, 7, 11)), 4)         # a summer Sunday: one round trip fewer
        self.assertEqual(n(D(2027, 1, 13)), 4)         # a winter Wednesday
        self.assertEqual(n(D(2027, 1, 17)), 2)
        # every crossing leaves within half an hour of its time in the table
        day = Day(D(2027, 7, 7), weather="fair")
        table = [t for t in spm.FERRY_TABLES if t[0] <= day.season.doy <= t[1]][0]
        for start, back, late in day.sea.ferry:
            sched = (table[3] if back else table[2])
            self.assertTrue(any(0 <= start - s <= 30 for s in sched), (hhmm(start), back))

    def test_no_crossing_in_a_gale(self):
        day = Day(D(2027, 7, 7), weather="fair")
        day.wx.wind_ms[:] = 19.0
        day.wx.gust_ms[:] = 26.0
        self.assertEqual(spm.SeaPlan(day).ferry, [])

    def test_passes_beyond_the_beacon_keeping_it_to_port(self):
        """At the beacon's column the ferry's waterline is beyond the beacon's foot (higher in the frame, y below
        1125 at native size), and on the way in the beacon lies on its port side."""
        way = spm.ferry_way()
        bx, bz, _ = wt.sea_point(*wt.BEACON)
        xs = [spm.to_frame(*way.at(t)[:1], 0, way.at(t)[1]) for t in np.linspace(0, way.T, 600)]
        xs = np.array(xs)
        k = int(np.argmin(np.abs(xs[:, 0] - wt.BEACON[0])))
        self.assertLess(xs[k, 1] * 1800, 1125)
        X, Z, h, _, _ = way.at(np.linspace(0, way.T, 600)[k])
        port = (-h[1], h[0])
        self.assertGreater((bx - X) * port[0] + (bz - Z) * port[1], 0)
        # and it ends at the island's harbour, on the horizon by the breakwater
        x, y = spm.to_frame(*way.P[-1][:1], 0, way.P[-1][1])
        self.assertAlmostEqual(x, spm.FERRY_HARBOUR[0], places=3)
        self.assertLess(y - VH, 0.003)

    def test_moves_without_jumping(self):
        """From one minute to the next the ferry moves at most about its own length on the frame."""
        way = spm.ferry_way()
        for t in range(int(way.T)):
            a, b = way.at(t), way.at(t + 1)
            if not (a and b):
                continue
            xa, ya = spm.to_frame(a[0], 0, a[1])
            xb, yb = spm.to_frame(b[0], 0, b[1])
            D_ = math.hypot(a[0], a[1])
            length = spm.FERRY_L / 15 / D_ / math.radians(220)       # its length as a fraction of the frame
            self.assertLess(math.hypot(xb - xa, (yb - ya) * 1800 / 2880), 1.3 * length + 0.004, t)


class Creel(unittest.TestCase):
    def test_weekly_rhythm_by_the_weather(self):
        days = [Day(d, weather="fair") for d in YEAR]
        out = [d for d in days if d.sea.creel]
        self.assertGreater(len(out), 8)
        for day in out:
            wd = day.date.weekday()
            self.assertIn(wd, spm.CREEL_DAYS, day.date)
            m0, plan, total = day.sea.creel
            self.assertGreaterEqual(m0, (day.events.sunrise + 0.5) * 60 - 26)
            self.assertLessEqual(m0, 11.5 * 60)
            self.assertLess(m0 + total, 13 * 60)
            if day.season.doy < 60 or day.season.doy > 340:
                self.assertEqual(wd, 5)
        fog = Day(D(2027, 6, 10), weather="fog")
        self.assertIsNone(fog.sea.creel)

    def test_hauls_each_pot_with_its_float_aboard(self):
        day = Day(D(2027, 6, 10), weather="fair")
        m0, plan, total = day.sea.creel
        aboard = [day.sea.pot_aboard(m) for m in range(m0, m0 + total)]
        self.assertEqual(sorted(set(a for a in aboard if a is not None)), [0, 1, 2, 3, 4])
        fr = lp.Frame(day, next(m for m in range(m0, m0 + total) if day.sea.pot_aboard(m) == 2), SCALE)
        marks = [k for k in fr.mark_positions() if k[0] == "pot"]
        self.assertEqual(len(marks), 5)
        drawn = []
        real = lp.Frame.ball

        def spy(self, L, R, x, yw, r, alb, **kw):
            drawn.append((round(x), round(yw)))
            return real(self, L, R, x, yw, r, alb, **kw)
        lp.Frame.ball = spy
        try:
            fr.sea_marks(0.0, 2.0)
        finally:
            lp.Frame.ball = real
        pot2 = marks[2]
        self.assertNotIn((round(pot2[2]), round(pot2[3])), drawn)
        self.assertIn((round(marks[1][2]), round(marks[1][3])), drawn)

    def test_creel_boat_is_drawn_at_the_pots(self):
        day = Day(D(2027, 6, 10), weather="fair")
        fr = lp.Frame(day, 8 * 60 + 25, 0.5)
        X, Z, h, speed, what = fr.creel_pose()
        x, y = fr.proj(X, 0, Z)
        self.assertTrue(0.62 * fr.W < x < 0.76 * fr.W and 0.72 * fr.H < y < 0.78 * fr.H, (x / fr.W, y / fr.H))


class Seals(unittest.TestCase):
    def test_hauled_out_only_where_dry(self):
        for d in (D(2027, 5, 20), D(2027, 1, 19), D(2027, 9, 1)):
            day = Day(d, weather="fair")
            for m in range(0, 1440, 5):
                wl = (float(day.tide[m]) - 0.5) * wt.TR
                for j, where, pose, f, a, b in day.sea.seals_at(m, wl):
                    _, _, h = spm.skerry_point(a, b)
                    if where == "rock":
                        self.assertGreater(h, wl, (d, m, j))
                    self.assertEqual((a, b), spm.SEAL_SPOTS[j])

    def test_the_pale_seal_keeps_her_spot_and_comes_most_low_waters(self):
        lows, with_her = 0, 0
        for d in YEAR[::2]:
            day = Day(d, weather="fair")
            m = int(np.argmin(day.tide[:1440]))
            wl = (float(day.tide[m]) - 0.5) * wt.TR
            lows += 1
            seals = day.sea.seals_at(m, wl)
            with_her += any(s[0] == 0 and s[1] == "rock" for s in seals)
        self.assertGreater(with_her / lows, 0.45)
        self.assertLess(with_her / lows, 0.9)

    def test_a_haul_out_spans_midnight(self):
        """The low water is counted the same on both sides of midnight, so the seals are the same."""
        for d in (D(2027, 3, 3), D(2027, 7, 21), D(2027, 11, 9), D(2028, 2, 2)):
            a, b = Day(d, weather="fair"), Day(d + dt.timedelta(1), weather="fair")
            na, _ = a.sea.low_water(1439)
            nb, _ = b.sea.low_water(0)
            self.assertEqual(na, nb, d)
            wl = (float(a.tide[1439]) - 0.5) * wt.TR
            sa = [(s[0], s[1]) for s in a.sea.seals_at(1439, wl)]
            sb = [(s[0], s[1]) for s in b.sea.seals_at(0, wl)]
            self.assertEqual(sa, sb, d)

    def test_cormorant_only_on_a_dry_knob_by_day(self):
        n = 0
        for d in YEAR[::3]:
            day = Day(d, weather="fair")
            for m in range(0, 1440, 3):
                wl = (float(day.tide[m]) - 0.5) * wt.TR
                c = day.sea.cormorant_at(m, wl)
                if c:
                    n += 1
                    _, _, h = spm.skerry_point(*spm.CORMORANT_KNOB)
                    self.assertGreater(h - wl, 0.0039)
                    self.assertGreater(day.sun_alt[m], 0)
        self.assertGreater(n, 50)


class Rare(unittest.TestCase):
    def test_gannets_in_season_and_dolphins_rarely(self):
        gannet_days, dolphin_days = set(), 0
        for d in YEAR:
            day = Day(d, weather="fair")
            if day.sea.gannets:
                gannet_days.add(d.month)
            if day.sea.dolphins:
                dolphin_days += 1
                self.assertIsNone(day.mysteries.whale)
        self.assertFalse(gannet_days & {1, 2, 12}, gannet_days)
        self.assertTrue(gannet_days & {6, 7, 8})
        self.assertLess(dolphin_days, 12)

    def test_nothing_on_the_bay_while_the_rare_visitor_is_there(self):
        for d in [D(2027, 1, 1) + dt.timedelta(k) for k in range(149, 300)]:
            day = Day(d, weather="fair")
            w = day.mysteries.whale
            if not w:
                continue
            for m in range(w[0] - 5, w[0] + 10):
                self.assertIsNone(day.sea.creel_at(m))
                self.assertEqual(day.sea.yachts_at(m), [])
                self.assertEqual(day.sea.gannets_at(m), [])
                self.assertIsNone(day.sea.dolphins_at(m))


class Clear(unittest.TestCase):
    def test_new_boats_keep_clear_of_the_sailing_boat_and_the_ships(self):
        for d in YEAR[::2]:
            day = Day(d, weather="fair")
            sp = day.sea
            for m in range(0, 1440, 2):
                mine = []
                f = sp._ferry_boxes(m)
                if f:
                    mine += f
                mine += [sp._yacht_box(y, m) for y in sp.yachts if sp.yacht_pos(y, m)]
                if not mine:
                    continue
                theirs = [b for b in [sp.sail_box(m)] + sp.ship_boxes(m) if b]
                for a in mine:
                    for b in theirs:
                        self.assertFalse(spm.boxes_meet(a, b), (d, hhmm(m)))

    def test_restraint(self):
        """Most daylight minutes show none or one of the new things; three at once are rare."""
        import sea_schedule
        hist = [0] * 5
        for d in YEAR[::3]:
            day = Day(d, weather="fair")
            for m in range(0, 1440, 2):
                if day.sun_alt[m] > -4:
                    hist[min(4, len(sea_schedule.shown(day, m)))] += 1
        tot = sum(hist)
        self.assertGreater((hist[0] + hist[1]) / tot, 0.75, hist)
        self.assertLess((hist[3] + hist[4]) / tot, 0.04, hist)


class Drawing(unittest.TestCase):
    def test_drawing_is_deterministic(self):
        for d, t in ((D(2027, 6, 10), "08:25"), (D(2027, 5, 20), "08:15"), (D(2027, 1, 19), "17:24")):
            m = int(t[:2]) * 60 + int(t[3:])
            out = []
            for _ in range(2):
                fr = lp.Frame(Day(d, weather="fair"), m, SCALE)
                img = fr.render((np.zeros((fr.H, fr.W, 3), np.float32), np.zeros((fr.H, fr.W), np.float32), None))
                out.append(np.asarray(img))
            self.assertTrue(np.array_equal(out[0], out[1]), (d, t))

    def test_an_ordinary_minute_is_as_before(self):
        """With nothing new on the bay, bay() draws exactly what it drew before (no extra items)."""
        day = Day(D(2027, 5, 20), weather="fair")
        m = 14 * 60 + 30       # high water, no ferry, no yacht
        fr = lp.Frame(day, m, SCALE)
        self.assertEqual(fr.sea_items(), [])
        self.assertIsNone(fr.ferry_now())
        self.assertEqual(day.sea.seals_at(m, fr.water_level()), [])


if __name__ == "__main__":
    unittest.main()
