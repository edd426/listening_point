#!/usr/bin/env python3
"""Tests for the shore in the renderer (renderers/procedural/shore.py): objects, their shadows, the lamp.

usage: ./venv/bin/python tests/test_shore_render.py [test_name ...]      (from the repo root)

Offline and synthetic. Needs a reference set: SHORE_REFERENCE=DIR, else one is built for the run (half a
minute). The no-regression test renders full frames with the renderer as it was before the shore
(LP_BASELINE, a git revision, default shore/kit) and as it is now, and compares the files byte for byte;
it is skipped when that revision does not exist. The whole file takes a few minutes.
"""
import datetime as dt
import filecmp
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from types import SimpleNamespace

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "renderers", "procedural"))
sys.path.insert(1, os.path.join(ROOT, "tools"))
sys.path.insert(2, os.path.join(ROOT, "tests"))
sys.path.insert(3, ROOT)
import listening_point as lp  # noqa: E402
import shore as shore_mod  # noqa: E402
import shore_reference as sr  # noqa: E402
import shore_support as S  # noqa: E402
from core import MOORED, Layer  # noqa: E402
from day import Day  # noqa: E402
from shorekit.compose import compose  # noqa: E402
from shorekit.rules import draw_order, paint  # noqa: E402

D = dt.date
PY = sys.executable
RENDERER = os.path.join(ROOT, "renderers", "procedural", "listening_point.py")
TMP = tempfile.mkdtemp(prefix="shore-render-")
MEAN_MAX, P99_MAX = 3, 12        # BUILD section 2: colour inside the footprint at the reference conditions


def fixture_cache(name="fixtures", veto=None):
    """A shore cache holding the four fixture objects (optionally with a veto event after them)."""
    ref = S.reference()
    shore = S.new_shore(ref)
    S.fixtures(shore, ref)
    if veto:
        shore.veto(veto, "2027-03-21T12:00:00Z")      # 13:00 in Budapest
    return S.write_cache(os.path.join(TMP, name), S.reference_dir(), shore), shore


