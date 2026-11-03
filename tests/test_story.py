#!/usr/bin/env python3
"""Tests for the story over weeks (v3 phase 5, part 1): story.py's calendar and marks.py's drawing.

usage: ./venv/bin/python -m unittest tests.test_story      (from the repo root)

Offline: synthetic and fair weather, and a weather cache made up in a temporary folder.
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "renderers", "procedural"))
sys.path.insert(1, os.path.join(ROOT, "tools"))
import listening_point as lp  # noqa: E402
import story as S  # noqa: E402
import weather as wxmod  # noqa: E402
from core import Layer  # noqa: E402
from day import BUDAPEST, Day  # noqa: E402
from hillside import garden_stage  # noqa: E402

D = dt.date
TZ, LAT, LON = BUDAPEST["tz"], BUDAPEST["lat"], BUDAPEST["lon"]


def story(date, weather="synthetic", cache=None):
    return S.Story(SimpleNamespace(date=date, tzname=TZ, lat=LAT, lon=LON), weather, cache)


def fake_cache(folder, first, last, gale=None, stamp="20200101T000000Z"):
    """An Open-Meteo response in the cache's own name and layout, covering first..last: calm and dry, with a
    gale (gusts 26 m/s) in the afternoon of `gale`."""
    t0, t1 = wxmod._midnight(first, TZ), wxmod._midnight(last + dt.timedelta(days=1), TZ)
    th = np.arange(t0, t1 + 3601, 3600.0)
    n = len(th)
    hv = dict(temperature_2m=[9.0] * n, relative_humidity_2m=[70.0] * n, dew_point_2m=[4.0] * n, precipitation=[0.0] * n,
              rain=[0.0] * n, showers=[0.0] * n, snowfall=[0.0] * n, snow_depth=[0.0] * n, weather_code=[1] * n,
              cloud_cover=[30.0] * n, cloud_cover_low=[10.0] * n, cloud_cover_mid=[10.0] * n, cloud_cover_high=[20.0] * n,
              visibility=[30000.0] * n, wind_speed_10m=[3.0] * n, wind_direction_10m=[250.0] * n, wind_gusts_10m=[5.0] * n)
    if gale is not None:
        g0 = wxmod._midnight(gale, TZ)
        for i, t in enumerate(th):
            if g0 + 12 * 3600 <= t <= g0 + 18 * 3600:
                hv["wind_gusts_10m"][i], hv["wind_speed_10m"][i] = 26.0, 14.0
    data = dict(utc_offset_seconds=3600, hourly_units={"wind_speed_10m": "m/s", "wind_gusts_10m": "m/s"},
                hourly=dict(time=[int(t) for t in th], **hv))
    with open(os.path.join(folder, f"open-meteo-{first}-{last}-{stamp}.json"), "w") as f:
        json.dump(data, f)


class Calendar(unittest.TestCase):
    def test_no_cache_means_nothing_happened(self):
        """Real weather with nothing in the cache: no storm, no work, nothing on the land, and the garden keeps
        to phase 3's calendar; a real gale on record brings a branch down the next morning."""
        tmp = tempfile.mkdtemp()
        try:
            for d in (D(2027, 1, 20), D(2027, 3, 20), D(2027, 7, 1), D(2027, 11, 20)):
                st = story(d, "auto", tmp)
                self.assertEqual(st.garden, garden_stage(d.timetuple().tm_yday))
                self.assertFalse(st.wall or st.branch or st.driftwood or st.logs or any(st.drift) or st.walls, d)
            fake_cache(tmp, D(2027, 2, 5), D(2027, 2, 11), gale=D(2027, 2, 8))
            self.assertIsNone(story(D(2027, 2, 8), "auto", tmp).branch)          # not until the night after
            st = story(D(2027, 2, 9), "auto", tmp)
            self.assertIsNotNone(st.branch)
            self.assertEqual(st.branch["fell"], D(2027, 2, 8))
            self.assertIsNone(story(D(2027, 2, 9), "auto", None).branch)        # no cache: nothing
            # a forecast fetched after the date began is not used for it
            tmp2 = tempfile.mkdtemp()
            fake_cache(tmp2, D(2027, 2, 5), D(2027, 2, 11), gale=D(2027, 2, 8), stamp="20270209T120000Z")
            self.assertIsNone(story(D(2027, 2, 9), "auto", tmp2).branch)
            self.assertIsNotNone(story(D(2027, 2, 10), "auto", tmp2).branch)
            shutil.rmtree(tmp2)
        finally:
            shutil.rmtree(tmp)

    def test_fair_weather_is_phase_3(self):
        """Fair weather is fit for work every day and brings no storm: the garden is phase 3's to the bit."""
        for i in range(0, 366, 3):
            d = D(2027, 1, 1) + dt.timedelta(days=i)
            st = story(d, "fair")
            self.assertEqual(st.garden, garden_stage(d.timetuple().tm_yday), d)
            self.assertFalse(st.wall or st.branch or st.driftwood or st.logs, d)

    def test_wall_rises_only_after_workable_days(self):
        """The fallen wall is rebuilt course by course, and changes overnight only after a day fit for work
        (its coming down follows a gale or a thaw instead)."""
        h = S.History("synthetic", None, TZ, LAT, LON, D(2027, 6, 1))
        seen, prev = [], None
        for i in range(0, 140):
            d = D(2026, 11, 20) + dt.timedelta(days=i)
            w = story(d).wall
            k = None if w is None else (w["state"], w["built"], w["pile"], w["line"])
            if prev is not None and k != prev[1]:
                if prev[1] is not None:
                    self.assertTrue(h.workable(prev[0]), (prev[0], prev[1], k))
                    if k is not None:
                        self.assertGreaterEqual(k[1], prev[1][1])
                seen.append("down" if prev[1] is None else "whole" if k is None else "work")
            prev = (d, k)
        # 2026-27's synthetic winter has the whole arc: down, rebuilt in steps, whole again
        self.assertEqual(seen[0], "down")
        self.assertEqual(seen[-1], "whole")
        self.assertGreater(seen.count("work"), 8)

    def test_garden_steps_with_the_work(self):
        """The garden's work never goes back within its year, never runs ahead of phase 3's calendar, and moves
        on only after a workable day."""
        h = S.History("synthetic", None, TZ, LAT, LON, D(2028, 1, 1))
        prev = None
        lagged = 0
        for i in range(0, 300):
            d = D(2027, 2, 20) + dt.timedelta(days=i)
            g = story(d).garden
            base = garden_stage(d.timetuple().tm_yday)
            for f in ("dug", "sown", "cleared", "rough"):
                self.assertLessEqual(getattr(g, f), getattr(base, f) + 1e-9, (d, f))
                lagged += getattr(g, f) < getattr(base, f) - 0.01
                if prev is not None:
                    self.assertGreaterEqual(getattr(g, f), getattr(prev[1], f) - 1e-12, (d, f))
            if prev is not None and g != prev[1] and (g.dug, g.sown, g.cleared, g.rough) != \
                    (prev[1].dug, prev[1].sown, prev[1].cleared, prev[1].rough):
                self.assertTrue(h.workable(prev[0]) or not h(prev[0]).known, d)
            prev = (d, g)
        self.assertGreater(lagged, 0)                       # bad weeks do hold it up

    def test_places_keep_from_day_to_day(self):
        """What the story places (the gap, the branch, the driftwood) is in the same place every day it shows."""
        for days in ((D(2027, 1, 22), D(2027, 1, 23), D(2027, 1, 30)), (D(2026, 12, 8), D(2026, 12, 9), D(2026, 12, 10))):
            sts = [story(d) for d in days]
            for a, b in zip(sts, sts[1:]):
                if a.wall and b.wall:
                    self.assertEqual((a.wall["site"], a.wall["mid"], a.wall["half"], a.wall["seed"]),
                                     (b.wall["site"], b.wall["mid"], b.wall["half"], b.wall["seed"]))
                if a.branch and b.branch:
                    self.assertEqual((a.branch["seed"], a.branch["wind_from"]), (b.branch["seed"], b.branch["wind_from"]))
                if a.driftwood and b.driftwood:
                    self.assertEqual([(p["slot"], p["v"], p["seed"]) for p in a.driftwood],
                                     [(p["slot"], p["v"], p["seed"]) for p in b.driftwood])
        self.assertTrue(story(D(2027, 1, 22)).branch and story(D(2026, 12, 9)).driftwood)

    def test_driftwood_keeps_off_the_shore_kits_ground(self):
        """Driftwood lies below the always-dry band where the shore kit's objects stand (shore_reference.DRY_V),
        above the day's high water when it arrives."""
        import shore_reference as sr
        n = 0
        for i in range(0, 730, 1):
            st = story(D(2026, 11, 1) + dt.timedelta(days=i))
            for p in st.driftwood:
                n += 1
                self.assertLess(p["v"], sr.DRY_V[0])
                self.assertLessEqual(p["v"], S.DRIFT_TOP)
        self.assertGreater(n, 0)

    def test_deterministic_and_reference_empty(self):
        a, b = story(D(2027, 1, 25)), story(D(2027, 1, 25))
        for k in ("garden", "walls", "wall", "branch", "scar", "logs", "driftwood", "drift", "spade"):
            self.assertEqual(getattr(a, k), getattr(b, k), k)
        day = Day(D(2027, 1, 25), weather="synthetic", reference=True)
        self.assertIsInstance(day.story, S.NoStory)
        self.assertFalse(isinstance(day.story, S.Story))
        self.assertIsNone(getattr(day, "garden_stage", None))
        self.assertFalse(getattr(day, "wall_stages", None))


