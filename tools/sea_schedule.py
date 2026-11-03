#!/usr/bin/env python3
"""How often the bay's boats and animals show (v3 phase 4, part 2; seaplan.py): walks every minute of a sample
of dates and counts, per thing, the minutes it is in view, and how many of the things show at once in daylight.

usage: ./venv/bin/python tools/sea_schedule.py [--weather synthetic|fair] [--year 2027] [--days 1,15]

Offline (fair or synthetic weather). Prints a table per date and the totals.
"""
import argparse
import datetime as dt
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "renderers", "procedural"))
from day import Day  # noqa: E402
from seaplan import to_frame  # noqa: E402
from water import TR  # noqa: E402

THINGS = ("ferry", "creel", "yacht", "seals out", "seal in water", "cormorant", "gannets", "dolphins")


def shown(day, m):
    """The things in view at minute m."""
    sp = day.sea
    wl = (float(day.tide[m]) - 0.5) * TR
    out = set()
    f = sp.ferry_at(m)
    if f:
        x, _ = to_frame(f[0], 0, f[1])
        if 0 <= x <= 1 and f[4] < 0.985:
            out.add("ferry")
    c = sp.creel_at(m)
    if c and not (c[0] == "come" and c[2] < 0.35) and not (c[0] == "go" and c[2] > 0.6):
        out.add("creel")              # (out of sight behind the point at the start and end)
    for y in sp.yachts:
        p = sp.yacht_pos(y, m)
        if p and 0 <= to_frame(p[0], 0, p[1])[0] <= 1:
            out.add("yacht")
    seals = sp.seals_at(m, wl)
    if any(s[1] == "rock" for s in seals):
        out.add("seals out")
    if any(s[1] == "water" for s in seals) or sp.seal_swim_at(m, wl):
        out.add("seal in water")
    if sp.cormorant_at(m, wl):
        out.add("cormorant")
    if sp.gannets_at(m):
        out.add("gannets")
    if sp.dolphins_at(m):
        out.add("dolphins")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weather", default="synthetic", choices=["synthetic", "fair"])
    ap.add_argument("--year", type=int, default=2027)
    ap.add_argument("--days", default="1,15")
    a = ap.parse_args()
    dates = [dt.date(a.year, mo, d) for mo in range(1, 13) for d in (int(v) for v in a.days.split(","))]
    tot = {k: 0 for k in THINGS}
    tot_day = {k: 0 for k in THINGS}
    hist = [0] * 5
    daylight = 0
    print(f"weather {a.weather}; minutes in view per day (all 1440 / daylight, sun above -4 deg)")
    print("date        " + " ".join(f"{k[:12]:>12}" for k in THINGS) + "   at once in daylight: 0/1/2/3/4+")
    for d in dates:
        day = Day(d, weather=a.weather)
        row = {k: [0, 0] for k in THINGS}
        h = [0] * 5
        for m in range(1440):
            s = shown(day, m)
            lit = float(day.sun_alt[m]) > -4
            for k in s:
                row[k][0] += 1
                row[k][1] += lit
            if lit:
                h[min(4, len(s))] += 1
        dl = sum(h)
        daylight += dl
        for k in THINGS:
            tot[k] += row[k][0]
            tot_day[k] += row[k][1]
        hist = [p + q for p, q in zip(hist, h)]
        print(f"{d} {d.strftime('%a')} " + " ".join(f"{row[k][0]:>5}/{row[k][1]:<6}" for k in THINGS)
              + "   " + "/".join(f"{100 * v / max(dl, 1):.0f}" for v in h) + " %")
    n = len(dates)
    print(f"{'mean/day':<15}" + " ".join(f"{tot[k] / n:>5.0f}/{tot_day[k] / n:<6.0f}" for k in THINGS))
    print(f"{'% of daylight':<15}" + " ".join(f"{100 * tot_day[k] / daylight:>11.1f}%" for k in THINGS))
    print("daylight minutes showing 0/1/2/3/4+ of them: " + " / ".join(f"{100 * v / daylight:.1f}%" for v in hist))


if __name__ == "__main__":
    main()
