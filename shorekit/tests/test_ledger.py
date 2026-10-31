"""The ledger: replay, rule 7's quotas, priority, storms (with piles), vetoes, and refusal of any
ledger that is not what the kit would have written."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import support as S
from shorekit import MAX_LIVE
from shorekit.cli import main
from shorekit.compose import plan_sha256
from shorekit.errors import ShoreError
from shorekit.ledger import Shore, day_number, days_from_civil, ledger_bytes, load_shore, parse_ledger
from shorekit.manifest import manifest_from_obj
from shorekit.strictjson import canonical

DAY1, DAY2, DAY3, DAY4 = "2026-11-02T04:30:00Z", "2026-11-03T04:30:00Z", "2026-11-04T04:30:00Z", "2026-11-05T04:30:00Z"


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue().splitlines()


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shorekit-test-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.shore = S.new_shore(self.tmp)
        self.n = 0

    def land(self, at, cands, expect=0):
        """Run one pass the way the carrier will: queue -> replay --out into the shore itself."""
        self.n += 1
        q = S.write_queue(os.path.join(self.tmp, "q%d" % self.n), at, cands)
        code, lines = run(["replay", "--shore", self.shore, "--queue", q, "--out", self.shore])
        self.assertEqual(code, expect, lines)
        with open(os.path.join(self.shore, "result.json"), "rb") as f:
            self.result = json.loads(f.read())
        os.remove(os.path.join(self.shore, "result.json"))
        return lines

    def events(self):
        with open(os.path.join(self.shore, "ledger.json"), "rb") as f:
            return parse_ledger(f.read())

    def write_events(self, events):
        with open(os.path.join(self.shore, "ledger.json"), "wb") as f:
            f.write(ledger_bytes(events))

    def replay(self):
        return run(["replay", "--shore", self.shore])

    def loaded(self):
        return load_shore(S.reference(), os.path.join(self.shore, "ledger.json"), os.path.join(self.shore, "objects"))


def fx(name):
    return S.fixture_obj(name)


class TestDays(Tmp):
    def three_days(self):
        self.land(DAY1, [("world-1", fx("2026-11-02-cairn")), ("world-2", fx("2026-11-02-flag"))])
        self.land(DAY2, [("world-1", fx("2026-11-03-shell")), ("world-2", fx("2026-11-03-log"))])
        self.land(DAY3, [("world-1", fx("2026-11-04-bottle"))])

    def test_fixtures_land_and_replay(self):
        self.three_days()
        evs = self.events()
        self.assertEqual([e["event"] for e in evs], ["add"] * 5)
        self.assertEqual([e["seq"] for e in evs], [1, 2, 3, 4, 5])
        shore = self.loaded()
        self.assertEqual([a.id for a in shore.live], [e["id"] for e in evs])
        self.assertEqual(self.result["live"], [a.id for a in shore.live])
        self.assertEqual(self.result["plan_sha256"], plan_sha256(S.reference(), shore.live))
        code, lines = self.replay()
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith("LEDGER OK 5 events, 5/48 live, 0 taken by the sea, 0 misfits"))

    def test_quota_one_per_maker_per_day(self):
        a = S.make_object("2026-11-02-a", "maker-a", S.block(4, 4), S.STONE, "shingle", 2640, 1665)
        b = S.make_object("2026-11-02-b", "maker-a", S.block(4, 4), S.STONE, "shingle", 2660, 1667)
        c = S.make_object("2026-11-02-c", "maker-c", S.block(4, 4), S.STONE, "shingle", 2680, 1669)
        self.land(DAY1, [("world-1", a), ("world-1", b), ("world-1", c)])
        self.assertEqual([e["id"] for e in self.result["append"]], ["2026-11-02-a", "2026-11-02-c"])
        self.assertEqual(self.result["returned"][0]["messages"],
                         ["E_QUOTA maker-a already has 2026-11-02-a on 2026-11-02 (one object per maker per day)"])
        b["id"] = "2026-11-03-b"
        self.land(DAY2, [("world-1", b)])
        self.assertEqual(self.result["returned"], [])

    def test_ids_dates_kits_and_references(self):
        self.land(DAY1, [("world-1", fx("2026-11-02-cairn"))])
        again = fx("2026-11-02-cairn")
        again["maker"] = "maker-z"
        future = S.make_object("2026-11-09-a", "maker-b", S.block(4, 4), S.STONE, "shingle", 2640, 1665)
        kit = S.make_object("2026-11-03-k", "maker-c", S.block(4, 4), S.STONE, "shingle", 2660, 1667)
        kit["kit"] = "2.0.0"
        r2 = S.make_object("2026-11-03-r", "maker-d", S.block(4, 4), S.STONE, "shingle", 2680, 1669, rid="r2")
        self.land(DAY2, [("world-1", again), ("world-1", future), ("world-1", kit), ("world-1", r2)])
        got = {r["id"]: r["messages"][0].split()[0] for r in self.result["returned"]}
        self.assertEqual(got, {"2026-11-02-cairn": "E_TAKEN", "2026-11-09-a": "E_ID", "2026-11-03-k": "E_KIT",
                               "2026-11-03-r": "E_REFERENCE"})

    def test_returned_objects_are_reported_not_fatal(self):
        bad = S.make_object("2026-11-02-a", "maker-a", S.block(4, 4), S.STONE, "shingle", 2640, 1600)
        lines = self.land(DAY1, [("world-1", bad)])
        self.assertIn("RETURN world-1/2026-11-02-a: E_REST", "\n".join(lines))
        self.assertEqual(self.events(), [])

    def test_unparseable_candidate(self):
        q = S.write_queue(os.path.join(self.tmp, "qx"), DAY1, [("world-1", fx("2026-11-02-cairn"))])
        with open(os.path.join(self.tmp, "qx", "world-1", "2026-11-02-cairn.json"), "wb") as f:
            f.write(b'{"shore": 1.0}')
        code, lines = run(["replay", "--shore", self.shore, "--queue", q])
        self.assertEqual(code, 0)
        self.assertIn("E_PARSE", lines[-2])


class TestPriority(Tmp):
    def test_parity_alternates_and_the_loser_is_a_race(self):
        self.assertEqual(days_from_civil(1970, 1, 1), 0)
        self.assertEqual(days_from_civil(2026, 11, 2), 20759)
        self.assertEqual(day_number(DAY1) % 2, 1)
        for at, first in ((DAY1, "world-2"), (DAY2, "world-1")):
            self.setUp()
            day = at[:10]
            one = S.make_object(day + "-one", "maker-a", S.block(10, 10), S.STONE, "shingle", 2640, 1665)
            two = S.make_object(day + "-two", "maker-b", S.block(10, 10), S.STONE, "shingle", 2643, 1666)
            self.land(at, [("world-1", one), ("world-2", two)])
            self.assertEqual([e["world"] for e in self.result["append"]], [first])
            ret = self.result["returned"][0]
            self.assertTrue(ret["race"])
            self.assertTrue(ret["messages"][-1].startswith("E_RACE it passes against yesterday's ledger"))


def fill(test, n, day="2026-11-02", at=DAY1):
    """n small stones along the dry band, one maker each, all on one pass."""
    ref = S.reference()
    shore = Shore(ref)
    cands = []
    x = 1700
    while len(cands) < n:
        d = ref.dry(x)
        if d:
            obj = S.make_object("%s-s%02d" % (day, len(cands)), "maker-%02d" % len(cands), S.block(4, 4), S.STONE,
                                "shingle", x, (d[0] + d[1]) >> 1)
            m = manifest_from_obj(obj)
            if not shore.judge(m, day)[0]:
                shore.accept(m, at, at, "world-1", "0" * 40)
                cands.append(("world-1", obj))
        x += 9
    test.land(at, cands)
    test.assertEqual(len(test.result["append"]), n)


class TestStormsAndVetoes(Tmp):
    def test_storm_takes_the_oldest_with_its_pile(self):
        fill(self, MAX_LIVE)
        top = S.make_object("2026-11-03-top", "maker-t", S.block(4, 4), S.STONE, "2026-11-02-s00", 0, 0)
        s00 = self.loaded().byid["2026-11-02-s00"]
        top["place"]["x"], top["place"]["y"] = s00.left + 1, s00.top - 1
        self.land(DAY2, [("world-1", top)])
        self.assertEqual(self.result["returned"][0]["messages"],
                         ["E_ON 2026-11-02-s00 would be taken by the storm that makes room"])
        code, lines = run(["replay", "--shore", self.shore, "--veto", "2026-11-02-s47", "--at", DAY2, "--out", self.shore])
        self.assertEqual(code, 0, lines)
        self.assertIn("VETO seq 49 takes 2026-11-02-s47", lines)
        self.land(DAY2, [("world-1", top)])
        self.assertEqual(self.result["append"][0]["id"], "2026-11-03-top")
        new = S.make_object("2026-11-04-new", "maker-n", S.block(4, 4), S.STONE, "shingle", 2846, 1683)
        lines = self.land(DAY3, [("world-2", new)])
        self.assertIn("STORM seq 51 takes 2026-11-02-s00, 2026-11-03-top (room for 2026-11-04-new)", lines)
        storm = self.result["append"][0]
        self.assertEqual(storm, {"seq": 51, "event": "storm", "at": DAY3, "for": "2026-11-04-new",
                                 "takes": ["2026-11-02-s00", "2026-11-03-top"]})
        shore = self.loaded()
        self.assertEqual(len(shore.live), 47)
        self.assertEqual(sorted(shore.taken), ["2026-11-02-s00", "2026-11-02-s47", "2026-11-03-top"])
        self.assertIn("2026-11-02-s00", shore.ids)
        again = S.make_object("2026-11-05-s00", "maker-q", S.block(4, 4), S.STONE, "2026-11-02-s00", 1700, 1290)
        errs = shore.judge(manifest_from_obj(again), "2026-11-05")[0]
        self.assertEqual([e.line() for e in errs], ["E_ON 2026-11-02-s00 is no longer on the shore (the sea took it)"])

        evs = self.events()
        forged = [dict(e) for e in evs]
        forged[50]["takes"] = ["2026-11-02-s00"]
        self.write_events(forged)
        self.assertEqual(self.replay()[0], 3)
        early = [dict(e) for e in evs[:49]]
        early.append({"seq": 50, "event": "storm", "at": DAY2, "for": "2026-11-03-top", "takes": ["2026-11-02-s00"]})
        self.write_events(early)
        code, lines = self.replay()
        self.assertEqual(code, 3)
        self.assertIn("a storm with room to spare", lines[0])
        alone = [dict(e) for e in evs[:51]]
        self.write_events(alone)
        code, lines = self.replay()
        self.assertEqual(code, 3)
        self.assertIn("ends after a storm", lines[0])
        self.write_events(evs)
        self.assertEqual(self.replay()[0], 0)

    def test_full_shore_without_a_storm_is_refused(self):
        fill(self, MAX_LIVE)
        evs = self.events()
        extra = S.make_object("2026-11-03-x", "maker-x", S.block(4, 4), S.STONE, "shingle", 2846, 1683)
        m = manifest_from_obj(extra)
        with open(os.path.join(self.shore, "objects", m.id + ".json"), "wb") as f:
            f.write(m.canonical)
        evs.append({"seq": 49, "event": "add", "at": DAY2, "lands": DAY2, "id": m.id, "maker": "maker-x",
                    "world": "world-1", "commit": "0" * 40, "sha256": m.sha256, "reference": "r1", "kit": "1.0.0"})
        self.write_events(evs)
        code, lines = self.replay()
        self.assertEqual(code, 3)
        self.assertIn("would make 49 live; a storm must come first", lines[0])

    def test_veto_takes_the_pile(self):
        self.land(DAY1, [("world-1", fx("2026-11-02-cairn")), ("world-2", fx("2026-11-02-flag"))])
        self.land(DAY2, [("world-1", fx("2026-11-03-shell"))])
        code, lines = run(["replay", "--shore", self.shore, "--veto", "2026-11-02-cairn", "--at", DAY2, "--out", self.shore])
        self.assertEqual(code, 0)
        self.assertIn("VETO seq 4 takes 2026-11-02-cairn, 2026-11-03-shell", lines)
        self.assertEqual([a.id for a in self.loaded().live], ["2026-11-02-flag"])
        evs = self.events()
        evs[3]["takes"] = ["2026-11-02-cairn"]
        self.write_events(evs)
        self.assertEqual(self.replay()[0], 3)
        code, lines = run(["replay", "--shore", self.shore, "--veto", "2026-11-02-nothing", "--at", DAY3])
        self.assertEqual(code, 3)


class TestCorruptLedgers(Tmp):
    def setUp(self):
        Tmp.setUp(self)
        self.land(DAY1, [("world-1", fx("2026-11-02-cairn")), ("world-2", fx("2026-11-02-flag"))])
        self.land(DAY2, [("world-1", fx("2026-11-03-shell")), ("world-2", fx("2026-11-03-log"))])
        self.good = self.events()

    def refused(self, events, text):
        self.write_events(events)
        code, lines = self.replay()
        self.assertEqual(code, 3, lines)
        self.assertIn(text, lines[0])

    def test_each_kind_of_damage(self):
        def ev(mut):
            evs = [dict(e) for e in self.good]
            mut(evs)
            return evs
        self.refused(ev(lambda e: e[1].update(seq=3)), "seq must be 2")
        self.refused(ev(lambda e: e.pop(0)), "seq must be 1")
        self.refused(ev(lambda e: e[1].update(at="2026-11-01T00:00:00Z", lands="2026-11-01T00:00:00Z")), "is before")
        self.refused(ev(lambda e: e[2].update(at="2026-11-02T05:00:00Z", lands="2026-11-02T05:00:00Z")),
                     "maker-a already added 2026-11-02-cairn on 2026-11-02")
        self.refused(ev(lambda e: e[1].update(sha256="0" * 64)), "the ledger says")
        self.refused(ev(lambda e: e[1].update(event="sink")), "must be add, storm or veto")
        self.refused(ev(lambda e: e[1].update(at="2026-11-02T24:00:00Z")), "not a real time")
        self.refused(ev(lambda e: e[1].update(lands="2026-11-01T00:00:00Z")), "lands before")
        self.refused(ev(lambda e: e.append(dict(e[0], seq=5, at=DAY3, lands=DAY3, maker="maker-q"))), "already used")
        self.refused(ev(lambda e: e[1].update(maker="maker-q")), "disagrees with the ledger")

    def test_edited_object(self):
        p = os.path.join(self.shore, "objects", "2026-11-02-flag.json")
        obj = json.loads(open(p, "rb").read())
        obj["place"]["x"] += 1
        with open(p, "wb") as f:
            f.write(canonical(obj))
        self.refused(self.good, "objects/2026-11-02-flag.json has sha256")

    def test_rule_break_is_corruption_under_its_own_kit_and_a_misfit_under_another(self):
        over = S.fixture_obj("2026-11-02-flag")
        over["id"], over["maker"] = "2026-11-04-over", "maker-o"
        over["place"] = {"on": "shingle", "x": 2450, "y": 1640}    # over the log's label
        m = manifest_from_obj(over)
        with open(os.path.join(self.shore, "objects", m.id + ".json"), "wb") as f:
            f.write(m.canonical)
        add = {"seq": 5, "event": "add", "at": DAY3, "lands": DAY3, "id": m.id, "maker": "maker-o", "world": "world-2",
               "commit": "0" * 40, "sha256": m.sha256, "reference": "r1", "kit": "1.0.0"}
        self.refused(self.good + [add], "fails against its own reference and kit: E_LABEL_COVER covers the label of")
        self.write_events(self.good + [dict(add, kit="0.9.0")])
        code, lines = self.replay()
        self.assertEqual(code, 0)
        self.assertIn("0 taken by the sea, 1 misfits", lines[0])
        self.assertTrue(lines[1].startswith("MISFIT seq 5 2026-11-04-over: E_"))
        self.assertIn("2026-11-04-over", [a.id for a in self.loaded().live])

    def test_previous_must_be_a_prefix(self):
        prev = os.path.join(self.tmp, "prev.json")
        with open(prev, "wb") as f:
            f.write(ledger_bytes(self.good[:3]))
        code, lines = run(["replay", "--shore", self.shore, "--previous", prev])
        self.assertEqual(code, 0)
        self.assertIn("EXTENDS the previous ledger (3 events) by 1", lines)
        changed = [dict(e) for e in self.good[:3]]
        changed[2]["lands"] = DAY4
        with open(prev, "wb") as f:
            f.write(ledger_bytes(changed))
        code, lines = run(["replay", "--shore", self.shore, "--previous", prev])
        self.assertEqual(code, 3)
        self.assertIn("dropped or changed an event", lines[-1])

    def test_ledger_bytes_round_trip(self):
        data = ledger_bytes(self.good)
        self.assertEqual(parse_ledger(data), self.good)
        self.assertEqual(data.count(b"\n"), len(self.good) + 2)
        self.assertEqual(ledger_bytes([]), b'{"events":[],"shore_ledger":1}\n')
        with self.assertRaises(ShoreError):
            parse_ledger(b'{"events":[],"shore_ledger":2}')


if __name__ == "__main__":
    unittest.main()
