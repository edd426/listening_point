"""Golden values. CI runs these on x86_64 Linux and arm64 macOS under Python 3.9 and 3.12; the Mac
runs them again at install. Identical results everywhere are what "passes in the sandbox =>
looks right on the Mac" rests on: the verdicts and their messages, every footprint pixel, the
draw order and who covers whom, the label glyphs, and the preview's decoded pixels.

To re-pin after a deliberate change: python3 shorekit/tests/test_golden.py --print
"""
import hashlib
import os
import sys

import support as S
from shorekit.compose import pixels_sha256, plan, plan_sha256, sheet, zoom
from shorekit.font import plaque_cells
from shorekit.ledger import Shore, ledger_sha256
from shorekit.manifest import manifest_from_obj
from shorekit.png import read_reference_png

import unittest

DAYS = {"2026-11-02": "2026-11-02T04:30:00Z", "2026-11-03": "2026-11-03T04:30:00Z", "2026-11-04": "2026-11-04T04:30:00Z"}
LANDED = [("2026-11-02-cairn", "world-1"), ("2026-11-02-flag", "world-2"), ("2026-11-03-shell", "world-1"),
          ("2026-11-03-log", "world-2"), ("2026-11-04-bottle", "world-1")]


def variants():
    st = S.STONE
    out = [
        S.make_object("2026-11-05-lean", "maker-c", S.block(12, 12), st, "shingle", 2598, 1660),
        S.make_object("2026-11-05-hide", "maker-c", S.block(14, 10), st, "shingle", 2600, 1650),
        S.make_object("2026-11-05-sign", "maker-c", S.block(4, 10), st, "shingle", 2435, 1640),
        S.make_object("2026-11-05-float", "maker-c", S.block(6, 6), st, "shingle", 2200, 1500),
        S.make_object("2026-11-05-gull", "maker-c", S.block(6, 6), {"a": (96, 80, 64)}, "pier", 2262, 1470),
        S.make_object("2026-11-05-hot", "maker-c", S.block(6, 6), {"a": (250, 10, 10)}, "shingle", 2640, 1665),
        S.make_object("2026-11-05-tiny", "maker-c", S.block(3, 3), st, "shingle", 2640, 1665),
        S.make_object("2026-11-05-pass", "maker-c", S.block(8, 6), st, "shingle", 2630, 1668, label="MARK"),
        S.make_object("2026-11-04-again", "maker-a", S.block(6, 6), st, "shingle", 2640, 1665),
        S.make_object("2026-11-05-quiet", "maker-c", S.block(6, 6), st, "shingle", 2640, 1665, label="hush"),
        dict(S.make_object("2026-11-05-lamp", "maker-c", ["aaa", "aga", "aga", "aaa", "aaa", "aaa"],
                           {"a": (96, 80, 64), "g": (236, 186, 104)}, "shingle", 2640, 1665, scale=4), glow="g"),
    ]
    return out


def scenario():
    ref = S.reference()
    got = {}
    rd = S.reference_dir()
    for name in ("surfaces.json", "palette.json", "conditions.json"):
        with open(os.path.join(rd, name), "rb") as f:
            got["file " + name] = hashlib.sha256(f.read()).hexdigest()
    with open(os.path.join(rd, "keepout.png"), "rb") as f:
        got["pixels keepout.png"] = hashlib.sha256(read_reference_png(f.read(), 0, "keepout.png")).hexdigest()
    for c in ref.conditions:
        got["pixels %s.png" % c.name] = hashlib.sha256(ref.crop(c.name)).hexdigest()
    shore = Shore(ref)
    for oid, world in LANDED:
        at = DAYS[oid[:10]]
        shore.accept(manifest_from_obj(S.fixture_obj(oid)), at, at, world, "0" * 40)
    got["ledger"] = ledger_sha256(shore.events)
    got["draw order"] = " ".join(o["id"] for o in plan(ref, shore.live))
    got["plan"] = plan_sha256(ref, shore.live)
    for o in plan(ref, shore.live):
        got["footprint " + o["id"]] = "%d solid (%d label, %d shown), %d shadow (%d shown)" % (
            len(o["solid"]), sum(1 for p in o["solid"] if p[3]), sum(1 for p in o["solid"] if p[4]),
            len(o["shadow"]), sum(1 for p in o["shadow"] if p[2]))
    w, h, px, panels = sheet(ref, shore.live)
    got["sheet"] = "%dx%d %s" % (w, h, pixels_sha256(px))
    z = zoom(ref, panels[0], shore.byid["2026-11-03-log"], shore.live)
    got["zoom"] = "%dx%d %s" % (z[0], z[1], pixels_sha256(z[2]))
    got["glyphs"] = hashlib.sha256("\n".join(plaque_cells("THE QUICK BROWN FOX'S 0123456789 .-")).encode()).hexdigest()
    lines = []
    for obj in variants():
        m = manifest_from_obj(obj)
        errs, takes, p = shore.judge(m, obj["id"][:10])
        lines += [m.id + " " + e.line() for e in errs] or [m.id + " PASS"]
    got["verdicts"] = lines
    return got


