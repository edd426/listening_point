#!/usr/bin/env python3
"""Tests for the shore kit's reference frames: the renderer's --reference mode and tools/shore_reference.py.

usage: ./venv/bin/python tests/test_shore_reference.py [test_name ...]      (from the repo root)

Offline. Building a reference set renders four full frames (about half a minute); the determinism test
builds two. Set SHORE_REFERENCE=DIR to also check a set built beforehand. Nothing is written inside the
repository: reference sets are shore data and go to a temporary folder.
"""
import datetime as dt
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "renderers", "procedural"))
sys.path.insert(1, os.path.join(ROOT, "tools"))
sys.path.insert(2, ROOT)
import listening_point as lp  # noqa: E402
import shore_reference as sr  # noqa: E402
from day import Day  # noqa: E402
from shorekit.reference import load_reference  # noqa: E402

D = dt.date
PY = sys.executable
TOOL = os.path.join(ROOT, "tools", "shore_reference.py")
# Every method that draws a creature, a rare event or a passing thing. In reference mode none may draw.
DRAWERS = ("comet", "ghost_ship", "far_lights", "whale", "footprints", "bottle", "book", "door_light", "pier_gulls",
           "sheep", "critters", "cat", "heron", "owl", "sky_extras", "boats", "falling_leaves", "high_air", "air_kite",
           "fox", "hares", "crows", "beacon", "beacon_glow", "sea_marks", "skerry", "whitecaps",
           "far_sea", "ferry", "yachts", "gannets", "creel_boat", "skerry_life", "draw_seal_head", "dolphins",
           "sea_lights")
# (date, time, weather, what normal mode draws then): each a day when it really happens (2027's schedule)
CASES = [
    (D(2027, 1, 25), "02:05", "fair", {"far_lights"}),                    # the light in the empty cottage
    (D(2027, 1, 26), "08:00", "fair", {"book"}),
    (D(2027, 2, 25), "03:20", "fair", {"far_lights"}),                    # the lantern on the far shore
    (D(2027, 1, 2), "03:05", "fog", {"ghost_ship"}),
    (D(2027, 3, 17), "06:00", "fair", {"heron", "sheep"}),
    (D(2027, 3, 17), "10:00", "fair", {"bottle", "pier_gulls", "sheep", "cat", "crows"}),
    (D(2027, 3, 17), "17:40", "fair", {"hares"}),                         # hares at dusk
    (D(2027, 3, 5), "18:59", "fair", {"fox"}),                            # the fox at dusk
    (D(2027, 3, 5), "06:58", "fair", {"hares"}),                          # two hares boxing
    (D(2027, 7, 6), "21:30", "fair", {"critters"}),                       # bats
    (D(2027, 3, 17), "22:00", "fair", {"owl"}),
    (D(2027, 6, 19), "12:14", "fair", {"whale"}),
    (D(2027, 7, 6), "00:00", "fair", {"comet"}),
    (D(2027, 9, 27), "08:57", "fair", {"door_light"}),
    (D(2027, 10, 20), "12:00", "fair", {"falling_leaves"}),
    (D(2027, 1, 12), "10:20", "fair", {"high_air"}),                      # a contrail and its aircraft
    (D(2027, 1, 12), "18:40", "fair", {"high_air"}),                      # a night flight's lights (17:15 had none)
    (D(2027, 1, 15), "16:00", "fair", {"sky_extras"}),                    # starlings at dusk
    (D(2027, 5, 3), "06:20", "fair", {"sky_extras"}),                     # a balloon
    (D(2027, 4, 25), "15:00", "synthetic", {"air_kite"}),
    (D(2027, 1, 20), "12:00", "synthetic", {"beacon", "sea_marks", "skerry", "whitecaps"}),   # the water in a blow
    (D(2026, 11, 13), "12:00", "synthetic", {"beacon", "sea_marks", "skerry"}),                 # low water, a calm
    (D(2027, 6, 10), "08:25", "fair", {"creel_boat", "far_sea", "ferry"}),       # the creel boat at the pots, the ferry
    (D(2027, 1, 19), "17:24", "fair", {"ferry", "sea_lights", "skerry_life"}),   # the ferry's lights, the pale seal
    (D(2027, 5, 20), "08:15", "fair", {"skerry_life"}),                          # seals hauled out, the cormorant
    (D(2027, 5, 20), "07:15", "fair", {"draw_seal_head"}),                       # a seal waiting in the water
    (D(2027, 5, 20), "16:00", "fair", {"yachts"}),                               # an extra yacht
    (D(2027, 6, 8), "12:30", "fair", {"gannets"}),
    (D(2027, 6, 18), "15:30", "fair", {"dolphins"}),
]
SMALL = 0.25


