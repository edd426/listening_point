"""The cast shadow (kit 1.3.0): where it falls, that it is drawn and never judged, and the reference data
that says which way it falls. The rule is held to a second implementation written from SCHEMA.md 4.6, pixel
by pixel, and to the schema's own worked example."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import support as S
from shorekit import CAST_MAX_DX, CAST_MAX_DY
from shorekit.cli import main
from shorekit.compose import cast_shown, compose, plan, plan_sha256, sheet
from shorekit.errors import ShoreError
from shorekit.geometry import cast_pixels, place
from shorekit.ledger import Shore, ledger_sha256
from shorekit.manifest import manifest_from_obj
from shorekit.reference import load_reference, point_in_polygon
from shorekit.rules import draw_order, paint
from shorekit.strictjson import canonical

DXS = (-768, -511, -256, -37, 0, 1, 200, 768)
DYS = (-256, -100, 0, 55, 256)


def off(k, d):
    return (d * k + 128) >> 8


def xy(ref, i):
    return i % ref.cw + ref.cx, i // ref.cw + ref.cy


def swept(p, ref, dx, dy):
    """Every pixel the rule's sweep reaches, before anything is left out: {(x, y)} in frame pixels."""
    out = set()
    for i in p.solid:
        X, Y = xy(ref, i)
        h = p.foot_y - Y
        a, b = sorted((off(h, dx), off(h + 1, dx)))
        out.update((x, p.foot_y + 1 + off(h, dy)) for x in range(X + a, X + b + 1))
    return out


def rule(p, ref, dx, dy):
    """SCHEMA.md 4.6 pixel by pixel, written apart from the kit's own code: a set of crop indices."""
    if p.on not in ("shingle", "pier"):
        return set()
    out = set()
    for x, y in swept(p, ref, dx, dy):
        if not (ref.rx0 <= x <= ref.rx1 and ref.ry0 <= y <= ref.ry1):
            continue
        j = ref.index(x, y)
        if ref.keepout[j] or j in p.solid:
            continue
        if p.on == "shingle":
            band = ref.dry(x)
            if band is None or y < band[0]:
                continue
        elif not point_in_polygon(x, y, ref.deck):
            continue
        out.add(j)
    return out


def put(obj, ref=None, support=None, seq=1):
    return place(manifest_from_obj(obj), ref or S.reference(), support, seq)


