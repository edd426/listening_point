#!/usr/bin/env python3
"""Tests for the animal lives (v3 phase 5, part 2): the lambs, the cat's kittens and the pale seal's year, in
story.py, and where they are drawn (events.py, fauna.py, life.py, seaplan.py).

usage: ./venv/bin/python -m unittest tests.test_lives      (from the repo root; a few minutes)

Offline: synthetic and fair weather, small frames.
"""
import datetime as dt
import math
import os
import sys
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "renderers", "procedural"))
import listening_point as lp  # noqa: E402
import story as S  # noqa: E402
import water as wt  # noqa: E402
from day import BUDAPEST, Day  # noqa: E402

D = dt.date
DAY = dt.timedelta(days=1)
TZ, LAT, LON = BUDAPEST["tz"], BUDAPEST["lat"], BUDAPEST["lon"]
YEARS = range(S.LIVES_FROM, S.LIVES_FROM + 8)
SCALE = 0.25


def story(date, weather="synthetic"):
    return S.Story(SimpleNamespace(date=date, tzname=TZ, lat=LAT, lon=LON), weather, None)


def litter_year():
    """The first year with a litter, and the litter."""
    for Y in YEARS:
        lit = S.litters(Y)[Y][0]
        if lit:
            return Y, lit
    raise AssertionError("no litter in eight years")


class Lambs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # every day of two years, synthetic weather (the sale waits for a day fit for work)
        cls.days = [D(S.LIVES_FROM, 1, 1) + i * DAY for i in range(2 * 365)]
        cls.st = {d: story(d) for d in cls.days}

    def test_lambs_grow_and_are_gone_by_autumn(self):
        """Lambs come in spring, their size rises with their age from about half a ewe's, and by the autumn they
        are all gone (sold); never more than MAX_LAMBS."""
        seen = {}
        for d in self.days:
            st = self.st[d]
            self.assertLessEqual(len(st.lambs), S.MAX_LAMBS, d)
            for lb in st.lambs:
                self.assertTrue((3, 20) <= (d.month, d.day) < (10, 20), (d, lb["id"]))
                seen.setdefault(lb["id"], []).append((lb["age"], lb["size"]))
            if (d.month, d.day) >= (10, 20) or d.month < 3:
                self.assertEqual(st.lambs, (), d)
        self.assertGreaterEqual(len(seen), 4)
        for k, v in seen.items():
            ages, sizes = zip(*v)
            self.assertEqual(list(ages), list(range(ages[0], ages[0] + len(ages))), k)     # every day, one day older
            self.assertTrue(all(b > a for a, b in zip(sizes, sizes[1:])), k)
            self.assertLess(sizes[0], 0.55, k)
            self.assertGreater(sizes[-1], 0.75, k)                                          # four months on, sturdier
            self.assertGreater(len(ages), 100, k)                                           # at her side all summer

    def test_the_same_lamb_is_the_same_lamb(self):
        """From one day to the next a lamb keeps its mother, its side of her, its look and its birthday; the ewe lamb
        kept back is the same animal in the flock the day after the sale (a hogg, in the oldest ewe's place)."""
        kept_seen = False
        for a, b in zip(self.days, self.days[1:]):
            la = {lb["id"]: lb for lb in self.st[a].lambs}
            lb_ = {lb["id"]: lb for lb in self.st[b].lambs}
            for k in set(la) & set(lb_):
                for f in ("mother", "side", "seed", "born", "ewe", "kept"):
                    self.assertEqual(la[k][f], lb_[k][f], (a, k, f))
            if la and not lb_:                         # the sale: the lambs went the night after a
                self.assertEqual(self.st[b].sold, a)
                kept = [k for k, v in la.items() if v["kept"]]
                hoggs = [e for e in self.st[b].ewes or () if e]
                self.assertEqual(kept, [e["id"] for e in hoggs if e["age"] < 200], b)
                kept_seen |= bool(kept)
            ea, eb = self.st[a].ewes or (None,) * 4, self.st[b].ewes or (None,) * 4
            for x, y in zip(ea, eb):
                if x and y:
                    self.assertEqual((x["id"], x["slot"]), (y["id"], y["slot"]))
                    self.assertGreater(y["size"], x["size"])
        self.assertTrue(kept_seen)

    def test_the_flock_carries_over(self):
        """Four ewes always; a kept ewe lamb lambs first the spring she is two, not the one after her birth."""
        yrs = S.flock_years(max(YEARS) + 1)
        for Y in YEARS:
            ewes = yrs[Y]["ewes"]
            self.assertEqual(len(ewes), S.EWES)
            mums = {lb["mother"] for lb in yrs[Y]["lambs"]}
            for k, (i, born, year) in enumerate(ewes):
                if Y - year < S.TUP_AGE:
                    self.assertNotIn(k, mums, (Y, i))
            if yrs[Y]["kept"]:
                self.assertEqual(yrs[Y + 1]["ewes"][yrs[Y]["place"]][0], yrs[Y]["kept"])

    def test_lambs_by_their_mothers_and_ewes_unmoved(self):
        """Each lamb is near its mother (within a few metres) and on her side of the field walls; adding the lambs
        moves no ewe (their draws are the story's own)."""
        import events
        for d in (D(S.LIVES_FROM, 4, 20), D(S.LIVES_FROM, 6, 15), D(S.LIVES_FROM, 8, 10)):
            day = Day(d, weather="fair")
            ev, st = day.events, day.story
            self.assertTrue(st.lambs, d)
            for m in range(0, 1440, 13):
                flock = ev.sheep(m / 60, st.lambs, st.ewes)
                ewes = {}
                for x, y, f, g, size, view, who in flock:
                    if who is None or "mother" not in who:
                        ewes[len(ewes)] = (x, y)
                bare = [p[:2] for p in ev.sheep(m / 60, (), st.ewes)]
                self.assertEqual(sorted(ewes.values()), sorted(bare), (d, m))
                for x, y, f, g, size, view, who in flock:
                    if who is None or "mother" not in who:
                        continue
                    i = who["mother"]
                    # the mother's own position, from the bare flock: match by the order of her slot's draws
                    mx, my = self.mother_xy(ev, m / 60, i, st.ewes)
                    self.assertLess(math.hypot(x - mx, (y - my) / 1.6), 0.06, (d, m, who["id"]))
                    self.assertEqual(y > events.wall_y(x), my > events.wall_y(mx), (d, m, who["id"]))
                    self.assertIn(who["pose"], ("stand", "graze", "suckle", "lie"))

    @staticmethod
    def mother_xy(ev, t, i, ewes):
        flock = ev.sheep(t, (), ewes)
        # the bare flock is sorted by y; find slot i's by recomputing with only her marked
        marked = list(ewes) if ewes else [None] * 4
        marked[i] = dict(size=1.0, mark=True)
        for x, y, f, g, size, view, who in ev.sheep(t, (), marked):
            if who and who.get("mark"):
                return x, y
        raise AssertionError(flock)


