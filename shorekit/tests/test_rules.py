"""Rules 1-6 against the synthetic reference, and add-never-erase held to an independent painter."""
import unittest
from fractions import Fraction

import support as S
from shorekit.geometry import place
from shorekit.manifest import manifest_from_obj
from shorekit.rules import check_local, evaluate, occlusion, redmean512


def man(obj):
    return manifest_from_obj(obj)


def codes(errs):
    return [e.code for e in errs]


def ev(obj, live=(), seq=1):
    return evaluate(man(obj), S.reference(), list(live), seq)


def placed(obj, seq, support=None):
    return place(man(obj), S.reference(), support, seq)


class TestLocalRules(unittest.TestCase):
    def test_fixtures_pass_alone(self):
        for n in ("2026-11-02-cairn", "2026-11-02-flag", "2026-11-03-log", "2026-11-04-bottle"):
            errs, p = ev(S.fixture_obj(n))
            self.assertEqual(errs, [], n)
            self.assertTrue(p.solid)

    def test_size(self):
        small = S.make_object("2026-11-05-a", "maker-a", S.block(5, 3), S.STONE, "shingle", 2640, 1665)
        self.assertEqual([e.line() for e in ev(small)[0]], ["E_SIZE 15 opaque cells, need 16-2500"])
        big = S.make_object("2026-11-05-a", "maker-a", S.block(51, 50), S.STONE, "shingle", 2640, 1665)
        self.assertEqual(codes(ev(big)[0])[0], "E_SIZE")
        tall = S.make_object("2026-11-05-a", "maker-a", S.block(1, 30), S.STONE, "shingle", 1800, 1388, scale=2)
        self.assertEqual([e.line() for e in ev(tall)[0]], ["E_SIZE 60 px tall standing at y=1388, max 58 there"])

    def test_size_floor(self):
        """Look B: a thing standing on the shingle or the pier averages at least min_h across its width
        and height; one built onto another may be smaller. (The synthetic set's own floor is kept low for
        the old fixtures, so this raises it to 20 px.)"""
        from shorekit.reference import load_reference
        self.assertEqual(S.reference().height_min(1665), 3)
        ref = load_reference(S.reference_dir())
        ref.min_h = [20] * len(ref.min_h)

        def judge(obj, live=(), seq=1):
            return [e.line() for e in evaluate(man(obj), ref, list(live), seq)[0]]
        small = S.make_object("2026-11-05-a", "maker-a", S.block(10, 10), S.STONE, "shingle", 2640, 1665)
        self.assertEqual(judge(small), ["E_SIZE 10x10 px standing at y=1665: its sides average 10 px, min 20 there"
                                        " (too small to notice)"])
        small["scale"] = 2
        self.assertEqual(judge(small), [])
        log = S.make_object("2026-11-05-a", "maker-a", S.block(34, 6), S.STONE, "shingle", 2600, 1665)
        self.assertEqual(judge(log), [])                       # long and low: 34 + 6 = 2 x 20
        log["rows"] = S.block(33, 6)
        self.assertEqual(len(judge(log)), 1)
        pole = S.make_object("2026-11-05-a", "maker-a", S.block(2, 38), S.STONE, "shingle", 2640, 1665)
        self.assertEqual(judge(pole), [])
        cairn = placed(S.fixture_obj("2026-11-02-cairn"), 1)
        chip = S.make_object("2026-11-05-a", "maker-a", S.block(8, 2), S.STONE, "2026-11-02-cairn", 2602, 1637,
                             anchor=(3, 1))
        self.assertEqual(judge(chip, [cairn], 2), [])

    def test_scale_up_to_four(self):
        big = S.make_object("2026-11-05-a", "maker-a", S.block(5, 5), S.STONE, "shingle", 2640, 1665, scale=4)
        errs, p = ev(big)
        self.assertEqual(errs, [])
        self.assertEqual((p.right - p.left + 1, p.foot_y - p.top + 1), (20, 20))

    def test_faces(self):
        from shorekit.geometry import FACE_EAST, FACE_FRONT, FACE_TOP, FACE_WEST, cell_face
        rows = ["..a..", ".aaa.", "aaaaa", "aa.aa", "a.a.a"]
        got = ["".join("FTEW"[cell_face(rows, c, r)] if ch != "." else "." for c, ch in enumerate(row))
               for r, row in enumerate(rows)]
        self.assertEqual((FACE_FRONT, FACE_TOP, FACE_EAST, FACE_WEST), (0, 1, 2, 3))
        # the viewer looks south: a cell open on its left faces east, open on its right faces west
        self.assertEqual(got, ["..T..", ".TFT.", "TFFFT", "EW.EW", "F.T.F"])

    def test_glow(self):
        lamp = {"a": (96, 80, 64), "g": (236, 186, 104)}
        rows = ["aaaa", "agga", "agga", "aaaa"]
        ok = S.make_object("2026-11-05-a", "maker-a", rows, lamp, "shingle", 2640, 1665, scale=4)
        ok["glow"] = "g"
        errs, p = ev(ok)
        self.assertEqual(errs, [])
        self.assertEqual(len(p.glow), 64)
        big = S.make_object("2026-11-05-a", "maker-a", ["aaaaa", "aggga", "aggga", "aaaaa"], lamp, "shingle", 2640,
                            1665, scale=3)
        big["glow"] = "g"
        self.assertEqual(ev(big)[0], [])              # 6 cells at scale 3: 54 px
        big["scale"] = 4
        self.assertEqual([e.line() for e in ev(big)[0]], ["E_GLOW glow 'g' lights 96 px, max 64"])
        grey = dict(ok, glow="a")
        self.assertEqual(codes(ev(grey)[0]), ["E_GLOW", "E_GLOW", "E_PALETTE"])   # and 'g' is now plain paint
        self.assertTrue(ev(grey)[0][0].text.startswith("glow 'a' (96,80,64) is "))
        # without a glow key, the lamp colour is judged like any other and is too bright for the shore
        plain = S.make_object("2026-11-05-a", "maker-a", rows, lamp, "shingle", 2640, 1665, scale=4)
        self.assertEqual(codes(ev(plain)[0]), ["E_PALETTE"])

    def test_glow_lights_up_at_night_only(self):
        from shorekit.compose import compose
        ref = S.reference()
        unlit_obj = S.make_object("2026-11-05-a", "maker-a", ["aaaa", "agga", "agga", "aaaa"],
                                  {"a": (96, 80, 64), "g": (236, 186, 104)}, "shingle", 2640, 1665, scale=4)
        p = placed(dict(unlit_obj, glow="g"), 1)
        dark = placed(unlit_obj, 1)
        i = min(p.glow)
        night = next(c for c in ref.conditions if c.name == "night")
        noon = next(c for c in ref.conditions if c.name == "noon")
        lit, unlit = compose(ref, [p], night), compose(ref, [dark], night)       # the lamps are lit at night
        self.assertGreater(sum(lit[3 * i:3 * i + 3]), sum(unlit[3 * i:3 * i + 3]) + 150)
        self.assertEqual(compose(ref, [p], noon), compose(ref, [dark], noon))

    def test_palette(self):
        rock = (134, 130, 122)
        self.assertEqual(redmean512(rock, (134, 150, 122)), 2048 * 400)
        near = S.make_object("2026-11-05-a", "maker-a", S.block(4, 4), {"a": (134, 150, 122)}, "shingle", 2640, 1665)
        self.assertEqual(check_local(man(near), S.reference()), [])   # (grey on grey: rule 7 would refuse it placed)
        far = S.make_object("2026-11-05-a", "maker-a", S.block(4, 4), {"a": (134, 151, 122)}, "shingle", 2640, 1665)
        self.assertEqual([e.line() for e in ev(far)[0]],
                         ["E_PALETTE 'a' (134,151,122) is 42 from the nearest reference colour rock (134,130,122), max 40"])
        hot = S.make_object("2026-11-05-a", "maker-a", S.block(4, 4), {"a": (241, 236, 222)}, "shingle", 2640, 1665)
        self.assertEqual([e.line() for e in ev(hot)[0]], ["E_PALETTE 'a' (241,236,222) has a channel of 241, max 240"])
        green = S.make_object("2026-11-05-a", "maker-a", S.block(4, 4), {"a": (10, 200, 30)}, "shingle", 2640, 1665)
        self.assertEqual(codes(ev(green)[0]), ["E_PALETTE"])

    def test_stand_out(self):
        """Look C, rule 7 (E_FAINT): the body's mean lit colour stands at least FAINT_D from the ground
        around it (its box grown by FAINT_RING px, less its own pixels and shadow) at noon and at golden
        hour. Look B's grey stone on the grey shingle is refused; the same stone tarred or whitewashed
        passes; and a colour that holds at noon can still vanish in the evening light."""
        grey = S.make_object("2026-11-05-a", "maker-a", S.block(5, 5), {"a": (134, 130, 122)}, "shingle", 2640, 1665,
                             scale=4)
        self.assertEqual([e.line() for e in ev(grey)[0]],
                         ["E_FAINT at noon it averages (126,121,112) against (140,131,115) around it, 30 apart, min 48:"
                          " too like the ground to notice (first px at (2630,1646))"])
        for paint in ((34, 34, 38), (228, 226, 220)):
            grey["palette"] = {"a": list(paint)}
            self.assertEqual(ev(grey)[0], [], paint)
        glass = S.make_object("2026-11-05-a", "maker-a", S.block(6, 6), {"a": (170, 180, 190)}, "shingle", 2640, 1665)
        self.assertEqual([e.code for e in ev(glass)[0]], ["E_FAINT"])
        self.assertTrue(ev(glass)[0][0].line().startswith("E_FAINT at golden "))

    def test_region_and_keepout(self):
        up = S.make_object("2026-11-05-a", "maker-a", S.block(4, 64), S.STONE, "shingle", 1700, 1200, scale=2)
        lines = [e.line() for e in ev(up)[0]]
        self.assertEqual(lines[0], "E_REGION cell (0,0) at (1697,1073) is outside the shore (x 1640-2879, y 1150-1789)"
                                   " (and 615 more px)")
        heron = S.make_object("2026-11-05-a", "maker-a", S.block(6, 6), S.STONE, "shingle", 2714, 1670)
        self.assertEqual([e.line() for e in ev(heron)[0]],
                         ["E_REGION cell (0,0) at (2712,1665) is on keep-out (and 35 more px)"])
        boat = S.make_object("2026-11-05-a", "maker-a", S.block(4, 8), S.STONE, "pier", 2466, 1418)
        self.assertEqual([e.line() for e in ev(boat)[0]],
                         ["E_REGION cell (0,0) at (2465,1411) is on keep-out (and 31 more px)"])
        beside = S.make_object("2026-11-05-a", "maker-a", S.block(4, 8), S.STONE, "pier", 2460, 1418)
        self.assertEqual(ev(beside)[0], [])

    def test_resting(self):
        def at(x, y, on="shingle"):
            return [e.line() for e in ev(S.make_object("2026-11-05-a", "maker-a", S.block(4, 4), S.STONE, on, x, y))[0]]
        self.assertEqual(at(2311, 1623), ["E_REST foot cell (0,3) 2 px below dry band at x=2310 (and 3 more foot cells)"])
        self.assertEqual(at(2311, 1590), ["E_REST foot cell (0,3) 9 px above dry band at x=2310 (and 3 more foot cells)"])
        self.assertEqual(at(2311, 1621), [])
        self.assertEqual(at(1650, 1300), ["E_REST foot cell (0,3) has no dry band under it at x=1649 (and 3 more foot cells)"])
        self.assertEqual(at(2300, 1440, "pier"), ["E_REST foot cell (0,3) at (2299,1440) is off the deck (and 3 more foot cells)"])
        self.assertEqual(at(2300, 1460, "pier"), [])

    def test_plaque_must_rest_and_stay_clear(self):
        log = S.fixture_obj("2026-11-03-log")
        log["place"]["y"] = 1617
        self.assertEqual([e.line() for e in ev(log)[0]], ["E_REST label plaque foot 1 px above dry band at x=2419"])
        log = S.fixture_obj("2026-11-03-log")
        log["label"]["side"] = "left"
        self.assertEqual(codes(ev(log)[0]), ["E_REST"])

    def test_build_onto(self):
        cairn = placed(S.fixture_obj("2026-11-02-cairn"), 1)
        shell = S.fixture_obj("2026-11-03-shell")
        self.assertEqual(ev(shell, [cairn], 2)[0], [])
        shell["place"]["x"] = 2603
        self.assertEqual([e.line() for e in ev(shell, [cairn], 2)[0]],
                         ["E_REST only 1 of 4 foot px rest on 2026-11-02-cairn, need half"])
        shell["place"]["x"] = 2601
        self.assertEqual(ev(shell, [cairn], 2)[0], [])
        self.assertEqual([e.line() for e in ev(shell, [], 2)[0]],
                         ["E_ON there is no object 2026-11-02-cairn on the shore to build onto"])
        p = ev(S.fixture_obj("2026-11-03-shell"), [cairn], 2)[1]
        self.assertEqual((p.ground_y, p.shadow), (cairn.ground_y, ()))


