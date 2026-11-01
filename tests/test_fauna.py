#!/usr/bin/env python3
"""Tests for the hillside's animals and what hides them (renderers/procedural/fauna.py, events.py).

usage: ./venv/bin/python -m unittest tests.test_fauna      (from the repo root; under a minute)

Offline: fixed weather, small frames.
"""
import datetime as dt
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "renderers", "procedural"))
import listening_point as lp  # noqa: E402
import events  # noqa: E402
import fauna  # noqa: E402
from core import Layer  # noqa: E402
from day import Day  # noqa: E402

SCALE = 0.25
D = dt.date


def days(step=5, year=2027):
    return [D(year, 1, 1) + dt.timedelta(k) for k in range(0, 365, step)]


class Schedule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.days = [Day(d, weather="fair") for d in days(6)]

    def test_fox_is_shy(self):
        """The fox is out mostly around dawn, dusk and at night; rarely in full daylight."""
        day_m = night_m = 0
        for day in self.days:
            ev = day.events
            for m0, track in ev.fox:
                for k in range(len(track)):
                    t = (m0 + k) / 60
                    if ev.sunrise + 2 < t < ev.sunset - 2:
                        day_m += 1
                    else:
                        night_m += 1
        self.assertGreater(night_m, 0)
        self.assertLess(day_m, 0.15 * (day_m + night_m), (day_m, night_m))

    def test_hares_at_dawn_and_dusk_boxing_in_spring(self):
        boxed = []
        for day in self.days:
            ev = day.events
            for h in ev.hares:
                for m in (h["m0"], h["m1"] - 1):
                    t = m / 60
                    self.assertTrue(ev.sunrise - 0.8 < t < ev.sunrise + 1.7 or ev.sunset - 1.6 < t < ev.sunset + 0.8, (day.date, t))
            for b in ev.boxing:
                boxed.append(day.date)
                poses = [p for m in range(b["m0"], b["m1"]) for p in ev.hares_at(m) if p[4] in (b["a"], b["b"])]
                self.assertTrue(poses and all(p[2] == "box" for p in poses), (day.date, poses))
        self.assertTrue(boxed, "no boxing in a year")
        self.assertTrue(all(d.month in (3, 4) for d in boxed), boxed)

    def test_crows_by_day(self):
        n = 0
        for day in self.days:
            ev = day.events
            for v in ev.crow_visits:
                n += 1
                self.assertTrue(ev.sunrise < v["m0"] / 60 and v["m1"] / 60 < ev.sunset, (day.date, v))
        self.assertGreater(n, 10 * len(self.days))

    def test_sheep_keep_to_their_field(self):
        """Each sheep stays on its side of the field walls all day (it never walks through one) and out
        of the walled garden."""
        for day in self.days[::3]:
            ev = day.events
            for m in range(0, 1440, 7):
                for x, y, f, grazing, size, view in ev.sheep(m / 60, lambs=True):
                    side = 1 if y > events.wall_y(x) else -1
                    self.assertGreater(abs(y - events.wall_y(x)), 0.005, (day.date, m, x, y))
                    if side < 0 and events.GARDEN[0][0] < x < events.GARDEN[1][0]:
                        self.assertGreater(y, events.garden_front_y(x), (day.date, m, x, y))
                    self.assertIn(view, ("side", "front", "back"))
            # the base point decides the side once for the day: compare the morning and evening flocks
            a = [1 if y > events.wall_y(x) else -1 for x, y, *_ in ev.sheep(9.0)]
            b = [1 if y > events.wall_y(x) else -1 for x, y, *_ in ev.sheep(23.5)]
            self.assertEqual(sorted(a), sorted(b), day.date)

    def test_reference_mode_has_no_animals(self):
        day = Day(D(2027, 3, 5), weather="fair", reference=True)
        ev = day.events
        self.assertFalse(ev.fox or ev.hares or ev.boxing or ev.crow_visits)