def minute(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def render_with_spies(day, m, scale=SMALL):
    """Render minute m and report which drawing methods changed any pixel, and how many glows the night
    lights made in the colours of moths and fireflies."""
    drew, specks = set(), [0]

    def wrap(name, real):
        def spy(self, *args, **kw):
            arrays = [self.c] + [a for a in args if isinstance(a, np.ndarray)] + ([self.a] if self.a is not None else [])
            before = [a.copy() for a in arrays]
            out = real(self, *args, **kw)
            if any(not np.array_equal(b, a) for b, a in zip(before, arrays)):
                drew.add(name)
            return out
        return spy

    real_glow, real_nl = lp.Frame.glow, lp.Frame.night_lights

    def night_lights(self):
        def glow(x, y, r, col, k, tail=0.0):
            if tuple(col) in ((255, 230, 190), (210, 255, 130), (170, 230, 100)):
                specks[0] += 1
            return real_glow(self, x, y, r, col, k, tail)
        self.glow = glow
        try:
            return real_nl(self)
        finally:
            del self.glow
    saved = {n: getattr(lp.Frame, n) for n in DRAWERS}
    try:
        for n in DRAWERS:
            setattr(lp.Frame, n, wrap(n, saved[n]))
        lp.Frame.night_lights = night_lights
        fr = lp.Frame(day, m, scale)
        # no near scenery (hill, pier, tree): nothing that comes and goes is drawn there
        img = fr.render((np.zeros((fr.H, fr.W, 3), np.float32), np.zeros((fr.H, fr.W), np.float32), None))
    finally:
        for n in DRAWERS:
            setattr(lp.Frame, n, saved[n])
        lp.Frame.night_lights = real_nl
    return drew, specks[0], img


def test_reference_mode_draws_no_creature_or_rare_event():
    seen = set()
    for date, hhmm, wx, expect in CASES:
        m = minute(hhmm)
        drew, specks, _ = render_with_spies(Day(date, weather=wx), m)
        assert expect <= drew, (date, hhmm, "normal mode should draw", expect - drew)
        seen |= drew
        day = Day(date, weather=wx, reference=True)
        my, ev = day.mysteries, day.events
        assert not any((my.comet, my.ghost, my.cottage, my.lantern, my.prints, my.whale, my.bottle, my.book,
                        my.clock_stopped, my.door)), date
        assert ev.trip is None and not ev.heron and not ev.owl and not ev.gulls and not ev.geese and not ev.meteors
        assert not ev.flights and not ev.contrails and not ev.starlings and not ev.balloons and not ev.kite
        assert not ev.fox and not ev.hares and not ev.boxing and not ev.crow_visits
        sea = day.sea          # the bay's boats and animals (seaplan.py): none
        assert not (sea.ferry or sea.creel or sea.yachts or sea.gannets or sea.dolphins or sea.cormorant or sea.seal_swims)
        drew, specks, img = render_with_spies(day, m)
        assert not drew, (date, hhmm, "reference mode drew", drew)
        assert specks == 0, (date, hhmm, "moths or fireflies in reference mode")
    assert seen >= {"comet", "ghost_ship", "far_lights", "whale", "bottle", "book", "door_light", "pier_gulls",
                    "sheep", "critters", "cat", "heron", "owl", "falling_leaves", "high_air", "air_kite",
                    "fox", "hares", "crows", "beacon", "beacon_glow", "sea_marks", "skerry", "whitecaps",
                    "far_sea", "ferry", "yachts", "gannets", "creel_boat", "skerry_life", "draw_seal_head", "dolphins",
                    "sea_lights"}, seen
    # the moths and fireflies of a warm summer night show only in normal mode
    day = Day(D(2027, 7, 6), weather="fair")
    assert render_with_spies(day, minute("23:30"))[1] > 0
    assert render_with_spies(Day(D(2027, 7, 6), weather="fair", reference=True), minute("23:30"))[1] == 0
    # the stopped clock is a rare event inside the tower's own drawing: off in reference mode
    assert Day(D(2027, 9, 14), weather="fair").mysteries.clock_stopped
    assert not Day(D(2027, 9, 14), weather="fair", reference=True).mysteries.clock_stopped


def test_reference_mode_has_no_grain_and_holds_the_tide():
    day = Day(sr.DATE, weather="clear", reference=True)
    assert np.all(day.tide == 1.0)
    a = lp.Frame(day, 600, SMALL)
    assert a.reference and not lp.Frame(Day(sr.DATE, weather="clear"), 600, SMALL).reference
    a.c = np.full((a.H, a.W, 3), 100, np.float32)
    vig, _ = lp.grade_maps(a.W, a.H)
    want = np.clip(100 * vig[..., None] + 0.5, 0, 255).astype(np.uint8)
    assert np.array_equal(a.grade(), np.repeat(want, 3, -1)), "reference frames must carry no grain"


def git_status():
    return subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "--untracked-files=all"], check=True,
                          capture_output=True, text=True).stdout


