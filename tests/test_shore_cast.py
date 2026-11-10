#!/usr/bin/env python3
"""Tests for the cast shadows of the shore's objects in the renderer (renderers/procedural/shore.py): the Mac draws
the very pixels the kit lays out (shorekit.compose.cast_shown), in the direction of the scene's own shadows, as
dark as the light allows, and they turn with the sun.

usage: ./venv/bin/python -m unittest tests.test_shore_cast      (from the repo root; under a minute)

Offline. The shore here is synthetic, made at run time in a temporary folder in the kit's layout, against the
kit's own synthetic reference set written with cast shadows (shorekit/tests/support.py): no shore data ever sits
in this repository.
"""
import copy
import datetime as dt
import math
import os
import pickle
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
import support as K  # noqa: E402  (the kit's synthetic reference set)
from core import KF  # noqa: E402
from day import Day  # noqa: E402
from shorekit import CAST_MAX_DX, CAST_MAX_DY  # noqa: E402
from shorekit.compose import cast_shown  # noqa: E402
from shorekit.ledger import Shore, ledger_bytes, load_shore  # noqa: E402
from shorekit.manifest import manifest_from_obj  # noqa: E402
from shorekit.reference import load_reference  # noqa: E402
from shorekit.rules import draw_order, paint  # noqa: E402

D = dt.date
TMP = tempfile.mkdtemp(prefix="shore-cast-")
NATIVE = 0.75                    # the 2880 x 1800 frame the kit's pixels are laid out in
DAY = D(2026, 11, 11)            # a short clear day: the sun rises in the south-east and sets in the south-west
MOON = D(2026, 11, 24)           # a full moon, high at 23:00
RED = {"a": (210, 60, 48)}


def tearDownModule():
    shutil.rmtree(TMP, True)


