#!/usr/bin/env python3
"""A frame that cannot be drawn is skipped, not fatal (listening_point.render_chunk).

usage: ./venv/bin/python -m unittest tests.test_skip      (from the repo root; a second)

frame_image is replaced, so nothing is rendered.
"""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "renderers", "procedural"))
import listening_point as lp  # noqa: E402


class Skip(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="lp-skip-")
        self.addCleanup(shutil.rmtree, self.out, True)
        self.addCleanup(lp.W_.clear)
        lp.W_.update(out=self.out, quality=80)

    def chunk(self, minutes, bad=(), image=None):
        def frame_image(m):
            if m in bad:
                raise ValueError(f"no frame for minute {m}")
            return image or Image.new("RGB", (8, 5), (m % 256, 0, 0))
        said = io.StringIO()
        with mock.patch.object(lp, "frame_image", frame_image), contextlib.redirect_stdout(said):
            return lp.render_chunk(minutes), said.getvalue()

    def names(self):
        return sorted(os.listdir(self.out))

    def test_one_bad_minute_costs_one_frame(self):
        (done, failed), said = self.chunk(range(565, 571), bad={567})
        self.assertEqual(failed, [567])
        self.assertEqual([os.path.basename(p) for p in done], ["0925.jpg", "0926.jpg", "0928.jpg", "0929.jpg", "0930.jpg"])
        self.assertEqual(self.names(), ["0925.jpg", "0926.jpg", "0928.jpg", "0929.jpg", "0930.jpg"])
        self.assertIn("frame 0927 failed and is skipped", said)
        self.assertIn("ValueError: no frame for minute 567", said, "the traceback is in the log")

    def test_bad_minutes_apart_are_each_skipped(self):
        bad = set(range(0, 60, 2))                      # every other minute: never ten in a row
        (done, failed), _ = self.chunk(range(60), bad=bad)
        self.assertEqual((len(done), len(failed)), (30, 30))

    def test_ten_in_a_row_stops_the_run(self):
        self.assertEqual(lp.SKIP_MAX, 10)
        (done, failed), _ = self.chunk(range(100, 120), bad=set(range(105, 114)))      # nine: carried through
        self.assertEqual((len(done), len(failed)), (11, 9))
        shutil.rmtree(self.out)
        os.makedirs(self.out)
        with self.assertRaises(ValueError):
            self.chunk(range(100, 120), bad=set(range(105, 115)))
        self.assertEqual(self.names(), ["0140.jpg", "0141.jpg", "0142.jpg", "0143.jpg", "0144.jpg"])

    def test_a_frame_that_cannot_be_saved_still_stops_the_run(self):
        image = mock.Mock()
        image.save.side_effect = OSError(28, "No space left on device")
        with self.assertRaises(OSError):
            self.chunk(range(3), image=image)
        self.assertEqual(self.names(), [])

    def test_nothing_failed(self):
        (done, failed), said = self.chunk(range(3))
        self.assertEqual((len(done), failed, said), (3, [], ""))


if __name__ == "__main__":
    unittest.main()
