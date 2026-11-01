#!/usr/bin/env python3
"""Tests for the hillside's built things and land detail (renderers/procedural/hillside.py).

usage: ./venv/bin/python -m unittest tests.test_hillside      (from the repo root; about half a minute)

Offline: fixed weather, small frames, the hillside drawn into fresh layers of its own.
"""
import datetime as dt
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "renderers", "procedural"))
import listening_point as lp  # noqa: E402
import hillside as hs  # noqa: E402
from core import Layer  # noqa: E402
from day import Day  # noqa: E402

SCALE = 0.25


def draw(day, m=720):
    """The hillside drawn alone for minute m of day: the albedo, normal and mask layers as arrays, and
    what casts shadows."""
    fr = lp.Frame(day, m, SCALE)
    y0 = int(0.58 * fr.H)
    xw = int(np.ceil(0.46 * fr.W))
    A, N, X, WM = (Layer(fr, 0, y0, xw, fr.H) for _ in range(4))
    persp = lambda y: 0.35 + 1.3 * np.clip((np.asarray(y) / fr.H - 0.6) / 0.4, 0, 1)
    casters, feet = fr.hillside(A, N, X, WM, persp)
    return [np.asarray(L.img) for L in (A, N, X, WM)], casters, feet


class GardenYear(unittest.TestCase):
    def test_stage_wraps_at_the_end_of_february(self):
        """The garden's year ends where it begins: the last day of one is the first of the next."""
        end, start = hs.garden_stage(49), hs.garden_stage(50)
        for f in ("dug", "sown", "growth", "ripe", "cleared", "rough"):
            self.assertAlmostEqual(getattr(end, f), 1.0, places=6)
            self.assertAlmostEqual(getattr(start, f), 0.0, places=6)

    def test_nothing_done_looks_like_a_year_over(self):
        """A garden with nothing done (all 0) is drawn exactly as one whose year is over (all 1), so the
        turn of the garden's year shows no jump."""
        day = Day(dt.date(2027, 2, 19), weather="clear")
        day.garden_stage = hs.GardenStage(1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
        a, _, _ = draw(day)
        day.garden_stage = hs.GardenStage()
        b, _, _ = draw(day)
        for x, y in zip(a, b):
            np.testing.assert_array_equal(x, y)

    def test_seasons_differ(self):
        """Spring, summer and winter gardens are not the same picture."""
        imgs = []
        for d in (dt.date(2027, 4, 8), dt.date(2027, 7, 5), dt.date(2027, 1, 10)):
            imgs.append(draw(Day(d, weather="clear"))[0][0])
        self.assertFalse(np.array_equal(imgs[0], imgs[1]))
        self.assertFalse(np.array_equal(imgs[1], imgs[2]))

    def test_stages_keep_their_plants_in_place(self):
        """Moving the stage on shows more of the garden without moving what was already there: the
        cabbage bed's old kale, left of where digging has reached, is the same at 40% and 60% dug."""
        day = Day(dt.date(2027, 3, 10), weather="clear")
        day.garden_stage = hs.GardenStage(dug=0.85)
        a, _, _ = draw(day)
        day.garden_stage = hs.GardenStage(dug=0.90)
        b, _, _ = draw(day)
        fr = lp.Frame(day, 720, SCALE)
        # the right-hand end of the cabbage bed (undug at both stages), in the layers' own pixels
        x0, y0 = fr.hs_g(0.75, hs.BEDS[0][1])
        x1, y1 = fr.hs_g(0.94, hs.BEDS[0][0])
        ss, top = 2, int(0.58 * fr.H)
        box = (slice(int((y0 - 12 - top) * ss), int((y1 + 2 - top) * ss)), slice(int(x0 * ss), int(x1 * ss)))
        np.testing.assert_array_equal(a[0][box], b[0][box])


class Walls(unittest.TestCase):
    def test_wall_rises_by_stage(self):
        """A wall stretch draws nothing at 0 courses, more stone at each stage, and the finished wall at 4."""
        day = Day(dt.date(2027, 6, 1), weather="clear")
        cover = []
        for c in (0.0, 1.0, 2.5, 4.0):
            day.wall_stages = {w: hs.WallStage(c) for w in hs.WALLS}
            (A, N, X, WM), casters, feet = draw(day)
            cover.append(int((WM[..., 0] > 0).sum()))
        self.assertTrue(cover[0] < cover[1] < cover[2] < cover[3], cover)
        day.wall_stages = None
        full = int((draw(day)[0][3][..., 0] > 0).sum())
        self.assertEqual(full, cover[3])


class Layout(unittest.TestCase):
    def test_clear_of_the_shore(self):
        """Nothing the hillside draws, nor any shadow it casts, reaches the shore kit's crop (frame x >= 1600
        of 2880), whatever the season or the weather."""
        for d, wx in ((dt.date(2027, 4, 6), "synthetic"), (dt.date(2027, 8, 25), "clear"), (dt.date(2027, 1, 27), "synthetic")):
            day = Day(d, weather=wx)
            for m in (480, 720, 960):
                (A, N, X, WM), casters, feet = draw(day, m)
                xs = np.nonzero((A[..., 3] > 0).any(0) | (X[..., 3] > 0).any(0))[0]
                limit = 1600 / 2880 * lp.Frame(day, m, SCALE).W * 2      # in the layers' supersampled pixels
                self.assertLess(xs.max(), limit * 0.85)
                fr = lp.Frame(day, m, SCALE)
                for c in casters:
                    pts = c[1] if c[0] in ("poly", "box") else [c[1], c[2]]
                    self.assertLess(max(p[0] for p in pts), 0.5 * fr.W)

    def test_deterministic(self):
        day = Day(dt.date(2026, 11, 1), weather="fair")
        a, ca, fa = draw(day)
        b, cb, fb = draw(day)
        for x, y in zip(a, b):
            np.testing.assert_array_equal(x, y)
        self.assertEqual(ca, cb)
        self.assertEqual(fa, fb)


if __name__ == "__main__":
    unittest.main()