def minute(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def open_x(ref, x0, reach):
    """The first column from x0 whose dry band has no keep-out for `reach` columns either side."""
    for x in range(x0, ref.rx1 - reach, 5):
        cols = [ref.dry(X) for X in range(x - reach, x + reach + 1)]
        if all(cols) and not any(ref.keepout[ref.index(X, Y)] for X in range(x - reach, x + reach + 1, 3)
                                 for Y in range(cols[reach][0] - 80, cols[reach][1] + 30, 3)):
            return x
    raise AssertionError("no open stretch of the synthetic shingle from x=%d" % x0)


def stand(ref, x, half):
    """A foot row every column within `half` of x has dry shingle on (the band slopes along the shore)."""
    cols = [ref.dry(X) for X in range(x - half, x + half + 1)]
    y = min(b[1] for b in cols) - 1
    assert y >= max(b[0] for b in cols), (x, half)
    return y


def build_cache(name="shore", cast=True):
    """A synthetic shore, accepted the way the carrier would: a tall rod and a red block on the shingle, a flag on
    the pier, and a small stone built onto the block. Returns the cache's path. Without `cast` its reference set
    is the one written before cast shadows (shore_conditions 1)."""
    ref = K.reference_cast() if cast else K.reference()
    shore = Shore(ref)

    def accept(obj, at):
        m = manifest_from_obj(obj)
        errs = shore.judge(m, at[:10])[0]
        assert not errs, [e.line() for e in errs]
        shore.accept(m, at, at, "world-1", "0" * 40)
        return shore.byid[obj["id"]]
    x = open_x(ref, 2480, 45)
    accept(K.make_object("2026-11-02-rod", "maker-a", K.block(3, 18), K.STONE, "shingle", x, stand(ref, x, 8), scale=4),
           "2026-11-02T04:30:00Z")
    x = open_x(ref, x + 110, 45)            # to the right of the rod: its morning shadow reaches the block
    block = accept(K.make_object("2026-11-03-block", "maker-b", K.block(8, 6), RED, "shingle", x, stand(ref, x, 20), scale=4),
                   "2026-11-03T04:30:00Z")
    accept(K.fixture_obj("2026-11-02-flag"), "2026-11-04T04:30:00Z")              # on the pier
    accept(K.make_object("2026-11-05-stone", "maker-a", K.block(4, 4), K.STONE, "2026-11-03-block", block.left + 6, block.top - 1),
           "2026-11-05T04:30:00Z")
    path = os.path.join(TMP, name)
    os.makedirs(os.path.join(path, "objects"))
    shutil.copytree(K.reference_dir_cast() if cast else K.reference_dir(), os.path.join(path, "reference", "r1"))
    with open(os.path.join(path, "ledger.json"), "wb") as f:
        f.write(ledger_bytes(shore.events))
    for oid, m in shore.manifests.items():
        with open(os.path.join(path, "objects", oid + ".json"), "wb") as f:
            f.write(m.canonical)
    return path


def layer(day, m, scale=NATIVE, **kw):
    """The shore alone, drawn into an empty front layer: (frame, premultiplied colour, coverage)."""
    fr = lp.Frame(day, m, scale, **kw)
    fr.c = np.zeros((fr.H, fr.W, 3), np.float32)
    fr.a = np.zeros((fr.H, fr.W), np.float32)
    fr.shore()
    return fr, fr.c, fr.a


class Vector(unittest.TestCase):
    def test_it_is_the_scene_s_own_projection_in_whole_numbers(self):
        """land.shadow_masks: cot = min(1/tan(alt), 3), sx = sin(az) cot, sy = -cos(az) cot KF; x256, halves up."""
        for alt in (1.01, 2.5, 10.2, 18.4349, 24.7, 42.8, 66.6, 89.9):
            for az in (45.0, 90.0, 130.2, 157.4, 180.0, 188.4, 217.8, 242.2, 270.0, 315.0):
                cot = min(1 / math.tan(math.radians(alt)), 3.0)
                sx, sy = math.sin(math.radians(az)) * cot, -math.cos(math.radians(az)) * cot * KF
                dx, dy = shore_mod.cast_vector(alt, az)
                self.assertEqual((dx, dy), (math.floor(256 * sx + 0.5), math.floor(256 * sy + 0.5)), (alt, az))
                self.assertTrue(type(dx) is int and type(dy) is int)
                self.assertTrue(abs(dx) <= CAST_MAX_DX and abs(dy) <= CAST_MAX_DY, (alt, az, dx, dy))   # the kit takes it
        # the viewer looks south: a sun in the east is on the left, and its shadows fall to the right
        self.assertGreater(shore_mod.cast_vector(10, 110)[0], 0)
        self.assertLess(shore_mod.cast_vector(10, 250)[0], 0)
        # a sun in the south is ahead: shadows come toward the viewer, down the frame, longer the lower it stands
        self.assertEqual(shore_mod.cast_vector(45, 180), (0, 77))
        self.assertGreater(shore_mod.cast_vector(20, 180)[1], shore_mod.cast_vector(45, 180)[1])
        # a sun in the north-east (a summer dawn) throws them up the frame, behind the thing
        self.assertLess(shore_mod.cast_vector(10, 60)[1], 0)
        # and nothing is longer than three times its height
        self.assertEqual(shore_mod.cast_vector(1.5, 90), (768, 0))


class Strength(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clear = Day(DAY, weather="clear")

    def cast(self, hhmm, day=None, **kw):
        return lp.Frame(day or self.clear, minute(hhmm), 0.25, **kw).shore_cast()

    def test_follows_the_sun_that_gets_through(self):
        noon = self.cast("12:00")
        self.assertAlmostEqual(noon[2], shore_mod.CAST, 3)              # a full sun: the animals' own share
        self.assertIsNone(self.cast("12:00", sun="off"))                # the sun behind cloud: no shadow
        self.assertIsNone(self.cast("12:00", Day(DAY, weather="fog")))  # nor in the reference's fog
        fr = lp.Frame(Day(DAY, weather="fog"), 720, 0.25)
        self.assertLessEqual(fr.sun_str, shore_mod.CAST_FROM[0] + 0.01)

    def test_comes_in_with_the_sun_and_never_takes_more_than_the_direct_light(self):
        self.assertIsNone(self.cast("06:30"))                           # before sunrise (06:42)
        self.assertIsNone(self.cast("16:30"))                           # after sunset (16:12)
        ks = []
        for m in range(minute("06:40"), minute("12:00"), 10):
            fr = lp.Frame(self.clear, m, 0.25)
            c = fr.shore_cast()
            k = 0.0 if c is None else c[2]
            self.assertLessEqual(k, shore_mod.CAST + 1e-6)
            self.assertLessEqual(k, fr.shore_direct() + 1e-6, m)
            if fr.sun_alt <= 1:
                self.assertIsNone(c)
            ks.append(k)
        self.assertEqual(ks[0], 0.0)
        self.assertEqual(ks, sorted(ks))                                # no jump back: it only grows through the morning
        self.assertLess(max(b - a for a, b in zip(ks, ks[1:])), 0.2)    # and it does not pop in
        low = lp.Frame(self.clear, minute("07:15"), 0.25)               # a low sun: most of the light there is the sky's
        self.assertLess(low.shore_cast()[2], 0.25)
        self.assertAlmostEqual(low.shore_cast()[2], low.shore_direct(), 5)

    def test_weaker_under_a_bright_moon_and_none_under_a_thin_one(self):
        full = self.cast("23:00", Day(MOON, weather="clear"))
        self.assertIsNotNone(full)
        self.assertTrue(0.05 < full[2] <= shore_mod.CAST_MOON < shore_mod.CAST, full)
        self.assertIsNone(self.cast("23:00"))                           # the 11th: a moon two days old, and set
        self.assertIsNone(self.cast("23:00", Day(MOON, weather="fog")))
        half = Day(D(2026, 11, 17), weather="clear")                    # first quarter, up in the evening
        fr = lp.Frame(half, minute("19:00"), 0.25)
        self.assertTrue(fr.moon_alt > 4 and 0.3 < fr.moon_frac < 0.7, (fr.moon_alt, fr.moon_frac))
        self.assertIsNone(fr.shore_cast())


class Drawn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = build_cache()
        cls.ref = load_reference(os.path.join(cls.cache, "reference", "r1"))
        # the kit's own view of the same cache, read apart from the renderer's
        cls.objs = load_shore(cls.ref, os.path.join(cls.cache, "ledger.json"), os.path.join(cls.cache, "objects")).live
        cls.day = Day(DAY, weather="clear", shore=cls.cache)
        cls.night = Day(MOON, weather="clear", shore=cls.cache)
        owner, drawn = paint(draw_order(cls.objs), cls.ref.cw * cls.ref.ch)
        cls.solid = np.frombuffer(owner.tobytes(), np.uint16).reshape(cls.ref.ch, cls.ref.cw) > 0
        cls.contact = np.zeros_like(cls.solid)
        for ds in drawn:
            for i in ds:
                if owner[i] == 0:
                    cls.contact[i // cls.ref.cw, i % cls.ref.cw] = True

    def crop(self, a):
        ref = self.ref
        return a[ref.cy:ref.cy + ref.ch, ref.cx:ref.cx + ref.cw]

    def kit_cast(self, dx, dy):
        mask = np.zeros_like(self.solid)
        idx = cast_shown(self.ref, self.objs, dx, dy)
        mask.ravel()[idx] = True
        return mask

    def test_the_mac_draws_the_kit_s_pixels(self):
        """Solid pixels, contact shadows and cast shadows: the layer covers exactly what the kit lays out for this
        minute's light, each shadow pixel black and as dark as the rule says."""
        ref = self.ref
        seen = full = 0
        for day, hhmm in ((self.day, "08:00"), (self.day, "11:30"), (self.day, "14:30"), (self.night, "23:00")):
            fr, c, a = layer(day, minute(hhmm))
            self.assertEqual((fr.W, fr.H), (ref.frame_w, ref.frame_h))
            dx, dy, k = fr.shore_cast()
            cast = self.kit_cast(dx, dy)
            self.assertGreater(int(cast.sum()), 150, hhmm)
            self.assertFalse((cast & self.solid).any())
            got = self.crop(a) > 0
            whole = self.solid | self.contact | cast
            self.assertTrue(np.array_equal(got, whole), (hhmm, int((got ^ whole).sum())))
            outside = a.copy()
            self.crop(outside)[...] = 0
            self.assertEqual(float(outside.max()), 0.0)
            # how dark: the cast shadow takes k of the light, less where the scenery's own shadow already lies
            sh, _ = fr.shadow_masks()
            want = k * (1 - self.crop(sh))
            ca, cc = self.crop(a), self.crop(c)
            only = cast & ~self.contact
            self.assertTrue(np.allclose(ca[only], want[only], atol=1e-6), hhmm)
            self.assertLessEqual(float(ca[only].max()), k + 1e-6)
            if (self.crop(sh)[only] == 0).any():                                    # open ground: all of k
                self.assertAlmostEqual(float(ca[only].max()), k, 5)
                full += 1
            both = cast & self.contact
            self.assertTrue(both.any(), hhmm)
            self.assertTrue(np.allclose(ca[both], 1 - (1 - want[both]) * (1 - shore_mod.SHADOW), atol=1e-6), hhmm)
            alone = self.contact & ~cast
            self.assertTrue(np.allclose(ca[alone], shore_mod.SHADOW), hhmm)
            self.assertTrue(np.all(ca[self.solid] == 1.0))
            self.assertEqual(float(np.abs(cc[cast | self.contact]).max()), 0.0)      # a shadow only takes light away
            seen += 1
        self.assertEqual(seen, 4)
        self.assertGreaterEqual(full, 2)        # (early on this day the tower's own long shadow lies over the shore)

    def test_the_shadow_turns_with_the_sun(self):
        """The rod is a sundial: its shadow lies to the right in the morning (the sun is in the east, on the left),
        comes round under it toward the viewer at noon, and lies to the left in the afternoon."""
        rod = next(o for o in self.objs if o.id == "2026-11-02-rod")
        tips, dxs = [], []
        for hhmm in ("08:00", "09:30", "11:30", "13:00", "14:30"):
            fr = lp.Frame(self.day, minute(hhmm), 0.25)
            dx, dy, _ = fr.shore_cast()
            idx = shore_mod.kit().geometry.cast_pixels(rod, self.ref, dx, dy)
            xs = np.array([i % self.ref.cw + self.ref.cx for i in idx])
            ys = np.array([i // self.ref.cw + self.ref.cy for i in idx])
            self.assertGreater(len(idx), 100, hhmm)
            self.assertTrue(np.all(ys > rod.foot_y), hhmm)                 # November: the sun is always to the south
            far = int(np.argmax(ys))                                       # the tip: the top pixel's shadow
            tips.append(int(xs[far]) - (rod.left + rod.right) // 2)
            dxs.append(dx)
        self.assertEqual(dxs, sorted(dxs, reverse=True))
        self.assertEqual(tips, sorted(tips, reverse=True))
        self.assertGreater(tips[0], 60)                                    # 08:00: well to the right
        self.assertLess(abs(tips[2]), 12)                                  # 11:30, about solar noon: straight down
        self.assertLess(tips[-1], -60)                                     # 14:30: well to the left

    def test_without_light_to_cast_one_the_layer_is_as_it_was(self):
        for day, hhmm in ((self.day, "03:00"), (self.day, "16:30"), (Day(DAY, weather="fog", shore=self.cache), "12:00")):
            fr, c, a = layer(day, minute(hhmm))
            self.assertIsNone(fr.shore_cast())
            got = self.crop(a)
            self.assertTrue(np.array_equal(got > 0, self.solid | self.contact), hhmm)
            self.assertTrue(np.all(got[self.contact] == np.float32(shore_mod.SHADOW)), hhmm)
        # and with the sun hidden, a frame that has objects is the frame it was before there were cast shadows
        fr, c, a = layer(self.day, 720, sun="off")
        saved = lp.Frame.shore_cast
        lp.Frame.shore_cast = lambda self: None
        try:
            _, c0, a0 = layer(self.day, 720, sun="off")
        finally:
            lp.Frame.shore_cast = saved
        self.assertTrue(np.array_equal(a, a0) and np.array_equal(c, c0))

    def test_a_reference_set_from_before_cast_shadows_draws_none(self):
        """The kit's preview shows no cast shadow against a set written as shore_conditions 1, so neither does the
        Mac: they arrive with the reference set that carries them."""
        old = build_cache("old-set", cast=False)
        day = Day(DAY, weather="clear", shore=old)
        self.assertEqual(day.shore.ref.conditions_version, 1)
        fr, c, a = layer(day, minute("11:30"))
        self.assertIsNotNone(fr.shore_cast())                    # the sun is out
        self.assertIsNone(fr.shore_cast_pixels(day.shore.at(minute("11:30"))))
        got = self.crop(a)
        self.assertTrue(np.array_equal(got > 0, self.solid | self.contact))
        self.assertTrue(np.all(got[self.contact] == np.float32(shore_mod.SHADOW)))

    def test_other_frame_sizes_show_it_too(self):
        """A preview at another scale resamples the native pixels: the shadow is there too."""
        _, c1, a1 = layer(self.day, minute("09:30"), 0.3)
        saved = lp.Frame.shore_cast
        lp.Frame.shore_cast = lambda self: None
        try:
            _, c0, a0 = layer(self.day, minute("09:30"), 0.3)
        finally:
            lp.Frame.shore_cast = saved
        self.assertGreater(float((a1 - a0).sum()), 20.0)
        self.assertGreater(int(((a1 > 0) & (a0 == 0)).sum()), 100)

    def test_the_workers_get_what_the_kit_needs(self):
        """The day is pickled to the render workers: the kit's reference set and placed objects go with it."""
        blob = pickle.dumps(self.day.shore)
        self.assertLess(len(blob), 24 << 20)
        day = copy.copy(self.day)
        day.shore = pickle.loads(blob)
        self.assertEqual(day.shore.ref.digest, self.ref.digest)
        m = minute("09:30")
        a = layer(self.day, m)[2]
        b = layer(day, m)[2]
        self.assertTrue(np.array_equal(a, b))
        self.assertGreater(int((self.crop(a) > 0).sum()), int((self.solid | self.contact).sum()))


class ReferenceDir(unittest.TestCase):
    def test_the_newest_set_is_the_one_in_use(self):
        """A Mac that moves to a new reference set builds it beside the old one: the renderer takes the newest."""
        path = os.path.join(TMP, "sets")
        os.makedirs(os.path.join(path, "reference"))
        with self.assertRaises(ValueError):
            shore_mod.reference_dir(path)
        for name in ("r2", "r9", "r10", "notes", ".r11.partial"):
            os.makedirs(os.path.join(path, "reference", name))
        self.assertEqual(shore_mod.reference_dir(path), os.path.join(path, "reference", "r10"))
        with open(os.path.join(path, "kit.lock"), "w") as f:
            f.write('{"shore_kit_lock":1,"kit":"1.3.0","commit":"%s","pyz_sha256":"%s","reference":"r2"}' % ("0" * 40, "0" * 64))
        self.assertEqual(shore_mod.reference_dir(path), os.path.join(path, "reference", "r2"))


if __name__ == "__main__":
    unittest.main()
