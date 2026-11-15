#!/usr/bin/env python3
"""The cloud layers' lens and the cirrus streaks' bearing (sky.cloud_plane, sky.streak_bearing).

usage: ./venv/bin/python -m unittest tests.test_clouds      (from the repo root; a second)
"""
import math
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "renderers", "procedural"))
import sky  # noqa: E402
from core import ALT_TOP, AZ_SPAN, VH  # noqa: E402

W, H = 2880, 1800
ASPECT = W / 2 / (VH * H)


def screen(alt, az):
    """Pixels right of the frame's middle and above the horizon."""
    return (az - 180.0) / AZ_SPAN * W, alt / ALT_TOP * VH * H


def plane(x, y):
    X, Z = sky.cloud_plane(np.array([y / (VH * H) * ALT_TOP]), np.array([180.0 + x / W * AZ_SPAN]), ASPECT)
    return float(X[0]), float(Z[0])


class Lens(unittest.TestCase):
    def test_straight_on_screen_is_straight_on_the_layer(self):
        rng = np.random.default_rng(3)
        for _ in range(200):
            (x0, y0), (x1, y1) = rng.uniform([-1400, 30], [1400, 1040], (2, 2))
            pts = [plane(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t) for t in (0.0, 0.37, 1.0)]
            (ax, az), (bx, bz), (cx, cz) = pts
            cross = (bx - ax) * (cz - az) - (bz - az) * (cx - ax)
            self.assertLess(abs(cross), 1e-3 * (1 + math.hypot(cx - ax, cz - az) * math.hypot(bx - ax, bz - az)))

    def test_rows_across_the_view_are_level(self):
        for y in (60, 300, 700, 1040):
            zs = [plane(x, y)[1] for x in (-1400, -500, 0, 800, 1400)]
            self.assertLess(max(zs) - min(zs), 1e-4 * zs[0])

    def cloudlet(self, x, y):
        """Width over height, on screen, of a small round patch of the layer seen at (x, y)."""
        X0, Z0 = plane(x, y)
        (Xx, Zx), (Xy, Zy) = plane(x + 1, y), plane(x, y + 1)
        J = np.array([[Xx - X0, Xy - X0], [Zx - Z0, Zy - Z0]])      # layer units per pixel right, per pixel up
        Ji = np.linalg.inv(J)                                       # pixels per layer unit east, south
        return float(np.hypot(*Ji[0]) / np.hypot(*Ji[1]))

    def test_round_at_the_top_and_flatter_toward_the_horizon(self):
        self.assertAlmostEqual(self.cloudlet(0, VH * H - 1), 1.0, delta=0.03)
        self.assertAlmostEqual(self.cloudlet(0, VH * H / 2), 2.0, delta=0.05)
        self.assertGreater(self.cloudlet(0, VH * H / 8), 7.0)
        self.assertAlmostEqual(self.cloudlet(900, VH * H - 1), self.cloudlet(-900, VH * H - 1), delta=0.03)

    def test_east_is_left_and_south_is_ahead(self):
        X, Z = plane(-800, 500)
        self.assertGreater(X, 0)        # the view faces south: the left of the frame is east
        self.assertGreater(Z, 0)
        self.assertLess(plane(800, 500)[0], 0)
        self.assertGreater(plane(0, 100)[1], plane(0, 900)[1], "lower in the frame is farther away")

    def test_directions_outside_the_frame_are_finite(self):
        X, Z = sky.cloud_plane(np.array([0.0, -3.0, 66.0, 20.0]), np.array([40.0, 320.0, 180.0, 0.0]), ASPECT)
        self.assertTrue(np.isfinite(X).all() and np.isfinite(Z).all())


class Streaks(unittest.TestCase):
    def off_axis(self, wind):
        """Degrees between the streaks' axis and the view's (0 = pointing at the viewer)."""
        b = (sky.streak_bearing(wind) - 180.0 + 90.0) % 180.0 - 90.0
        return abs(b)

    def test_never_at_a_point_inside_the_frame_but_for_a_wind_along_the_view(self):
        edge = math.degrees(math.atan(math.tan(math.radians(sky.LENS_TOP)) * ASPECT))    # the frame's edge, in the lens
        self.assertGreater(sky.STREAK_MIN, edge)
        for wind in np.arange(0, 360, 0.25):
            along = min(abs((wind + 90.0) % 180.0 - 90.0), 90.0)
            if along >= sky.STREAK_SWING:
                self.assertGreaterEqual(self.off_axis(wind), sky.STREAK_MIN - 1e-6, wind)

    def test_along_the_wind_when_it_blows_across(self):
        for wind in (270.0, 90.0, 250.0, 115.0, 300.0, 61.0):
            d = (sky.streak_bearing(wind) - wind + 90.0) % 180.0 - 90.0
            self.assertAlmostEqual(d, 0.0, places=6, msg=wind)

    def test_it_never_jumps(self):
        prev = None
        for wind in np.arange(0, 720, 0.05):
            b = sky.streak_bearing(wind % 360.0)
            if prev is not None:
                d = abs((b - prev + 90.0) % 180.0 - 90.0)       # as axes: 0 and 180 are the same streak
                self.assertLess(d, 1.0, wind)
            prev = b

    def test_the_slant_follows_the_side_the_wind_comes_from(self):
        self.assertGreater(sky.streak_bearing(200.0), 180.0)
        self.assertLess(sky.streak_bearing(160.0), 180.0)


if __name__ == "__main__":
    unittest.main()