# ------------------------------------------------------------- add never erase --
def naive(new, live):
    """An independent reading of rule 5 with dicts, sets and fractions."""
    def paint(objs):
        owner, drawn = {}, {}
        for o in sorted(objs, key=lambda o: (o.ground_y, o.seq)):
            drawn[o.id] = [i for i in o.shadow if i not in owner]
            for i in o.solid:
                owner[i] = o.id
        return owner, drawn
    ob, db = paint(live)
    oa, da = paint(list(live) + [new])
    out = set()
    for a in live:
        whole = len(a.solid) + len(db[a.id])
        before = {i for i in a.solid if ob.get(i) == a.id} | {i for i in db[a.id] if i not in ob}
        after = {i for i in a.solid if oa.get(i) == a.id} | {i for i in db[a.id] if i not in oa}
        lost = before - after
        if lost and Fraction(len(after), whole) < Fraction(60, 100):
            out.add(("keep", a.id))
        if lost and Fraction(len(lost), whole) > Fraction(25, 100):
            out.add(("take", a.id))
        if any(oa.get(i) != a.id for i in a.label):
            out.add(("label", a.id))
    whole = len(new.solid) + len(da[new.id])
    shown = {i for i in new.solid if oa.get(i) == new.id} | {i for i in da[new.id] if i not in oa}
    if Fraction(len(shown), whole) < Fraction(1, 2):
        out.add(("hidden", new.id))
    if any(oa.get(i) != new.id for i in new.label):
        out.add(("ownlabel", new.id))
    return out


