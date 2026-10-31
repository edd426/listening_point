"""The ledger: replay, rule 7's quotas, priority, the sea (batched storms and the owner's veto, one
event kind, with piles), the carrier's reasons, and refusal of any ledger that is not what the kit
would have written."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import support as S
from shorekit import KIT_VERSION, MAX_LIVE, STORM_TO
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
    cands = [("world-1", obj) for obj in S.crowd(Shore(S.reference()), n, day, at)]
    test.land(at, cands)
    test.assertEqual(len(test.result["append"]), n)


def ids(prefix, a, b):
    return ["%s-s%02d" % (prefix, i) for i in range(a, b)]


class TestTheSea(Tmp):
    """Rule 7: a storm comes only when 48 are live, and takes the oldest until 40 remain, with whatever
    rests on them. In the ledger a storm and the owner's veto are one kind of event, `sea`, which says
    what was taken and never why."""

    def crowded(self):
        """47 stones on day one, then a top built onto the second of them: 48 live."""
        fill(self, MAX_LIVE - 1)
        s01 = self.loaded().byid["2026-11-02-s01"]
        top = S.make_object("2026-11-03-top", "maker-t", S.block(4, 4), S.STONE, "2026-11-02-s01", s01.left + 1, s01.top - 1)
        self.land(DAY2, [("world-1", top)])
        self.assertEqual(self.result["append"][0]["id"], "2026-11-03-top")
        self.assertEqual(len(self.loaded().live), MAX_LIVE)

    def reasons(self, *rs):
        self.n += 1
        path = os.path.join(self.tmp, "sea-%d.json" % self.n)
        with open(path, "wb") as f:
            f.write(canonical({"shore_sea": 1, "sea": list(rs)}))
        return path

    def strict(self, path):
        return run(["replay", "--shore", self.shore, "--reasons", path])

    def test_a_storm_takes_the_oldest_down_to_forty_with_their_piles(self):
        self.crowded()
        onto = S.make_object("2026-11-04-held", "maker-o", S.block(4, 4), S.STONE, "2026-11-02-s00", 0, 0)
        s00 = self.loaded().byid["2026-11-02-s00"]
        onto["place"]["x"], onto["place"]["y"] = s00.left + 1, s00.top - 1
        new = S.make_object("2026-11-04-new", "maker-n", S.block(4, 4), S.STONE, "shingle", 2846, 1683)
        lines = self.land(DAY3, [("world-1", onto), ("world-1", new)])
        self.assertEqual(self.result["returned"][0]["messages"],
                         ["E_ON 2026-11-02-s00 would be taken by the sea that makes room"])
        want = ids("2026-11-02", 0, 7) + ["2026-11-03-top"]
        self.assertIn("SEA seq 49 takes %s (a storm, to make room for 2026-11-04-new)" % ", ".join(want), lines)
        sea, add = self.result["append"]
        # the ledger says only what the sea took: no reason, no "for"
        self.assertEqual(sea, {"seq": 49, "event": "sea", "at": DAY3, "takes": want})
        self.assertEqual(add["id"], "2026-11-04-new")
        # the reason goes to whoever ran the pass (the carrier), in result.json, never in the ledger
        self.assertEqual(self.result["sea"], [{"seq": 49, "why": "storm", "for": "2026-11-04-new"}])
        shore = self.loaded()
        self.assertEqual(len(shore.live), STORM_TO + 1)
        self.assertEqual(sorted(shore.taken), sorted(want))
        self.assertIn("2026-11-02-s00", shore.ids)
        again = S.make_object("2026-11-05-s00", "maker-q", S.block(4, 4), S.STONE, "2026-11-02-s00", 1700, 1290)
        errs = shore.judge(manifest_from_obj(again), "2026-11-05")[0]
        self.assertEqual([e.line() for e in errs], ["E_ON 2026-11-02-s00 is no longer on the shore (the sea took it)"])
        # 41 live: the next object needs no storm
        later = S.make_object("2026-11-05-later", "maker-l", S.block(4, 4), S.STONE, "shingle", 2836, 1683)
        self.land(DAY4, [("world-1", later)])
        self.assertEqual([e["event"] for e in self.result["append"]], ["add"])
        self.assertEqual(self.result["sea"], [])

        # with the carrier's reasons, replay holds the storm to the rule exactly
        good = self.reasons({"seq": 49, "why": "storm", "for": "2026-11-04-new"})
        code, lines = self.strict(good)
        self.assertEqual(code, 0, lines)
        self.assertIn("REASONS OK 1 sea event, each held to its rule", lines)
        evs = self.events()

        def forged(takes, check_plain=True):
            """A ledger whose storm took `takes` instead: refused with the reasons; without them, only
            if it breaks what any sea event must keep (live objects, nothing left floating)."""
            bad = [dict(e) for e in evs[:50]]
            bad[48]["takes"] = takes
            self.write_events(bad)
            code, lines = self.strict(good)
            self.assertEqual(code, 3, lines)
            self.assertIn("the storm must take", lines[0])
            return self.replay()[0]
        # kit 1.0.0's storm (just enough room), and one that takes one too many: both well-formed sea
        # events, so a world (which has no reasons) cannot tell them from a veto, and accepts them
        self.assertEqual(forged(["2026-11-02-s00"]), 0)
        self.assertEqual(forged(want[:-1] + ["2026-11-02-s07", "2026-11-03-top"]), 0)
        self.write_events(evs)
        self.assertEqual(self.strict(good)[0], 0)

        early = [dict(e) for e in evs[:47]]
        early.append({"seq": 48, "event": "sea", "at": DAY2, "takes": ["2026-11-02-s00"]})
        self.write_events(early)
        code, lines = self.strict(self.reasons({"seq": 48, "why": "storm", "for": "2026-11-03-top"}))
        self.assertEqual(code, 3)
        self.assertIn("a storm with 47 live; a storm comes only when 48 are", lines[0])
        self.assertEqual(self.replay()[0], 0, "a sea event with room to spare is a veto as far as a world can tell")

        alone = [dict(e) for e in evs[:49]]
        self.write_events(alone)
        code, lines = self.strict(good)
        self.assertEqual(code, 3)
        self.assertIn("ends after a storm", lines[0])
        self.write_events(evs)
        for rs, text in (([], "seq 49: the sea event has no reason"),
                         ([{"seq": 49, "why": "storm", "for": "2026-11-05-later"}], "the storm before it was for 2026-11-05-later"),
                         ([{"seq": 49, "why": "storm", "for": "2026-11-04-new"}, {"seq": 50, "why": "veto", "id": "2026-11-04-new"}],
                          "the reasons name seq 50, which is an add"),
                         ([{"seq": 49, "why": "storm", "for": "2026-11-04-new"}, {"seq": 90, "why": "veto", "id": "2026-11-04-new"}],
                          "the reasons name seq 90, which the ledger does not reach"),
                         ([{"seq": 49, "why": "veto", "id": "2026-11-02-s00"}], "the veto of 2026-11-02-s00 must take 2026-11-02-s00")):
            code, lines = self.strict(self.reasons(*rs))
            self.assertEqual(code, 3, (rs, lines))
            self.assertIn(text, lines[0])

    def test_any_sea_event_takes_live_objects_and_leaves_nothing_floating(self):
        self.crowded()
        evs = self.events()

        def refused(sea, text):
            self.write_events(evs + [dict(sea, seq=49, event="sea", at=DAY3)])
            code, lines = self.replay()
            self.assertEqual(code, 3, lines)
            self.assertIn(text, lines[0])
        refused({"takes": ["2026-11-02-s01"]}, "takes 2026-11-02-s01 but leaves 2026-11-03-top, which rests on it")
        refused({"takes": ["2026-11-09-x"]}, "takes 2026-11-09-x, which is not on the shore")
        refused({"takes": ["2026-11-02-s03", "2026-11-02-s02"]}, "listed in seq order")
        refused({"takes": ["2026-11-02-s00"], "for": "2026-11-04-new"}, "keys must be exactly at, event, seq, takes")
        self.write_events(evs + [{"seq": 49, "event": "storm", "at": DAY3, "for": "x", "takes": ["2026-11-02-s00"]}])
        self.assertIn("must be add or sea", self.replay()[1][0])
        self.write_events(evs + [{"seq": 49, "event": "sea", "at": DAY3, "takes": ["2026-11-02-s01", "2026-11-03-top"]}])
        self.assertEqual(self.replay()[0], 0)

    def test_a_full_shore_without_the_sea_is_refused(self):
        fill(self, MAX_LIVE)
        evs = self.events()
        extra = S.make_object("2026-11-03-x", "maker-x", S.block(4, 4), S.STONE, "shingle", 2846, 1683)
        m = manifest_from_obj(extra)
        with open(os.path.join(self.shore, "objects", m.id + ".json"), "wb") as f:
            f.write(m.canonical)
        evs.append({"seq": 49, "event": "add", "at": DAY2, "lands": DAY2, "id": m.id, "maker": "maker-x",
                    "world": "world-1", "commit": "0" * 40, "sha256": m.sha256, "reference": "r1", "kit": KIT_VERSION})
        self.write_events(evs)
        code, lines = self.replay()
        self.assertEqual(code, 3)
        self.assertIn("would make 49 live; the sea must make room first", lines[0])

    def test_the_owners_veto_is_a_sea_event_like_any_other(self):
        self.land(DAY1, [("world-1", fx("2026-11-02-cairn")), ("world-2", fx("2026-11-02-flag"))])
        self.land(DAY2, [("world-1", fx("2026-11-03-shell"))])
        code, lines = run(["replay", "--shore", self.shore, "--veto", "2026-11-02-cairn", "--at", DAY2, "--out", self.shore])
        self.assertEqual(code, 0)
        self.assertIn("SEA seq 4 takes 2026-11-02-cairn, 2026-11-03-shell (the owner's veto of 2026-11-02-cairn)", lines)
        with open(os.path.join(self.shore, "result.json"), "rb") as f:
            result = json.loads(f.read())
        self.assertEqual(result["append"], [{"seq": 4, "event": "sea", "at": DAY2, "takes": ["2026-11-02-cairn", "2026-11-03-shell"]}])
        self.assertEqual(result["sea"], [{"seq": 4, "why": "veto", "id": "2026-11-02-cairn"}])
        self.assertEqual([a.id for a in self.loaded().live], ["2026-11-02-flag"])
        evs = self.events()
        self.assertNotIn(b"veto", ledger_bytes(evs))
        evs[3]["takes"] = ["2026-11-02-cairn"]
        self.write_events(evs)
        self.assertEqual(self.replay()[0], 3, "the shell would be left floating")
        evs[3]["takes"] = ["2026-11-03-shell"]
        self.write_events(evs)
        self.assertEqual(self.replay()[0], 0, "a sea event taking just the shell is as good as any")
        code, lines = run(["replay", "--shore", self.shore, "--reasons", self.reasons({"seq": 4, "why": "veto", "id": "2026-11-02-cairn"})])
        self.assertEqual(code, 3, "but not as the veto of the cairn")
        self.assertIn("the veto of 2026-11-02-cairn must take 2026-11-02-cairn, 2026-11-03-shell", lines[0])
        code, lines = run(["replay", "--shore", self.shore, "--veto", "2026-11-02-nothing", "--at", DAY3])
        self.assertEqual(code, 3)

    def test_reasons_files_are_strict(self):
        self.land(DAY1, [("world-1", fx("2026-11-02-cairn"))])
        for body in (b"[]", b'{"shore_sea": 2, "sea": []}', b'{"shore_sea": 1, "sea": [1]}',
                     b'{"shore_sea": 1, "sea": [{"seq": 1, "why": "tide", "id": "2026-11-02-cairn"}]}',
                     b'{"shore_sea": 1, "sea": [{"seq": 1, "why": "veto", "for": "2026-11-02-cairn"}]}',
                     b'{"shore_sea": 1, "sea": [{"seq": 0, "why": "veto", "id": "2026-11-02-cairn"}]}',
                     b'{"shore_sea": 1, "sea": [{"seq": 1, "why": "veto", "id": "2026-11-02-cairn", "x": 1}]}',
                     b'{"shore_sea": 1, "sea": [{"seq": 2, "why": "veto", "id": "a"}, {"seq": 1, "why": "veto", "id": "a"}]}'):
            path = os.path.join(self.tmp, "bad.json")
            with open(path, "wb") as f:
                f.write(body)
            code, lines = run(["replay", "--shore", self.shore, "--reasons", path])
            self.assertEqual(code, 3, (body, lines))
        code, lines = run(["replay", "--shore", self.shore, "--reasons", self.reasons()])
        self.assertEqual(code, 0, lines)


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
        self.refused(ev(lambda e: e[1].update(event="sink")), "must be add or sea")
        self.refused(ev(lambda e: e[1].update(at="2026-11-02T24:00:00Z")), "not a real time")
        self.refused(ev(lambda e: e[1].update(lands="2026-11-01T00:00:00Z")), "lands before")
        self.refused(ev(lambda e: e.append(dict(e[0], seq=5, at=DAY3, lands=DAY3, maker="maker-q"))), "already used")
        self.refused(ev(lambda e: e[1].update(maker="maker-q")), "disagrees with the ledger")

    def test_edited_object(self):
        p = os.path.join(self.shore, "objects", "2026-11-02-flag.json")
        with open(p, "rb") as f:
            obj = json.loads(f.read())
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
               "commit": "0" * 40, "sha256": m.sha256, "reference": "r1", "kit": KIT_VERSION}
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