class Kittens(unittest.TestCase):
    def test_kittens_only_in_a_litter_year_and_gone_after_their_weeks(self):
        """Kittens are out only in a litter year (or the one that stayed), from four weeks old, each until its own
        day for a new home at ten to twelve weeks; a litter is 2-4."""
        for Y in YEARS:
            litter, stayed = S.litters(Y)[Y]
            if litter:
                self.assertTrue(S.LITTER_N[0] <= len(litter) <= S.LITTER_N[1])
                self.assertTrue(all(S.KIT_HOME[0] <= k["home"] <= S.KIT_HOME[1] for k in litter))
            for d in (D(Y, 1, 1) + i * DAY for i in range(0, 365, 2)):
                st = story(d, "fair")
                for k in st.kittens:
                    if k["stays"]:
                        continue
                    self.assertTrue(litter and k["id"].startswith(f"{Y}-"), (d, k["id"]))
                    self.assertTrue(S.KIT_OUT <= k["age"] < k["home"], (d, k["id"], k["age"]))
                if not litter:
                    self.assertFalse([k for k in st.kittens if not k["stays"]], d)
        Y, lit = litter_year()
        last = max(k["born"] + k["home"] * DAY for k in lit if not k["stays"])
        self.assertFalse([k for k in story(last, "fair").kittens if not k["stays"]])
        self.assertTrue(story(lit[0]["born"] + 30 * DAY, "fair").kittens)

    def test_kittens_keep_their_identity(self):
        Y, lit = litter_year()
        d0 = lit[0]["born"] + S.KIT_OUT * DAY
        prev = None
        for i in range(60):
            ks = {k["id"]: k for k in story(d0 + i * DAY, "fair").kittens}
            if prev:
                for k in set(ks) & set(prev):
                    self.assertEqual((ks[k]["coat"], ks[k]["seed"], ks[k]["born"]), (prev[k]["coat"], prev[k]["seed"], prev[k]["born"]))
                    self.assertGreater(ks[k]["size"], prev[k]["size"] - 1e-12)
                self.assertTrue(set(ks) <= set(prev), "a kitten came back")
            prev = ks

    def test_kittens_stay_near_the_cat(self):
        """Settled kittens are within a few of her lengths of the cat; while she is indoors or by the lamp, and from a
        little after dark, they are in."""
        Y, lit = litter_year()
        for age in (30, 45, 60):
            d = lit[0]["born"] + age * DAY
            day = Day(d, weather="fair")
            self.assertTrue(day.story.kittens)
            shown = 0
            for m in range(0, 1440, 3):
                fr = lp.Frame(day, m, SCALE)
                kits = fr.kittens_now()
                spot, prev, since, seeds, _ = day.events.cat_at(m)
                if since < 14:
                    continue                    # following her from her last place
                k = 30 * fr.s * fr.persp(fr.H * 0.75) * 0.36
                dark = [mm for mm in range(m - since, m + 1) if day.sun_alt[mm] < -4]
                if spot in ("inside", "lamp") or (dark and m - dark[0] >= 14):
                    self.assertEqual(kits, [], (d, m, spot))
                    continue
                if dark:
                    continue                    # dusk: on their way in by the door
                here = fr.cat_spot(spot, seeds)
                for kit, x, y, pose, f in kits:
                    shown += 1
                    self.assertLess(math.hypot(x - here[0], y - here[3]), 8 * k, (d, m, spot, kit["id"]))
            self.assertGreater(shown, 20, (d, "kittens never out"))

    def test_kept_in_by_a_wet_spell(self):
        """On a day after a wet spell (synthetic weather) the young kittens stay indoors all day."""
        found = 0
        for Y in YEARS:
            lit = S.litters(Y)[Y][0]
            if not lit:
                continue
            for i in range(S.KIT_OUT, S.KIT_HOME[0]):
                d = lit[0]["born"] + i * DAY
                st = story(d)
                if st.kittens_in:
                    h = S.History("synthetic", None, TZ, LAT, LON, d)
                    self.assertGreaterEqual(h(d - DAY).rain, S.KIT_WET[1])
                    if found < 2:
                        day = Day(d, weather="synthetic")
                        for m in range(0, 1440, 20):
                            young = [k for k, *_ in lp.Frame(day, m, SCALE).kittens_now() if k["age"] < S.KIT_HOME[1]]
                            self.assertEqual(young, [], (d, m))
                    found += 1
        self.assertGreater(found, 0, "no wet spell in any litter's weeks")