def kit(new, live):
    out = set()
    for e in occlusion(new, live, S.reference()):
        t = e.text
        if e.code == "E_COVER" and t.startswith("would leave"):
            out.add(("keep", t.split()[2]))
        elif e.code == "E_COVER":
            out.add(("take", t.split()[3]))
        elif e.code == "E_LABEL_COVER" and t.startswith("covers"):
            out.add(("label", t.split()[4]))
        elif e.code == "E_LABEL_COVER":
            out.add(("ownlabel", new.id))
        elif e.code == "E_HIDDEN":
            out.add(("hidden", new.id))
    return out


A_X, A_FOOT = 2640, 1665


def wall(label=None):
    return S.make_object("2026-11-05-wall", "maker-a", S.block(40, 10), S.STONE, "shingle", A_X, A_FOOT, label=label,
                         side="left")


def cover(oid, n, left=0, foot=A_FOOT):
    """A bitmap that covers exactly n of the wall's pixels from its foot up, starting `left` columns in."""
    q, rem = divmod(n, 20)
    rows = (["a" * rem + "." * (20 - rem)] if rem else []) + ["a" * 20] * q
    return S.make_object(oid, "maker-b", rows, S.STONE, "shingle", A_X - 19 + left, foot, anchor=(0, len(rows) - 1))