def build(out):
    p = subprocess.run([PY, TOOL, out], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-3000:]
    return p.stdout


def test_reference_build_is_deterministic_and_leaves_the_tree_clean():
    before = git_status()
    tmp = tempfile.mkdtemp(prefix="shore-ref-")
    try:
        a, b = os.path.join(tmp, "a"), os.path.join(tmp, "b")
        build(a)
        build(b)
        names = sorted(os.listdir(a))
        assert names == sorted(os.listdir(b))
        assert names == ["conditions.json", "context.jpg", "fog.png", "golden.png", "keepout.png", "night.png",
                         "noon.png", "palette.json", "surfaces.json"], names
        for n in names:
            assert filecmp.cmp(os.path.join(a, n), os.path.join(b, n), shallow=False), n
        assert load_reference(a).digest == load_reference(b).digest
        assert git_status() == before, "building a reference set changed the working tree"
        # and it refuses to write one into the repository (outside the ignored out/)
        p = subprocess.run([PY, TOOL, os.path.join(ROOT, "reference-test")], capture_output=True, text=True)
        assert p.returncode != 0 and "refusing" in p.stderr and not os.path.exists(os.path.join(ROOT, "reference-test"))
        check_set(a)
    finally:
        shutil.rmtree(tmp)


def check_set(path):
    """The shape of a reference set beyond what the kit itself checks."""
    ref = load_reference(path)
    assert (ref.frame_w, ref.frame_h, ref.cx, ref.cy) == (2880, 1800, 1600, 1150)
    assert [c.name for c in ref.conditions] == ["noon", "golden", "night", "fog"]
    keep = np.frombuffer(ref.keepout, np.uint8).reshape(ref.ch, ref.cw) > 0
    deck = np.frombuffer(bytes(ref.deck_mask), np.uint8).reshape(ref.ch, ref.cw) > 0
    at = lambda x, y: keep[y - ref.cy, x - ref.cx]
    # the moored boat, its mast, the lantern post and the left margin are kept out; the deck is mostly open
    assert at(2552, 1415) and at(2545, 1330) and at(2469, 1390) and at(1620, 1500)
    assert deck.sum() > 10000 and (deck & ~keep).sum() > 0.9 * deck.sum()
    # the dry band: most columns right of the pier's root have one, and most of it is open ground
    cols = [i for i in range(ref.rx1 - ref.rx0 + 1) if ref.dry_top[i] != -1]
    assert len(cols) > 1000, len(cols)
    open_px = sum((~keep[ref.dry_top[i] - ref.cy:ref.dry_bottom[i] + 1 - ref.cy, ref.rx0 + i - ref.cx]).sum() for i in cols)
    all_px = sum(ref.dry_bottom[i] - ref.dry_top[i] + 1 for i in cols)
    assert open_px > 0.75 * all_px, (open_px, all_px)
    # the lights: day brighter than golden hour brighter than night; fog veils, the others do not
    light = {c.name: sum(c.light) for c in ref.conditions}
    assert light["noon"] > light["golden"] > light["night"] > 0, light
    veil = {c.name: max(c.veil_alpha) for c in ref.conditions}
    assert veil["fog"] > 64 and veil["noon"] == veil["golden"] == veil["night"] == 0, veil
    for c in ref.conditions:
        for t in c.lut:
            assert list(t) == sorted(t), "a tone curve must not fall"
        assert 0 < c.shadow_alpha < 256 and c.shadow_rgb == (0, 0, 0)


def test_existing_set():
    path = os.environ.get("SHORE_REFERENCE")
    if path:
        check_set(path)


def main():
    pick = sys.argv[1:]
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f) and (not pick or n in pick)]
    failed = []
    for name, f in tests:
        t0 = time.time()
        try:
            f()
            print(f"ok    {name} ({time.time() - t0:.1f}s)", flush=True)
        except Exception:
            failed.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"{len(tests) - len(failed)}/{len(tests)} passed" + (": failed " + ", ".join(failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
