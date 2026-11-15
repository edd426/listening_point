#!/usr/bin/env python3
"""What tools/nightly.py decides to render on one run: the rest of today and, from 18:00, tomorrow, once.

usage: ./venv/bin/python -m unittest tests.test_nightly      (from the repo root; a second)

render(), the power source and the side jobs (the listener's outbox, the shore, the hourly wallpaper,
the weather note) are replaced by recorders, and the root is a temporary folder: nothing is rendered,
fetched or written outside it.
"""
import datetime as dt
import os
import shutil
import sys
import tempfile
import unittest
import warnings
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import nightly  # noqa: E402

DAY = dt.date(2026, 11, 15)
NEXT = DAY + dt.timedelta(days=1)


def at(h, m=0, d=DAY):
    return dt.datetime.combine(d, dt.time(h, m))


class Plan(unittest.TestCase):
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)    # main() holds its lock file until the process ends

    def run_at(self, times, power=("ac", 100), argv=(), ready=True):
        """Run main() with the clock reading each of `times` in turn (the last one from then on); returns
        the render() calls as (date, first minute, last minute, why)."""
        root = tempfile.mkdtemp(prefix="nightly-")
        self.addCleanup(shutil.rmtree, root, True)
        times, calls = list(times), []

        def clock():
            return times.pop(0) if len(times) > 1 else times[0]

        def render(days, d, minutes, jobs, why):
            minutes = list(minutes)
            calls.append((d, minutes[0], minutes[-1], why.split(",")[0]))
            return True

        quiet = mock.DEFAULT
        with mock.patch.multiple(nightly, render=render, power=lambda: power, shore_on=lambda: False,
                                 drain_listener=quiet, refresh_shore=quiet, refresh_hourly=quiet,
                                 note_weather=quiet, prune=quiet, log=quiet,
                                 missing=lambda folder, minutes: [] if ready else list(minutes)):
            nightly.main(["--root", root, *argv], clock=clock)
        return calls

    def test_before_six_only_the_rest_of_today(self):
        for t in (at(0, 5), at(10), at(17, 59)):
            m = t.hour * 60 + t.minute
            self.assertEqual(self.run_at([t]), [(DAY, max(0, m - 2), 1439, "the rest of today")], t)

    def test_from_six_tomorrow_once(self):
        for t in (at(18), at(21, 40), at(23, 59)):
            calls = self.run_at([t])
            self.assertEqual(calls[1:], [(NEXT, 0, 1439, "tomorrow")], t)
            self.assertEqual(len(calls), 2)

    def test_a_run_that_crosses_six_goes_on_to_tomorrow(self):
        calls = self.run_at([at(17, 50), at(18, 20)])
        self.assertEqual(calls, [(DAY, 17 * 60 + 48, 1439, "the rest of today"), (NEXT, 0, 1439, "tomorrow")])

    def test_a_run_that_crosses_midnight_leaves_the_new_day_alone(self):
        calls = self.run_at([at(23, 50), at(0, 10, NEXT)])
        self.assertEqual(calls, [(DAY, 23 * 60 + 48, 1439, "the rest of today")])
        calls = self.run_at([at(17, 50), at(18, 30, NEXT)])     # asleep for a day in the middle of a run
        self.assertEqual(len(calls), 1)

    def test_force_does_not_bring_tomorrow_forward(self):
        self.assertEqual(len(self.run_at([at(10)], power=("battery", 20), argv=["--force"])), 1)
        self.assertEqual(len(self.run_at([at(19)], power=("battery", 20), argv=["--force"])), 2)

    def test_on_battery_three_hours_and_never_tomorrow(self):
        self.assertEqual(self.run_at([at(19)], power=("battery", 80), ready=False),
                         [(DAY, 19 * 60 - 2, 19 * 60 + 179, "next three hours")])
        self.assertEqual(self.run_at([at(19)], power=("battery", 80), ready=True), [])
        self.assertEqual(self.run_at([at(19)], power=("battery", 30), ready=False), [])

    def test_a_date_asked_for_is_rendered_at_any_hour(self):
        self.assertEqual(self.run_at([at(9)], argv=["--date", "2026-12-21"]),
                         [(dt.date(2026, 12, 21), 0, 1439, "asked for")])

    def test_old_days_go_before_anything_is_rendered(self):
        order = []
        with mock.patch.multiple(nightly, render=lambda *a: order.append("render") or True,
                                 prune=lambda *a: order.append("prune"), power=lambda: ("ac", 100),
                                 shore_on=lambda: False, drain_listener=mock.DEFAULT, refresh_shore=mock.DEFAULT,
                                 refresh_hourly=mock.DEFAULT, note_weather=mock.DEFAULT, log=mock.DEFAULT):
            root = tempfile.mkdtemp(prefix="nightly-")
            self.addCleanup(shutil.rmtree, root, True)
            nightly.main(["--root", root], clock=lambda: at(19))
        self.assertEqual(order, ["prune", "render", "render"])

    def test_due(self):
        self.assertEqual(nightly.TOMORROW_FROM, 18)
        self.assertFalse(nightly.tomorrow_due(at(17, 59), DAY))
        self.assertTrue(nightly.tomorrow_due(at(18), DAY))
        self.assertFalse(nightly.tomorrow_due(at(18, 0, NEXT), DAY))

    def test_no_frame_is_deleted_for_a_forecast(self):
        with open(os.path.join(ROOT, "tools", "nightly.py")) as f:
            src = f.read()
        self.assertNotIn("refresh_tomorrow", src)
        self.assertNotIn('"evening"', src)


class Disk(unittest.TestCase):
    def test_nothing_is_rendered_on_a_nearly_full_disk(self):
        root = tempfile.mkdtemp(prefix="nightly-")
        self.addCleanup(shutil.rmtree, root, True)
        usage = mock.Mock(free=nightly.FREE_MIN - 1)
        lines, ran = [], []
        with mock.patch.object(nightly.shutil, "disk_usage", return_value=usage), \
                mock.patch.object(nightly, "log", lines.append), mock.patch.object(nightly, "_told", []), \
                mock.patch.object(nightly.subprocess, "run", lambda *a, **k: ran.append(a)):
            self.assertFalse(nightly.render(root, DAY, range(10), 1, "test"))
            self.assertFalse(nightly.render(root, NEXT, range(10), 1, "test"))
        self.assertEqual(ran, [])
        self.assertEqual(len(lines), 1, "said once per run")
        self.assertIn("3.0 GB free", lines[0])
        self.assertFalse(os.path.exists(os.path.join(root, DAY.isoformat())))

    def test_frames_already_there_need_no_room(self):
        root = tempfile.mkdtemp(prefix="nightly-")
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, DAY.isoformat()))
        open(os.path.join(root, DAY.isoformat(), "0000.jpg"), "w").close()
        with mock.patch.object(nightly.shutil, "disk_usage", return_value=mock.Mock(free=0)):
            self.assertTrue(nightly.render(root, DAY, range(1), 1, "test"))


if __name__ == "__main__":
    unittest.main()