SCALE = 0.25


def draw(day, m=720):
    """The hillside drawn alone (with the story's marks), as the albedo layer's array."""
    fr = lp.Frame(day, m, SCALE)
    y0 = int(0.58 * fr.H)
    xw = int(np.ceil(0.46 * fr.W))
    A, N, X, WM = (Layer(fr, 0, y0, xw, fr.H) for _ in range(4))
    persp = lambda y: 0.35 + 1.3 * np.clip((np.asarray(y) / fr.H - 0.6) / 0.4, 0, 1)
    fr.hillside(A, N, X, WM, persp)
    return np.asarray(A.img), fr, y0


class Marks(unittest.TestCase):
    def test_branch_stays_put(self):
        """The branch lies in the same pixels on consecutive days (a winter branch has no leaves to wilt), and is
        gone once cleared."""
        a, fr, y0 = draw(Day(D(2027, 1, 22), weather="synthetic"))
        b, _, _ = draw(Day(D(2027, 1, 23), weather="synthetic"))
        c, _, _ = draw(Day(D(2027, 2, 10), weather="synthetic"))
        ss = 2
        box = (slice(int((0.69 * fr.H - y0) * ss), int((0.735 * fr.H - y0) * ss)), slice(int(0.33 * fr.W * ss), int(0.445 * fr.W * ss)))
        np.testing.assert_array_equal(a[box], b[box])
        self.assertFalse(np.array_equal(a[box], c[box]))

    def test_nothing_in_the_story_draws_nothing(self):
        """With an empty story the hillside is drawn exactly as phase 3 drew it."""
        day = Day(D(2027, 1, 22), weather="synthetic")
        a, _, _ = draw(day)
        day.story = S.NoStory()
        day.garden_stage, day.wall_stages = None, {}
        b, _, _ = draw(day)
        self.assertFalse(np.array_equal(a, b))
        day2 = Day(D(2027, 1, 22), weather="synthetic", reference=True)
        c, _, _ = draw(day2)
        np.testing.assert_array_equal(b, c)


if __name__ == "__main__":
    unittest.main()
