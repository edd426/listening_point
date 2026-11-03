#!/usr/bin/env python3
"""Tests for the water (renderers/procedural/water.py): the light on the sea and the marks in the bay.

usage: ./venv/bin/python -m unittest tests.test_water      (from the repo root; under a minute)

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
import listening_point as lp  # noqa: E402
import water as wt  # noqa: E402
from core import VH, hill_edge_y  # noqa: E402
from day import Day  # noqa: E402

SCALE = 0.25
D = dt.date


def frame(date, hhmm, weather="synthetic", scale=SCALE, reference=False):
    m = int(hhmm[:2]) * 60 + int(hhmm[3:])
    return lp.Frame(Day(date, weather=weather, reference=reference), m, scale)


class Places(unittest.TestCase):
    def test_marks_are_on_open_water(self):
        """Every mark stands on the sea: below the horizon and above the shore's low-water line."""
        for xn, yn in [wt.BEACON, wt.SKERRY] + list(wt.POTS) + [(b[0], b[1]) for b in wt.BUOYS]:
            self.assertGreater(yn, VH + 0.02, (xn, yn))
            self.assertLess(yn, float(hill_edge_y(xn)) - 0.03, (xn, yn))

    def test_sea_point_inverts_the_projection(self):
        fr = frame(D(2027, 3, 21), "12:00", "clear")
        for xn, yn in [wt.BEACON, wt.SKERRY, wt.POTS[2]]:
            X, Z, dist = wt.sea_point(xn, yn)
            x, y = fr.proj(X, 0, Z)
            self.assertAlmostEqual(float(x) / fr.W, xn, places=6)
            self.assertAlmostEqual(float(y) / fr.H, yn, places=6)
            self.assertAlmostEqual(math.hypot(X, Z), dist, places=9)

    def test_marks_keep_clear_of_the_sailing_route(self):
        """The skerry, the floats and the buoys lie off the sailing boat's round trip."""
        from events import ROUTE, catmull
        pts = np.array([catmull(ROUTE, u)[0] for u in np.linspace(0, 1, 600)])
        for xn, yn in [wt.SKERRY] + list(wt.POTS) + [(b[0], b[1]) for b in wt.BUOYS]:
            d = np.hypot(pts[:, 0] - xn, pts[:, 1] - yn).min()
            self.assertGreater(d, 0.025, (xn, yn))


class Tide(unittest.TestCase):
    def test_skerry_covers_and_uncovers(self):
        """At low water much of the skerry stands out of the sea; at a spring high water none of it does,
        and at a neap high water only the top of its highest knob is awash."""
        h, _ = wt.skerry_field()
        level = lambda tide: (tide - 0.5) * wt.TR
        low, high = (h > level(0.1)).mean(), (h > level(1.0)).mean()
        self.assertGreater(low, 0.25)
        self.assertEqual(high, 0.0)
        self.assertLess((h > level(0.72)).mean(), 0.02)
        self.assertGreater((h > level(0.5)).mean(), 0.0)

    def test_water_climbs_the_beacon(self):
        """At high water the waterline stands higher on the beacon's post; its light stays where it is.
        The floats swing round their moorings with the stream and the wind."""
        day = Day(D(2027, 1, 20), weather="fair")
        lo, hi = int(np.argmin(day.tide[:1440])), int(np.argmax(day.tide[:1440]))
        a, b = lp.Frame(day, lo, 0.75), lp.Frame(day, hi, 0.75)
        self.assertEqual(a.beacon_light()[:2], b.beacon_light()[:2])
        self.assertGreater(a.beacon_light()[2] - b.beacon_light()[2], 3.0)     # px
        flow = int(np.argmax(np.abs(np.diff(day.tide[:1440]))))
        c = lp.Frame(day, flow, 0.75)
        xa = [m[2] for m in a.mark_positions()]
        xc = [m[2] for m in c.mark_positions()]
        self.assertGreater(max(abs(p - q) for p, q in zip(xa, xc)), 1.0)

    def test_stream_turns_with_the_tide(self):
        day = Day(D(2027, 1, 20), weather="fair")
        t = day.tide
        rising = int(np.argmax(np.diff(t[:1440])))
        falling = int(np.argmin(np.diff(t[:1440])))
        self.assertGreater(lp.Frame(day, rising, SCALE).tide_flow(), 0.5)
        self.assertLess(lp.Frame(day, falling, SCALE).tide_flow(), -0.5)