# ------------------------------------------------------------- no regression --
def baseline_renderer():
    rev = os.environ.get("LP_BASELINE", "shore/kit")
    if subprocess.run(["git", "-C", ROOT, "rev-parse", "--verify", "-q", rev + "^{commit}"], capture_output=True).returncode:
        return None, rev
    dst = os.path.join(TMP, "baseline")
    if not os.path.isdir(dst):
        os.makedirs(dst)
        arch = subprocess.run(["git", "-C", ROOT, "archive", rev, "renderers"], check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", dst], input=arch, check=True)
    return os.path.join(dst, "renderers", "procedural", "listening_point.py"), rev


def render_files(renderer, out, date, sel, extra=()):
    os.makedirs(out, exist_ok=True)
    cmd = [PY, renderer, out, "--date", date, *sel, "--scale", "0.75", "--jobs", "1", "--weather", "fair",
           "--cache", os.path.join(TMP, "wx"), *extra]
    p = subprocess.run(cmd, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-3000:]
    return sorted(f for f in os.listdir(out) if f.endswith(".jpg"))


def test_no_shore_and_empty_shore_are_byte_identical_to_the_renderer_before():
    base, rev = baseline_renderer()
    if base is None:
        print(f"      skipped: no revision {rev} (set LP_BASELINE)")
        return
    ref_dir = S.reference_dir()
    empty = S.write_cache(os.path.join(TMP, "empty"), ref_dir, S.new_shore(S.reference()))
    # objects that land only after the day, and a lamp lit on another day: nothing to draw either
    later = S.new_shore(S.reference())
    m, _ = S.place_first(later, lambda x, y: S.manifest("2027-03-17-cairn", "maker-a", S.CAIRN, S.STONES, "shingle",
                                                        x, y), S.dry_spots(S.reference(), 2400, 2800))
    later.accept(m, "2027-03-18T04:30:00Z", "2027-03-18T04:30:00Z", "world-1", "0" * 40)
    later = S.write_cache(os.path.join(TMP, "later"), ref_dir, later)
    lamp = os.path.join(TMP, "lamp-other-day.json")
    with open(lamp, "w") as f:
        json.dump({"version": 1, "lit": {"2027-03-16": "2027-03-16T19:04:11+01:00"}}, f)
    variants = {"none": [], "empty": ["--shore", empty], "later": ["--shore", later, "--lamp", lamp]}
    # 2027-03-17: the heron at dawn, the gulls on the pier and a thing washed up at 10:00, the lamps at night
    # (21:21 and 21:22 are cross-faded between two keyframes, as a day's render makes them)
    for sel in (["--times", "06:00,10:00"], ["--minutes", "1281-1282"]):
        tag = sel[1].replace(",", "_")
        want = render_files(base, os.path.join(TMP, "base", tag), "2027-03-17", sel)
        assert len(want) == 2, want
        for name, extra in variants.items():
            got = render_files(RENDERER, os.path.join(TMP, name, tag), "2027-03-17", sel, extra)
            assert got == want, (name, got)
            for f in want:
                assert filecmp.cmp(os.path.join(TMP, "base", tag, f), os.path.join(TMP, name, tag, f), shallow=False), \
                    f"{name} {f} differs from {rev}"


# ------------------------------------------------------------- kit agreement --
def kit_footprint(ref, objs):
    """The kit's footprint of these objects: every pixel an object owns or a shadow is shown on."""
    order = draw_order(objs)
    owner, drawn = paint(order, ref.cw * ref.ch)
    mask = np.frombuffer(owner.tobytes(), np.uint16).reshape(ref.ch, ref.cw) > 0
    for ds in drawn:
        for i in ds:
            if owner[i] == 0:
                mask[i // ref.cw, i % ref.cw] = True
    return mask


def test_frames_agree_with_the_kit_at_the_reference_conditions():
    ref = S.reference()
    cache, shore = fixture_cache()
    objs = list(shore.live)
    want_mask = kit_footprint(ref, objs)
    report = []
    for cond in ref.conditions:
        name, hhmm, kind = next(c for c in sr.CONDITIONS if c[0] == cond.name)
        m = sr.minute(hhmm)
        day = Day(sr.DATE, weather=kind, reference=True, shore=cache)
        st = day.shore.at(m)
        assert st is not None and set(st["ids"]) == {o.id for o in objs}, cond.name
        got_mask = np.zeros_like(want_mask)
        got_mask[st["sy"] - ref.cy, st["sx"] - ref.cx] = True
        got_mask[st["hy"] - ref.cy, st["hx"] - ref.cx] = True
        assert np.array_equal(got_mask, want_mask), (cond.name, "footprint", int((got_mask ^ want_mask).sum()))
        img = sr.crop(sr.render(day, m)).astype(int)
        bare = np.frombuffer(ref.crop(cond.name), np.uint8).reshape(ref.ch, ref.cw, 3).astype(int)
        kit = np.frombuffer(bytes(compose(ref, objs, cond)), np.uint8).reshape(ref.ch, ref.cw, 3).astype(int)
        # nothing outside the footprint changes; inside, the colour is the kit's within tolerance
        assert np.array_equal(img[~want_mask], bare[~want_mask]), (cond.name, "pixels outside the footprint changed")
        d = np.abs(img[want_mask] - kit[want_mask]).ravel()
        mean, p99 = d.mean(), np.percentile(d, 99)
        report.append(f"{cond.name} mean {mean:.2f} p99 {p99:.1f} max {d.max()}")
        assert mean <= MEAN_MAX and p99 <= P99_MAX, report[-1]
        # and the objects really are drawn: inside the footprint the frame is not the bare crop
        assert (np.abs(img[want_mask] - bare[want_mask]).sum(-1) > 0).mean() > 0.9, cond.name
    print("      " + "; ".join(report))


# ------------------------------------------------------------- the timeline --
def test_objects_show_from_landing_until_the_sea_takes_them():
    P = lambda oid, on="shingle": SimpleNamespace(id=oid, on=on)
    adds = {"a": ("2027-03-18T04:30:00Z", P("a")), "b": ("2027-03-19T04:30:00Z", P("b", on="a")),
            "c": ("2027-03-19T04:30:00Z", P("c")), "d": ("2027-03-20T04:30:00Z", P("d", on="c"))}
    gone = {"a": "2027-03-20T04:30:00Z", "b": "2027-03-20T04:30:00Z"}       # a storm took a, and b with it
    ids = lambda t: [p.id for p in shore_mod.on_show(adds, gone, t)]
    assert ids("2027-03-18T04:29:59Z") == []
    assert ids("2027-03-18T04:30:00Z") == ["a"]
    assert ids("2027-03-19T12:00:00Z") == ["a", "b", "c"]
    assert ids("2027-03-20T04:30:00Z") == ["c", "d"]
    # a thing built onto something that is not (yet) there does not float
    assert [p.id for p in shore_mod.on_show({"x": ("2027-01-01T00:00:00Z", P("x", on="y"))}, {}, "2027-02-01T00:00:00Z")] == []
    # through a real cache: the day's minutes before the last landing show three objects, after it four;
    # a veto takes the cairn and the flag on it from 13:00 local (12:00 UTC)
    cache, shore = fixture_cache("vetoed", veto="2027-03-18-cairn")
    day = Day(D(2027, 3, 21), weather="clear", shore=cache)
    st = lambda hhmm: set(day.shore.at(sr.minute(hhmm))["ids"])
    assert st("12:59") == {"2027-03-18-cairn", "2027-03-19-flag", "2027-03-18-post", "2027-03-19-log"}
    assert st("13:00") == {"2027-03-18-post", "2027-03-19-log"}
    day = Day(D(2027, 3, 19), weather="clear", shore=cache)
    assert set(day.shore.at(sr.minute("05:29"))["ids"]) == {"2027-03-18-cairn", "2027-03-18-post"}
    assert len(day.shore.at(sr.minute("05:31"))["ids"]) == 4
    assert day.shore.at(0)["ids"] == ("2027-03-18-cairn", "2027-03-18-post")
    # a cache the kit refuses draws nothing (and says so) instead of stopping the render
    bad = os.path.join(TMP, "bad")
    shutil.copytree(cache, bad, symlinks=True)
    obj = os.path.join(bad, "objects", "2027-03-19-log.json")
    with open(obj, "rb") as f:
        data = f.read()
    with open(obj, "wb") as f:
        f.write(data.replace(b"[150,140,116]", b"[150,140,117]"))      # no longer the object the ledger names
    assert Day(D(2027, 3, 21), weather="clear", shore=bad).shore is None


def test_resting_things_are_hidden_by_objects_standing_nearer():
    cache, shore = fixture_cache("allow")
    day = Day(D(2027, 3, 21), weather="clear", shore=cache)
    fr = lp.Frame(day, 720, 0.75)
    cairn = shore.byid["2027-03-18-cairn"]
    ref = S.reference()
    x0, y0, x1, y1 = cairn.bbox
    L = Layer(fr, ref.cx + x0 - 5, ref.cy + y0 - 5, ref.cx + x1 + 6, ref.cy + y1 + 6)
    allow = fr.shore_allow(L, cairn.ground_y - 20)        # something resting farther back
    assert allow is not None and allow.min() == 0 and allow.max() == 1
    for i in cairn.solid:
        assert allow[i // ref.cw + ref.cy - L.y0, i % ref.cw + ref.cx - L.x0] == 0
    assert fr.shore_allow(L, cairn.ground_y + 5) is None  # something nearer than the cairn shows in front
    assert lp.Frame(Day(D(2027, 3, 21), weather="clear"), 720, 0.75).shore_allow(L, 0) is None


# ------------------------------------------------------------------ the lamp --
def write_lamp(lit):
    path = os.path.join(TMP, "lamp-%d.json" % len(os.listdir(TMP)))
    with open(path, "w") as f:
        json.dump({"version": 1, "lit": lit}, f)
    return path


def test_lamp_state_file():
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Budapest")
    p = write_lamp({"2027-03-21": "2027-03-21T21:00:00+01:00", "2027-03-22": "not a time"})
    assert shore_mod.lamp_lit(p, D(2027, 3, 21), tz) == dt.datetime(2027, 3, 21, 21, 0, tzinfo=tz)
    assert shore_mod.lamp_lit(p, D(2027, 3, 22), tz) == dt.datetime(2027, 3, 22, 0, 0, tzinfo=tz)   # lit, time unreadable
    assert shore_mod.lamp_lit(p, D(2027, 3, 20), tz) is None
    assert shore_mod.lamp_lit(os.path.join(TMP, "missing.json"), D(2027, 3, 21), tz) is None
    bad = os.path.join(TMP, "lamp-bad.json")
    for body in ('{"version": 2, "lit": {"2027-03-21": "x"}}', "not json", '{"version": 1}', "[]"):
        with open(bad, "w") as f:
            f.write(body)
        assert shore_mod.lamp_lit(bad, D(2027, 3, 21), tz) is None, body


def small(day, m):
    lp.init_worker(day, 0.25, 1, None)
    return np.asarray(lp.frame_image(m), np.int32)


def test_the_lamp_lights_the_boat_window_from_dusk_on_a_lit_day():
    date = D(2027, 3, 21)
    lit = write_lamp({"2027-03-21": "2027-03-21T21:00:00+01:00"})
    plain = lambda m: small(Day(date, weather="clear"), m)
    lamp = lambda m: small(Day(date, weather="clear", lamp=lit), m)
    # by day, and in the dark before the moment it was lit, nothing changes
    assert np.array_equal(plain(720), lamp(720))
    assert np.array_equal(plain(sr.minute("20:50")), lamp(sr.minute("20:50")))
    a, b = plain(sr.minute("21:30")), lamp(sr.minute("21:30"))
    diff = np.abs(a - b).sum(-1)
    assert diff.max() > 30
    ys, xs = np.nonzero(diff > 2)
    bx, by = MOORED[0] * a.shape[1], MOORED[1] * a.shape[0]
    assert abs(xs.mean() - bx) < 40 and xs.min() > bx - 80 and xs.max() < bx + 80, (xs.min(), xs.max(), bx)
    assert ys.min() > by - 60, (ys.min(), by)                   # the window, its glow, and its reflection below
    fr = lp.Frame(Day(date, weather="clear", lamp=lit), sr.minute("21:30"), 0.25)
    wx, wy = fr.window_xy(MOORED[0] * fr.W, MOORED[1] * fr.H, 170 * fr.s)[0]
    px = b[int(wy), int(wx)]
    assert px[0] > px[2] + 40, px                              # warm
    # the boat is always moored from dusk: every sailing trip is home before the lamps come on
    for k in range(0, 200, 9):
        day = Day(D(2027, 4, 15) + dt.timedelta(k), weather="fair")
        if day.events.trip:
            dusk = next(m for m in range(720, 1440) if day.sun_alt[m] < 2)
            assert day.events.trip[1] * 60 < dusk, (day.date, day.events.trip, dusk)


def main():
    pick = sys.argv[1:]
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f) and (not pick or n in pick)]
    failed = []
    try:
        for name, f in tests:
            t0 = time.time()
            try:
                f()
                print(f"ok    {name} ({time.time() - t0:.1f}s)", flush=True)
            except Exception:
                failed.append(name)
                print(f"FAIL  {name}")
                traceback.print_exc()
    finally:
        shutil.rmtree(TMP, True)
    print(f"{len(tests) - len(failed)}/{len(tests)} passed" + (": failed " + ", ".join(failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