class Occlusion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.day = Day(D(2027, 3, 17), weather="fair")
        fauna.OCC.clear()
        cls.fr = lp.Frame(cls.day, 720, SCALE)
        cls.fallback = list(cls.fr.occluders())         # drawn again on their own
        fauna.OCC.clear()
        cls.C, cls.A = cls.fr.foreground()               # recorded while the hill is drawn
        cls.recorded = list(cls.fr.occluders())

    def group(self, name, groups=None):
        return next(g for g in (groups or self.recorded) if g[0] == name)

    def test_recording_leaves_the_near_scenery_alone(self):
        """The hill drawn while its standing things are recorded is the hill drawn without."""
        key = self.fr.occl_key()
        self.assertIn(key, fauna.OCC)
        C, A = lp.Frame(self.day, 720, SCALE).foreground()     # recorded already: nothing is recorded now
        np.testing.assert_array_equal(C, self.C)
        np.testing.assert_array_equal(A, self.A)

    def test_redrawn_hillside_matches_the_recorded(self):
        names = [g[0] for g in self.recorded]
        self.assertEqual(names, [g[0] for g in self.fallback])
        for g, h in zip(self.recorded, self.fallback):
            if g[0].startswith("wall-"):        # the field walls' stones come from the hill's own draws
                continue
            self.assertEqual(g[1:3], h[1:3], g[0])
            np.testing.assert_array_equal(g[3], h[3], g[0])
            np.testing.assert_array_equal(g[4], h[4], g[0])
        for name in ("wall-upper", "wall-lower", "gate-leaf", "hinge-post", "latch-post", "garden-front", "garden-right", "shed"):
            self.assertIn(name, names)

    def test_behind_the_gate_is_hidden_in_front_is_not(self):
        fr = self.fr
        name, gx0, gy0, mask, foot = self.group("gate-leaf")
        L = Layer(fr, gx0, gy0, gx0 + mask.shape[1], gy0 + mask.shape[0])
        depth = float(foot.min()) - 3
        behind = fr.life_allow(L, depth)
        self.assertIsNotNone(behind)
        solid = mask > 0.95
        self.assertTrue(solid.any())
        self.assertLess(float(behind[solid].max()), 0.05)
        # between the rails what is behind shows, unless something else (the wall, a post) stands nearer
        fr2 = lp.Frame(self.day, 720, SCALE)
        fr2.occluders = lambda: [g for g in self.recorded if g[0] != "gate-leaf"]
        others = fr2.life_allow(L, depth)
        others = np.ones_like(behind) if others is None else others
        gaps = mask < 0.01
        np.testing.assert_allclose(behind[gaps], others[gaps], atol=1e-6)
        self.assertGreater(int((gaps & (others > 0.99)).sum()), 20, "no gaps between the rails")
        front = fr.life_allow(L, float(foot.max()) + 30)
        self.assertTrue(front is None or float(front.min()) > 0.99)

    def test_garden_wall_hides_what_is_inside(self):
        fr = self.fr
        name, gx0, gy0, mask, foot = self.group("garden-front")
        L = Layer(fr, gx0, gy0, gx0 + mask.shape[1], gy0 + mask.shape[0])
        allow = fr.life_allow(L, float(foot.min()) - 4)
        self.assertLess(float(allow[mask > 0.95].max()), 0.05)

    def test_animals_hide_the_ones_behind(self):
        fr = lp.Frame(self.day, 720, SCALE)
        fr.c = np.zeros((fr.H, fr.W, 3), np.float32)
        fr.a = np.zeros((fr.H, fr.W), np.float32)
        fr._life = []
        x, y = 0.6 * fr.W, 0.9 * fr.H          # open grass, clear of the walls
        near = Layer(fr, x - 20, y - 20, x + 20, y)
        near.ellipse(x, y - 10, 15, 9, (255, 0, 0))
        fr.life_put(near, y)
        far = Layer(fr, x - 20, y - 20, x + 20, y)
        allow = fr.life_allow(far, y - 6)
        self.assertIsNotNone(allow)
        self.assertLess(float(allow[10, 20]), 0.05)
        self.assertIsNone(fr.life_allow(far, y + 6), "one standing nearer than the first is not hidden by it")

    def test_crows_stand_on_the_coping(self):
        """A perched crow's feet are on the topmost stone or rail under it: covered just below, open above."""
        fr = self.fr
        for site in ("wall-upper", "wall-lower", "gate-leaf", "garden-front", "garden-front-east", "garden-right"):
            name, gx0, gy0, mask, foot = self.group(site)
            for u in (0.1, 0.5, 0.9):
                at = fr.crow_spot(site, u, 0)
                self.assertIsNotNone(at, (site, u))
                x, feet, depth, M = at
                c = int(x) - gx0
                r = int(feet) - gy0
                col = mask[:, max(0, c - 1):c + 2]
                self.assertGreater(float(col[r:r + 3].max()), 0.5, (site, u, "nothing under its feet"))
                self.assertLess(float(col[:max(0, r - 1)].max(initial=0)), 0.5, (site, u, "stone above its feet"))
                self.assertGreater(depth, float(np.interp(x, np.arange(gx0, gx0 + len(foot)) + 0.5, foot)), (site, "hidden by its perch"))


class Drawing(unittest.TestCase):
    def test_animals_draw_and_are_deterministic(self):
        """Each animal draws something when its schedule has it out, and the same minute draws the same."""
        for date, hhmm, name in ((D(2027, 3, 5), "18:59", "fox"), (D(2027, 3, 17), "17:40", "hares"),
                                 (D(2027, 3, 17), "10:00", "crows"), (D(2027, 3, 17), "12:00", "sheep"),
                                 (D(2027, 3, 5), "06:58", "hares")):
            m = int(hhmm[:2]) * 60 + int(hhmm[3:])
            outs = []
            for _ in range(2):
                fr = lp.Frame(Day(date, weather="fair"), m, SCALE)
                fr.c = np.zeros((fr.H, fr.W, 3), np.float32)
                fr.a = np.zeros((fr.H, fr.W), np.float32)
                fr._life = []
                getattr(fr, name)()
                outs.append((fr.c.copy(), fr.a.copy()))
            self.assertGreater(float(outs[0][1].sum()), 5.0, (date, hhmm, name))
            np.testing.assert_array_equal(outs[0][0], outs[1][0])


if __name__ == "__main__":
    unittest.main()