class Light(unittest.TestCase):
    def test_cloud_shadows_follow_the_cloud(self):
        """Broken cloud casts patches on the sea; a clear sky casts none; the shadow at the foot of the
        frame is the light the land gets."""
        fr = frame(D(2027, 1, 19), "12:00")
        fr.sky()
        T = fr.sea_shadow("sun")
        self.assertIsNotNone(T)
        self.assertGreater(float(np.percentile(T, 95) - np.percentile(T, 5)), 0.2)
        foot = float(T[-1].mean())
        self.assertAlmostEqual(foot, fr.sun_vis, delta=0.2)
        clear = frame(D(2027, 3, 21), "12:00", "clear")
        clear.sky()
        self.assertIsNone(clear.sea_shadow("sun"))

    def test_shadows_drift_with_the_wind(self):
        """A minute later the shadows have moved on about as much as the clouds in the sky have, no more."""
        a, b = frame(D(2027, 1, 19), "12:00"), frame(D(2027, 1, 19), "12:01")
        a.sky()
        b.sky()
        Ta, Tb = a.sea_shadow("sun"), b.sea_shadow("sun")
        dT = float(np.abs(Ta - Tb).mean())
        dsky = float(np.abs(a.cloud_occ - b.cloud_occ).mean())
        self.assertGreater(dT, 0.0)
        self.assertLess(dT, 2.0 * dsky + 0.05, (dT, dsky))

    def test_wind_patterns_by_wind(self):
        """Glassy water and cat's paws in light airs (a wide spread of roughness); lanes in a breeze."""
        calm = frame(D(2026, 11, 13), "08:00")
        breeze = frame(D(2026, 11, 22), "12:00")
        self.assertLess(calm.wx.wind_ms, 2.0)
        self.assertGreater(breeze.wx.wind_ms, 5.0)
        rows = np.arange(calm.hz, calm.H, dtype=np.float32) + 0.5
        lc, _ = calm.sea_wind(rows)
        lb, _ = breeze.sea_wind(rows)
        near = slice(int(0.06 * calm.H), None)
        self.assertLess(float(np.percentile(lc[near], 20)), 0.6)        # glassy
        self.assertGreater(float(np.percentile(lc[near], 95)), 1.1)     # cat's paws
        self.assertGreater(float(np.percentile(lb[near], 20)), 0.65)    # rippled all over

    def test_glitter_narrows_in_a_calm(self):
        """The sun's path is narrower on a calm sea than in a blow, with the same sun."""
        fr = frame(D(2027, 1, 20), "12:00")
        rows = np.arange(fr.hz, fr.H, dtype=np.float32) + 0.5
        ad = (rows - VH * fr.H) / (VH * fr.H) * 70.0
        rp = np.zeros((len(rows), fr.W), np.float32)
        lr = np.ones_like(rp)
        widths = []
        for v in (0.5, 12.0):
            fr.wx.wind_ms = v
            g = fr.glitter(10.0, fr.W / 2, (255, 255, 255), 1.0, 1.0, ad, rp, lr, None)[..., 0]
            row = g[len(rows) // 4]
            widths.append(int((row > 0.5 * row.max()).sum()))
        self.assertLess(widths[0], 0.7 * widths[1], widths)

    def test_whitecaps_only_in_a_blow(self):
        for date, hhmm, want in ((D(2027, 1, 20), "12:00", True), (D(2026, 11, 22), "12:00", False)):
            fr = frame(date, hhmm)
            fr.c[:] = 0
            fr.whitecaps()
            self.assertEqual(bool(fr.c.max() > 0), want, (date, fr.wx.wind_ms))

    def test_beacon_light_is_steady(self):
        """The beacon's light is the same from one night minute to the next."""
        day = Day(D(2027, 1, 20), weather="fair")
        out = []
        for m in (23 * 60, 23 * 60 + 1):
            fr = lp.Frame(day, m, 0.5)
            fr.c[:] = 0
            fr.beacon()
            fr.beacon_glow()
            x, ly, _ = fr.beacon_light()
            out.append(fr.c[int(ly) - 3:int(ly) + 4, int(x) - 3:int(x) + 4].copy())
        self.assertGreater(float(out[0].max()), 50)
        np.testing.assert_allclose(out[0], out[1], atol=1e-3)


class Reference(unittest.TestCase):
    def test_reference_mode_has_none_of_it(self):
        """In reference mode none of the water's methods run, so the shore kit's frames stay as they were."""
        names = ("sea_shadow", "sea_wind", "glitter", "whitecaps", "beacon", "beacon_light", "beacon_glow", "bay",
                 "sea_marks", "skerry", "mark_positions")
        calls = {}
        saved = {n: getattr(lp.Frame, n) for n in names}

        def spy(name):
            def f(self, *a, **k):
                calls[name] = calls.get(name, 0) + 1
                return saved[name](self, *a, **k)
            return f
        try:
            for n in names:
                setattr(lp.Frame, n, spy(n))
            for ref in (True, False):
                calls.clear()
                fr = frame(D(2027, 1, 20), "12:00", "synthetic", reference=ref)
                fr.render((np.zeros((fr.H, fr.W, 3), np.float32), np.zeros((fr.H, fr.W), np.float32), None))
                if ref:
                    self.assertEqual(calls, {})
                else:
                    self.assertTrue({"sea_shadow", "sea_wind", "glitter", "whitecaps", "beacon", "bay",
                                     "sea_marks", "skerry"} <= set(calls), calls)
        finally:
            for n in names:
                setattr(lp.Frame, n, saved[n])


if __name__ == "__main__":
    unittest.main()