class TestAddNeverErase(unittest.TestCase):
    def test_takes_at_most_a_quarter(self):
        a = placed(wall(), 1)
        whole = len(a.solid) + len(a.shadow)
        self.assertEqual(whole, 400 + 42 + 40)
        n = whole * 25 // 100
        ok = placed(cover("2026-11-05-b", n), 2)
        self.assertEqual(occlusion(ok, [a], S.reference()), [])
        over = placed(cover("2026-11-05-b", n + 1), 2)
        self.assertEqual([e.line() for e in occlusion(over, [a], S.reference())],
                         ["E_COVER takes 26% of 2026-11-05-wall (max 25%); first covered px at (2621,1659)"])

    def test_older_keeps_sixty_percent(self):
        a = placed(wall(), 1)
        whole = len(a.solid) + len(a.shadow)
        c = placed(cover("2026-11-05-c", 100), 2)
        self.assertEqual(occlusion(c, [a], S.reference()), [])
        keep_min = -(-60 * whole // 100)            # 290 of 482: 60.2%, while 289 would be 59.96%
        self.assertEqual(keep_min, 290)
        ok = placed(cover("2026-11-05-b", whole - 100 - keep_min, left=20), 3)
        self.assertEqual(occlusion(ok, [a, c], S.reference()), [])
        bad = placed(cover("2026-11-05-b", whole - 100 - keep_min + 1, left=20), 3)
        self.assertEqual([e.line() for e in occlusion(bad, [a, c], S.reference())],
                         ["E_COVER would leave 2026-11-05-wall 59% visible (needs 60%); first covered px at (2641,1661)"])

    def test_labels_are_never_covered(self):
        a = placed(wall("WALL"), 1)
        left = a.plaque[0]
        b = S.make_object("2026-11-05-b", "maker-b", S.block(4, 4), S.STONE, "shingle", left + 1, A_FOOT)
        self.assertEqual(kit(placed(b, 2), [a]), {("label", "2026-11-05-wall")})
        behind = S.make_object("2026-11-05-b", "maker-b", S.block(30, 30), S.STONE, "shingle", A_X - 40, A_FOOT - 2,
                               label="BEHIND", side="right")
        nb = placed(behind, 2)
        self.assertIn(("ownlabel", "2026-11-05-b"), kit(nb, [a]))

    def test_newcomer_shows_half(self):
        a = placed(wall(), 1)
        b = S.make_object("2026-11-05-b", "maker-b", S.block(10, 8), S.STONE, "shingle", A_X - 5, A_FOOT - 1)
        errs = occlusion(placed(b, 2), [a], S.reference())
        self.assertEqual([e.code for e in errs], ["E_HIDDEN"])
        self.assertIn("hidden by 2026-11-05-wall", errs[0].text)

    def test_sweep_agrees_with_an_independent_painter(self):
        a = placed(wall("WALL"), 1)
        c = placed(S.make_object("2026-11-05-c", "maker-c", S.block(6, 14), S.STONE, "shingle", A_X + 10, A_FOOT + 3), 2)
        seen = set()
        n = 0
        for w, h in ((8, 8), (14, 12), (24, 6)):
            for dy in (-3, -1, 0, 2, 6):
                for x in range(A_X - 70, A_X + 30, 3):
                    b = placed(S.make_object("2026-11-05-b", "maker-b", S.block(w, h), S.STONE, "shingle", x,
                                             A_FOOT + dy), 3)
                    got = kit(b, [a, c])
                    self.assertEqual(got, naive(b, [a, c]), (w, h, dy, x))
                    seen |= {k for k, _ in got}
                    n += 1
        self.assertGreater(n, 400)
        self.assertEqual(seen, {"keep", "take", "label", "hidden"})


if __name__ == "__main__":
    unittest.main()