class PaleSeal(unittest.TestCase):
    def test_her_knob_is_empty_while_she_is_away_and_hers_again_after(self):
        """While the pale cow is away no seal 0 hauls out or swims; the first days she is back she is on her knob at
        the day's low waters; a day before she leaves is as phase 4 had it."""
        trips = [(Y, S.seal_year(Y)) for Y in YEARS if S.seal_year(Y)]
        self.assertGreaterEqual(len(trips), 4)
        for Y, (left, back) in trips[:2]:
            self.assertTrue(30 <= (back - left).days <= 46 and 9 <= left.month <= 10)
            for d in (left, left + 10 * DAY, back - DAY):
                day = Day(d, weather="fair")
                self.assertTrue(day.story.pale["away"])
                n0 = day.sea.low_water(0)[0]
                for m in range(0, 1440, 2):
                    if d == left and day.sea.low_water(m)[0] == n0:
                        continue                # the low water of the night before she went
                    self.assertFalse([s for s in day.sea.seals_at(m, self.wl(day, m)) if s[0] == 0], (d, m))
                    sw = day.sea.seal_swim_at(m, self.wl(day, m))
                    self.assertFalse(sw and sw[0] == 0, (d, m))
            day = Day(back, weather="fair")
            self.assertTrue(day.story.pale["sure"])
            out = [m for m in range(0, 1440, 2) if any(s[0] == 0 and s[1] == "rock" for s in day.sea.seals_at(m, self.wl(day, m)))]
            self.assertTrue(out, back)
            # before she goes: the story leaves her alone
            day = Day(left - 5 * DAY, weather="fair")
            self.assertIsNone(day.story.pale)

    def test_a_haul_out_across_midnight_is_one(self):
        """On the nights she leaves and comes back, the low water across midnight is the same on both sides."""
        for Y in YEARS:
            trip = S.seal_year(Y)
            if not trip:
                continue
            for d in trip:
                a, b = Day(d - DAY, weather="fair"), Day(d, weather="fair")
                self.assertEqual(a.sea.low_water(1439)[0], b.sea.low_water(0)[0])
                wl = self.wl(a, 1439)
                self.assertEqual([s[:2] for s in a.sea.seals_at(1439, wl)], [s[:2] for s in b.sea.seals_at(0, wl)], d)
                self.assertEqual(a.sea.pale(1439), b.sea.pale(0), d)

    @staticmethod
    def wl(day, m):
        return (float(day.tide[min(m, 1440)]) - 0.5) * wt.TR


class Reference(unittest.TestCase):
    def test_reference_mode_has_no_lives(self):
        for d in (D(S.LIVES_FROM, 5, 20), D(S.LIVES_FROM, 10, 5)):
            day = Day(d, weather="synthetic", reference=True)
            st = day.story
            self.assertIsInstance(st, S.NoStory)
            self.assertFalse(st.lambs or st.ewes or st.kittens or st.kittens_in or st.pale)
            self.assertIsNone(day.sea.pale())
            self.assertEqual(lp.Frame(day, 720, SCALE).kittens_now(), [])
            live = Day(d, weather="synthetic").story
            self.assertTrue(live.lambs or live.pale)

    def test_deterministic(self):
        for d in (D(S.LIVES_FROM, 5, 20), D(S.LIVES_FROM + 1, 6, 20), D(S.LIVES_FROM, 10, 5)):
            a, b = story(d), story(d)
            for k in ("lambs", "ewes", "kittens", "kittens_in", "pale", "sold"):
                self.assertEqual(getattr(a, k), getattr(b, k), (d, k))


if __name__ == "__main__":
    unittest.main()