GOLDEN = {'draw order': '2026-11-04-bottle 2026-11-02-flag 2026-11-03-log 2026-11-02-cairn 2026-11-03-shell',
 'file conditions.json': 'ba8678e0d3b38960dde0bd7c77289f1088ad016dd478a12312bea28009700f55',
 'file palette.json': '38124db51bf56a21da961bbefc574f937d5d0ae6dae091c851aa28eb8768103e',
 'file surfaces.json': 'e9f354f1c0ace8c5f3be4455cffd505992e2644cb9d1693327c4620e728029d4',
 'footprint 2026-11-02-cairn': '208 solid (0 label, 208 shown), 34 shadow (34 shown)',
 'footprint 2026-11-02-flag': '65 solid (0 label, 65 shown), 6 shadow (6 shown)',
 'footprint 2026-11-03-log': '629 solid (505 label, 629 shown), 134 shadow (134 shown)',
 'footprint 2026-11-03-shell': '20 solid (0 label, 20 shown), 0 shadow (0 shown)',
 'footprint 2026-11-04-bottle': '120 solid (0 label, 120 shown), 18 shadow (18 shown)',
 'glyphs': 'c81c1c68c120241edb4e9511748740a703782eff6598f73ea1f05f7e44667bf7',
 'ledger': 'e9bb0b00f71e037eb6b874113782eb8937b0ccd0e09c0298e60a2fef6141c32b',
 'pixels fog.png': 'f0d94ce77d3409566207ea87323f5d3f90b3f53d6cb4b4894b88c05b31da80c2',
 'pixels golden.png': 'cd9a805f9b7c6cd58c523d8c35baaf383ec49ebbc95fa35d5979d2ab7a8113f1',
 'pixels keepout.png': '98cc0d4edab0639d8baddce29c9996fc1ef49c1e88a897ba52641fa1cefe3d3b',
 'pixels night.png': 'e1642b2c9fa325e0ae6e6b3e83387307f04726da172aea505683ecc5b178d02b',
 'pixels noon.png': 'bf842a2fa2ca89a9729dab6447181fdb121d71aab259310d2e816b615368dde7',
 'plan': '70844d1e23d2b67bb217dd95f6375d79f994d097faee9aa649dd66e884958980',
 'sheet': '2560x1280 867c2d013b823c28f3984d14c42c67d59e1c84738b1e2d24e3d02ace5e603805',
 'verdicts': ['2026-11-05-lean E_COVER would leave 2026-11-02-cairn 56% visible (needs 60%); first covered px at '
              '(2594,1649)',
              '2026-11-05-lean E_COVER takes 44% of 2026-11-02-cairn (max 25%); first covered px at (2594,1649)',
              '2026-11-05-hide E_HIDDEN only 20% visible (needs 50%); hidden by 2026-11-02-cairn, first at '
              '(2599,1641)',
              '2026-11-05-sign E_LABEL_COVER covers the label of 2026-11-03-log at (2434,1631)',
              '2026-11-05-float E_REGION cell (0,0) at (2198,1495) is on keep-out (and 35 more px)',
              '2026-11-05-float E_REST foot cell (0,5) 80 px above dry band at x=2198 (and 5 more foot cells)',
              '2026-11-05-gull E_REGION cell (0,0) at (2260,1465) is on keep-out (and 11 more px)',
              "2026-11-05-hot E_PALETTE 'a' (250,10,10) has a channel of 250, max 240",
              '2026-11-05-tiny E_SIZE 9 opaque cells, need 16-2500',
              '2026-11-05-pass PASS',
              '2026-11-04-again E_QUOTA maker-a already has 2026-11-04-bottle on 2026-11-04 (one object per maker '
              'per day)',
              "2026-11-05-quiet E_LABEL label character 0 (0x68) is not one of A-Z 0-9 space . ' -",
              '2026-11-05-lamp PASS'],
 'zoom': '500x244 ee5c9f3ea3260d3b770f048881f7c5a1a35bfee0314e0ba24011cb159aed02ce'}


class TestGolden(unittest.TestCase):
    def test_golden(self):
        got = scenario()
        self.assertEqual(sorted(got), sorted(GOLDEN))
        for k in sorted(GOLDEN):
            self.assertEqual(got[k], GOLDEN[k], k)


if __name__ == "__main__":
    if "--print" in sys.argv:
        import pprint
        pprint.pprint(scenario(), width=118, sort_dicts=True)
    else:
        unittest.main()