def rod(x, y, w=2, h=8, oid="2026-11-05-rod", scale=1):
    """A plain upright w x h cells whose bottom-left pixel is (x, y)."""
    return S.make_object(oid, "maker-a", S.block(w, h), S.STONE, "shingle", x + scale // 2, y, anchor=(0, h - 1), scale=scale)


def open_spot(ref, reach, down, x_from=None):
    """A foot pixel (x, y) at the bottom of the dry band with open ground all round it: for `reach` columns to
    either side and `down` rows below, no keep-out, and every column's dry band begins at or above the foot."""
    for x in range((x_from or ref.rx0) + reach, ref.rx1 - reach, 7):
        band = ref.dry(x)
        if band is None or band[1] + down > ref.ry1:
            continue
        y = band[1]
        ok = True
        for X in range(x - reach, x + reach + 1):
            b = ref.dry(X)
            if b is None or b[0] > y or any(ref.keepout[ref.index(X, Y)] for Y in range(y - 1, y + down + 1)):
                ok = False
                break
        if ok:
            return x, y
    raise AssertionError("the synthetic shore has no open spot %d wide" % (2 * reach + 1))


def connected(pts):
    """True if the pixels are one piece, stepping only up, down, left and right."""
    pts = set(pts)
    todo = [next(iter(pts))]
    seen = set(todo)
    while todo:
        x, y = todo.pop()
        for q in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if q in pts and q not in seen:
                seen.add(q)
                todo.append(q)
    return len(seen) == len(pts)


class TestCastGeometry(unittest.TestCase):
    def setUp(self):
        self.ref = S.reference()

    def frame(self, cast):
        return set(xy(self.ref, i) for i in cast)

    def test_the_schema_s_worked_example(self):
        """SCHEMA.md 4.6: an upright 2 px wide and 8 px tall, dx 384 (1.5 px a px), dy 64 (a quarter)."""
        ref = self.ref
        x, y = open_spot(ref, 20, 6)
        p = put(rod(x, y))
        self.assertEqual((p.left, p.right, p.top, p.foot_y), (x, x + 1, y - 7, y))
        self.assertEqual([off(h, 384) for h in range(9)], [0, 2, 3, 5, 6, 8, 9, 11, 12])
        self.assertEqual([off(h, 64) for h in range(8)], [0, 0, 1, 1, 1, 1, 2, 2])
        want = ([(X, y + 1) for X in range(x, x + 5)] + [(X, y + 2) for X in range(x + 3, x + 11)]
                + [(X, y + 3) for X in range(x + 9, x + 14)])
        got = cast_pixels(p, ref, 384, 64)
        self.assertEqual(sorted(self.frame(got)), sorted(want))
        self.assertEqual(len(got), 18)

    def test_it_is_the_rule_pixel_by_pixel(self):
        ref = self.ref
        cairn = put(S.fixture_obj("2026-11-02-cairn"))
        things = [cairn, put(S.fixture_obj("2026-11-02-flag")), put(S.fixture_obj("2026-11-03-log")),
                  put(S.fixture_obj("2026-11-04-bottle")), put(S.fixture_obj("2026-11-03-shell"), support=cairn),
                  put(rod(2860, ref.dry(2860)[1], 6, 30)), put(rod(1700, ref.dry(1700)[0], 5, 9))]
        self.assertEqual([len(p.label) > 0 for p in things].count(True), 1)      # the log's label board casts too
        n = 0
        for p in things:
            for dx in DXS:
                for dy in DYS:
                    got = cast_pixels(p, ref, dx, dy)
                    self.assertEqual(list(got), sorted(rule(p, ref, dx, dy)), (p.id, dx, dy))
                    self.assertEqual(len(set(got)), len(got))
                    self.assertFalse(set(got) & set(p.solid), (p.id, dx, dy))    # never on its own pixels
                    for i in got:
                        X, Y = xy(ref, i)
                        self.assertTrue(ref.in_region(X, Y) and not ref.keepout[i])
                    n += len(got)
        self.assertGreater(n, 20000)

    def test_it_falls_away_from_the_light_and_as_far_as_the_thing_is_tall(self):
        ref = self.ref
        H = 30
        x, y = open_spot(ref, 3 * H + 6, H + 2)
        p = put(rod(x, y, 2, H))
        for dx in (0, 1, 90, 256, 500, 768):
            for dy in (0, 40, 128, 256):
                right = self.frame(cast_pixels(p, ref, dx, dy))
                left = self.frame(cast_pixels(p, ref, -dx, dy))
                self.assertEqual(right, swept(p, ref, dx, dy))                   # open ground: nothing left out
                xs, ys = [q[0] for q in right], [q[1] for q in right]
                # a light on the left (the east, in the morning) lays the shadow to the right, and the other way round
                self.assertEqual((min(xs), max(xs)), (p.left, p.right + off(H, dx)), (dx, dy))
                self.assertEqual((min(q[0] for q in left), max(q[0] for q in left)), (p.left + off(H, -dx), p.right))
                # it starts on the row under the foot and runs down the frame as far as dy carries the top pixel
                self.assertEqual((min(ys), max(ys)), (y + 1, y + 1 + off(H - 1, dy)), (dx, dy))
        # a light in front of the viewer and low enough to see: longer shadows from a lower light
        reach = [max(q[0] for q in self.frame(cast_pixels(p, ref, dx, 80))) for dx in range(0, 769, 64)]
        self.assertEqual(reach, sorted(reach))
        self.assertEqual(reach[-1] - reach[0], 3 * H)
        # from behind the viewer the shadow runs up the frame, behind the thing, and shows only beside it
        back = self.frame(cast_pixels(p, ref, 300, -100))
        self.assertTrue(back and min(q[1] for q in back) == y + 1 + off(H - 1, -100) < y)
        self.assertFalse(back & set(xy(ref, i) for i in p.solid))

    def test_no_holes(self):
        """A rod one pixel wide leaves one unbroken shadow whatever the direction; a block leaves no gaps in any row."""
        ref = self.ref
        H = 40
        x, y = open_spot(ref, 3 * H + 6, H + 2)
        thin = put(rod(x, y, 1, H))
        block = put(rod(x, y, 12, 12, "2026-11-05-block"))
        for dx in range(-CAST_MAX_DX, CAST_MAX_DX + 1, 32):
            for dy in (0, 1, 64, 127, 128, 200, CAST_MAX_DY):
                got = self.frame(cast_pixels(thin, ref, dx, dy))
                self.assertEqual(got, swept(thin, ref, dx, dy))
                self.assertTrue(connected(got), (dx, dy))
                rows = sorted(set(q[1] for q in got))
                self.assertEqual(rows, list(range(rows[0], rows[-1] + 1)), (dx, dy))
                got = self.frame(cast_pixels(block, ref, dx, dy))
                for r in set(q[1] for q in got):
                    xs = sorted(q[0] for q in got if q[1] == r)
                    self.assertEqual(xs, list(range(xs[0], xs[-1] + 1)), (dx, dy, r))
        # and behind the thing, the shadow and the thing together are still one piece
        for dx in range(-CAST_MAX_DX, CAST_MAX_DX + 1, 96):
            for dy in (-1, -90, -CAST_MAX_DY):
                got = swept(thin, ref, dx, dy)
                self.assertTrue(connected(got), (dx, dy))

    def test_keep_out_and_the_edge_of_the_shore(self):
        ref = self.ref
        # the heron's lane (keep-out columns 2700-2729) lies across this shadow: it falls on both sides, never on it
        p = put(rod(2689, 1670, 4, 20))
        self.assertEqual(put(rod(2689, 1670, 4, 20)).region_errors, [])
        got = self.frame(cast_pixels(p, ref, 768, 30))
        raw = swept(p, ref, 768, 30)
        self.assertTrue(any(ref.keepout[ref.index(*q)] for q in raw))
        self.assertTrue(any(q[0] < 2700 for q in got) and any(q[0] > 2729 for q in got))
        self.assertFalse(any(2700 <= q[0] <= 2729 for q in got))
        # at the right edge of the shore the shadow stops with the region
        x = ref.rx1 - 9
        p = put(rod(x, ref.dry(x)[1], 4, 20))
        got = self.frame(cast_pixels(p, ref, 768, 30))
        self.assertEqual(max(q[0] for q in got), ref.rx1)
        self.assertGreater(max(q[0] for q in swept(p, ref, 768, 30)), ref.rx1)

    def test_shingle_shadows_stay_off_the_tidal_band(self):
        """Like the contact shadow: nothing seaward of the dry band's top; the grass below the band is ground."""
        ref = self.ref
        x, y = open_spot(ref, 100, 40)
        top = ref.dry(x)[0]
        p = put(rod(x, top + 2, 4, 24))                   # standing near the band's top edge
        got = self.frame(cast_pixels(p, ref, 300, -256))
        raw = swept(p, ref, 300, -256)
        self.assertTrue(any(q[1] < ref.dry(q[0])[0] for q in raw))
        self.assertTrue(got)
        self.assertTrue(all(q[1] >= ref.dry(q[0])[0] for q in got))
        p = put(rod(x, y, 4, 24))                         # at the band's lower edge, the light in front
        got = self.frame(cast_pixels(p, ref, 0, 256))
        self.assertTrue(any(q[1] > ref.dry(q[0])[1] for q in got))

    def test_pier_shadows_stay_on_the_deck(self):
        ref = self.ref
        flag = put(S.fixture_obj("2026-11-02-flag"))
        self.assertEqual(flag.surface, "pier")
        for dx, dy in ((200, 100), (300, -200), (-500, -120)):
            got = cast_pixels(flag, ref, dx, dy)
            self.assertTrue(got, (dx, dy))
            self.assertTrue(all(ref.deck_mask[i] for i in got), (dx, dy))
            # the sweep also reaches open water beyond the deck's far edge, which is not keep-out: only the deck stops it
            beyond = [q for q in swept(flag, ref, dx, dy) if ref.in_region(*q) and not ref.keepout[ref.index(*q)]
                      and ref.index(*q) not in flag.solid and not ref.deck_mask[ref.index(*q)]]
            if dy < 0:
                self.assertTrue(beyond, (dx, dy))

    def test_a_thing_built_onto_another_casts_none(self):
        ref = self.ref
        cairn = put(S.fixture_obj("2026-11-02-cairn"))
        shell = put(S.fixture_obj("2026-11-03-shell"), support=cairn, seq=2)
        self.assertEqual(shell.shadow, ())                # as with the contact shadow
        for dx in DXS:
            self.assertEqual(cast_pixels(shell, ref, dx, 80), ())
        self.assertTrue(cast_pixels(cairn, ref, 200, 80))

    def test_direction_limits(self):
        p = put(S.fixture_obj("2026-11-02-cairn"))
        for dx, dy in ((CAST_MAX_DX + 1, 0), (-CAST_MAX_DX - 1, 0), (0, CAST_MAX_DY + 1), (0, -CAST_MAX_DY - 1)):
            with self.assertRaises(ValueError):
                cast_pixels(p, self.ref, dx, dy)
        self.assertEqual((CAST_MAX_DX, CAST_MAX_DY), (768, 256))
        cast_pixels(p, self.ref, CAST_MAX_DX, -CAST_MAX_DY)


def landed(ref):
    """The golden scenario's five objects on `ref`."""
    shore = Shore(ref)
    for oid in ("2026-11-02-cairn", "2026-11-02-flag", "2026-11-03-shell", "2026-11-03-log", "2026-11-04-bottle"):
        at = oid[:10] + "T04:30:00Z"
        shore.accept(manifest_from_obj(S.fixture_obj(oid)), at, at, "world-1", "0" * 40)
    return shore


class TestCastDrawn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old, cls.new = S.reference(), S.reference_cast()
        cls.a, cls.b = landed(cls.old), landed(cls.new)

    def test_a_set_without_cast_draws_none(self):
        self.assertEqual(self.old.conditions_version, 1)
        self.assertEqual([(c.cast_dx, c.cast_dy, c.cast_alpha) for c in self.old.conditions], [(0, 0, 0)] * 4)
        # and a condition whose alpha is 0 (fog) is drawn exactly as a set without cast draws it
        fog_old, fog_new = self.old.conditions[3], self.new.conditions[3]
        self.assertEqual((fog_new.name, fog_new.cast_alpha), ("fog", 0))
        self.assertEqual(compose(self.old, self.a.live, fog_old), compose(self.new, self.b.live, fog_new))

    def test_only_ground_in_shadow_changes_and_by_the_formula(self):
        old, new = self.old, self.new
        owner, drawn = paint(draw_order(self.b.live), new.cw * new.ch)
        contact = set(i for ds in drawn for i in ds if owner[i] == 0)
        for co, cn in zip(old.conditions[:3], new.conditions[:3]):
            before, after = compose(old, self.a.live, co), compose(new, self.b.live, cn)
            crop = new.crop(cn.name)
            cast = cast_shown(new, self.b.live, cn.cast_dx, cn.cast_dy)
            self.assertGreater(len(cast), 150, cn.name)
            self.assertEqual(cast, sorted(set(cast)))
            changed = [i for i in range(new.cw * new.ch) if before[3 * i:3 * i + 3] != after[3 * i:3 * i + 3]]
            self.assertEqual(changed, cast, cn.name)
            self.assertFalse(any(owner[i] for i in cast))                 # never on an object
            both = 0
            for i in cast:
                want = [(crop[3 * i + c] * (256 - cn.cast_alpha)) >> 8 for c in range(3)]
                if i in contact:                                          # then the contact shadow over it
                    both += 1
                    want = [(want[c] * (256 - cn.shadow_alpha) + cn.shadow_rgb[c] * cn.shadow_alpha) >> 8 for c in range(3)]
                self.assertEqual(list(after[3 * i:3 * i + 3]), want, (cn.name, i))
            self.assertGreater(both, 0, cn.name)

    def test_shadows_that_meet_darken_once_and_none_falls_on_an_object(self):
        ref = self.new
        x, y = open_spot(ref, 110, 40)
        tall = put(rod(x, y, 3, 30, "2026-11-05-tall"), ref, seq=1)
        other = put(rod(x + 14, y, 3, 30, "2026-11-05-other"), ref, seq=2)
        wall = put(rod(x + 40, y + 5, 8, 12, "2026-11-05-wall"), ref, seq=3)       # standing a little nearer
        objs = [tall, other, wall]
        a, b = set(cast_pixels(tall, ref, 600, 40)), set(cast_pixels(other, ref, 600, 40))
        self.assertTrue(a & b)                                            # the two shadows overlap
        self.assertTrue(a & set(wall.solid))                              # and on its own the first would cross the wall
        shown = cast_shown(ref, objs, 600, 40)
        every = a | b | set(cast_pixels(wall, ref, 600, 40))
        self.assertEqual(set(shown), every - set(tall.solid) - set(other.solid) - set(wall.solid))
        self.assertEqual(cast_shown(ref, objs[::-1], 600, 40), shown)     # the order of the objects does not matter
        cond = ref.conditions[0]
        k = 256 - cond.cast_alpha
        cond.cast_dx, cond.cast_dy, saved = 600, 40, (cond.cast_dx, cond.cast_dy)
        try:
            out = compose(ref, objs, cond)
        finally:
            cond.cast_dx, cond.cast_dy = saved
        crop = ref.crop(cond.name)
        contact = set(tall.shadow) | set(other.shadow) | set(wall.shadow)
        i = min((a & b) - contact - set(wall.solid))
        self.assertEqual(list(out[3 * i:3 * i + 3]), [(crop[3 * i + c] * k) >> 8 for c in range(3)])
        plain = compose(self.old, [put(rod(x + 40, y + 5, 8, 12, "2026-11-05-wall"), self.old, seq=3)], self.old.conditions[0])
        for i in wall.solid:
            self.assertEqual(out[3 * i:3 * i + 3], plain[3 * i:3 * i + 3])

    def test_it_is_drawn_and_never_judged(self):
        """With and without cast shadows: the same footprints, the same plan, the same ledger, the same verdicts."""
        import test_golden
        old, new = self.old, self.new
        self.assertEqual(plan(old, self.a.live), plan(new, self.b.live))
        self.assertEqual(plan_sha256(old, self.a.live), plan_sha256(new, self.b.live))
        self.assertEqual(ledger_sha256(self.a.events), ledger_sha256(self.b.events))
        for p, q in zip(self.a.live, self.b.live):
            self.assertEqual((p.shadow, p.bbox, sorted(p.solid)), (q.shadow, q.bbox, sorted(q.solid)))
        for obj in test_golden.variants():
            m = manifest_from_obj(obj)
            va, vb = self.a.judge(m, obj["id"][:10]), self.b.judge(m, obj["id"][:10])
            self.assertEqual([e.line() for e in va[0]], [e.line() for e in vb[0]], m.id)
        self.assertNotEqual(sheet(old, self.a.live)[2], sheet(new, self.b.live)[2])     # though the picture differs
        self.assertNotEqual(old.digest, new.digest)

    def test_the_cli_says_the_same_and_draws_the_shadow(self):
        tmp = tempfile.mkdtemp(prefix="shorekit-cast-")
        self.addCleanup(shutil.rmtree, tmp)
        said = []
        for name, rd in (("old", S.reference_dir()), ("new", S.reference_dir_cast())):
            shore = S.new_shore(os.path.join(tmp, name), rd)
            lines = []
            for cmd in (["check"], ["preview", "--out", os.path.join(tmp, name, "pv")]):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    code = main(cmd + [os.path.join(S.FIXTURES, "objects", "2026-11-02-cairn.json"), "--shore", shore])
                self.assertEqual(code, 0)
                lines += [l.replace(os.path.join(tmp, name), "") for l in buf.getvalue().splitlines()]
            said.append(lines)
        old, new = said
        self.assertEqual(old[0], "PASS 2026-11-02-cairn: seq 1, draws 1 of 1, 208 solid px, 34 shadow px")
        self.assertEqual([l for l in old if l[:4] in ("PASS", "PLAN")], [l for l in new if l[:4] in ("PASS", "PLAN")])
        self.assertEqual(len([l for l in old if l.startswith("PLAN")]), 1)
        sheets = [[l for l in s if l.startswith("SHEET")][0] for s in said]
        self.assertNotEqual(sheets[0], sheets[1])


class TestCastReference(unittest.TestCase):
    def test_both_versions_load(self):
        old, new = S.reference(), S.reference_cast()
        self.assertEqual((old.conditions_version, new.conditions_version), (1, 2))
        self.assertEqual([(c.name, c.cast_dx, c.cast_dy, c.cast_alpha) for c in new.conditions],
                         [(n,) + S.CAST[n] for n in S.CONDITIONS])
        for c in old.conditions:
            self.assertEqual(old.crop(c.name), new.crop(c.name))
        self.assertEqual(old.keepout, new.keepout)

    def edited(self, f, src=None):
        d = tempfile.mkdtemp(prefix="shorekit-ref-cast-")
        self.addCleanup(shutil.rmtree, d)
        dst = os.path.join(d, "r1")
        shutil.copytree(src or S.reference_dir_cast(), dst)
        p = os.path.join(dst, "conditions.json")
        with open(p, "rb") as fh:
            o = json.loads(fh.read())
        o = f(o) or o
        with open(p, "wb") as fh:
            fh.write(o if type(o) is bytes else canonical(o))
        return load_reference(dst)

    def test_the_limits_are_allowed(self):
        ref = self.edited(lambda o: o["conditions"][0].update(cast={"dx": -768, "dy": 256, "alpha": 256}))
        self.assertEqual((ref.conditions[0].cast_dx, ref.conditions[0].cast_dy, ref.conditions[0].cast_alpha), (-768, 256, 256))
        ref = self.edited(lambda o: o["conditions"][1].update(cast={"dx": 768, "dy": -256, "alpha": 0}))
        self.assertEqual((ref.conditions[1].cast_dx, ref.conditions[1].cast_dy), (768, -256))

    def test_malformed_cast_is_refused(self):
        for name, f, src in cast_cases():
            with self.assertRaises(ShoreError, msg=name) as cm:
                self.edited(f, src)
            self.assertEqual(cm.exception.code, "E_REFDATA", name)


def cast_cases():
    """(name, edit of conditions.json, source set or None for the one with cast): each must be refused."""
    def cast(k, **kw):
        return lambda o: o["conditions"][k]["cast"].update(**kw)
    old = S.reference_dir()
    return [
        ("one condition lacks cast", lambda o: o["conditions"][2].pop("cast"), None),
        ("no condition has cast", lambda o: [c.pop("cast") for c in o["conditions"]] and None, None),
        ("cast in a set written as 1", lambda o: o.update(shore_conditions=1), None),
        ("cast on one condition of a set written as 1",
         lambda o: o["conditions"][0].update(cast={"dx": 0, "dy": 0, "alpha": 0}), old),
        ("a set written as 2 with no cast", lambda o: o.update(shore_conditions=2), old),
        ("version 3", lambda o: o.update(shore_conditions=3), None),
        ("version 0", lambda o: o.update(shore_conditions=0), None),
        ("version true", lambda o: o.update(shore_conditions=True), None),
        ("dx too far right", cast(0, dx=769), None),
        ("dx too far left", cast(0, dx=-769), None),
        ("dy too far down", cast(1, dy=257), None),
        ("dy too far up", cast(1, dy=-257), None),
        ("alpha over 256", cast(2, alpha=257), None),
        ("alpha negative", cast(2, alpha=-1), None),
        ("dx a string", cast(0, dx="12"), None),
        ("dy true", cast(0, dy=True), None),
        ("an extra key", cast(3, rgb=[0, 0, 0]), None),
        ("a missing key", lambda o: o["conditions"][3]["cast"].pop("alpha"), None),
        ("cast a list", lambda o: o["conditions"][0].update(cast=[2, 83, 87]), None),
        ("a fraction", lambda o: canonical(o).replace(b'"dx":24', b'"dx":24.5'), None),
    ]


if __name__ == "__main__":
    unittest.main()
