#!/usr/bin/env python3
"""What the story shows on each date (v3 phase 5, part 1; story.py): for a year of dates, the day's weather as
the story reads it, whether it was a day for work, and what is on the land the next morning: the wall (whole,
fallen, or how far rebuilt), the branch under the tree, the logs by the shed, driftwood on the shingle, snow
drifted against the walls, and the garden (how far it lags phase 3's calendar).

usage: ./venv/bin/python tools/story_calendar.py [--weather synthetic|fair|auto] [--from 2026-11-01] [--days 365]
                                                 [--changes] [--cache DIR]

Offline: synthetic and fair weather make their own; auto reads only the weather cache. --changes prints only
the dates on which something the story shows changes (and the first), then the totals.
"""
import argparse
import datetime as dt
import os
import sys
import time
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "renderers", "procedural"))
import story as S  # noqa: E402
from day import BUDAPEST  # noqa: E402
from hillside import garden_stage  # noqa: E402


def shows(st, hist, d):
    """What the story shows on date d, as short words (and the garden's lag)."""
    out = []
    w = st.wall
    if w:
        if w["state"] == "fallen":
            out.append(f"wall {w['site']} down")
        else:
            out.append(f"wall {w['site']} {w['built']:.2f}" + (" pile" if w["pile"] > 0 else ""))
    if st.branch:
        out.append(f"branch ({st.branch['age']}d)")
    if st.logs:
        out.append(f"logs {st.logs}")
    if st.driftwood:
        g = st.driftwood[0]["gone"]
        out.append(f"driftwood x{len(st.driftwood)}" + (f" (sea takes it {g // 60:02d}:{g % 60:02d})" if g is not None else ""))
    today = hist(d)
    e, n = st.drift
    if today.known and (today.depth >= 0.005 or today.snow >= 0.05) and (abs(e) + abs(n)) > 2:
        out.append("drifts")
    base = garden_stage(d.timetuple().tm_yday)
    lag = max(abs(getattr(base, f) - getattr(st.garden, f)) for f in ("dug", "sown", "cleared", "rough"))
    if lag > 0.005:
        out.append(f"garden behind {lag:.2f}")
    if st.spade:
        out.append("spade")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weather", default="synthetic", choices=["synthetic", "fair", "auto"])
    ap.add_argument("--from", dest="start", default="2026-11-01")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--changes", action="store_true")
    ap.add_argument("--cache", default=os.path.expanduser("~/Library/Caches/listening-point"))
    a = ap.parse_args()
    d0 = dt.date.fromisoformat(a.start)
    tz, lat, lon = BUDAPEST["tz"], BUDAPEST["lat"], BUDAPEST["lon"]
    totals = dict(days=0, work=0, gale=0, onshore=0, snow=0, wall=0, branch=0, logs=0, driftwood=0, drifts=0, garden=0, spade=0)
    prev, costs = None, []
    print(f"weather {a.weather}; from {d0} for {a.days} days. A date's line is what shows that day (from the days before it);"
          f" 'work' means that day itself was fit for work, so its work shows the next morning.")
    for i in range(a.days):
        d = d0 + dt.timedelta(days=i)
        t = time.perf_counter()
        st = S.Story(SimpleNamespace(date=d, tzname=tz, lat=lat, lon=lon), a.weather, a.cache)
        costs.append((time.perf_counter() - t) * 1000)
        hist = S.History(a.weather, a.cache, tz, lat, lon, d + dt.timedelta(days=1))
        s = hist(d)
        what = shows(st, hist, d)
        wx = "-" if not s.known else (f"gust {s.gust:4.1f} rain {s.rain:4.1f} snow {s.snow:3.1f} lying {100 * s.depth:3.0f}cm "
                                      f"{s.tmin:5.1f}..{s.tmax:4.1f}C" + (" work" if hist.workable(d) else ""))
        totals["days"] += 1
        totals["work"] += hist.workable(d)
        totals["gale"] += s.known and s.gust >= S.GALE
        totals["onshore"] += s.known and s.onshore >= S.ONSHORE
        totals["snow"] += s.known and s.depth >= 0.005
        for k, word in (("wall", "wall"), ("branch", "branch"), ("logs", "logs"), ("driftwood", "driftwood"), ("drifts", "drifts"),
                        ("garden", "garden"), ("spade", "spade")):
            totals[k] += any(x.startswith(word) for x in what)
        key = tuple(x for x in what if not x.startswith(("branch", "garden behind")))
        key += tuple("branch" for x in what if x.startswith("branch"))
        if not a.changes or key != prev or i == 0:
            print(f"{d} {d.strftime('%a')}  {wx:<52s} | {', '.join(what) or '-'}")
        prev = key
    n = totals["days"]
    print(f"\n{n} days: {totals['work']} fit for work ({100 * totals['work'] / n:.0f}%), {totals['gale']} with gusts of"
          f" {S.GALE:.0f} m/s or more, {totals['onshore']} with an onshore blow of {S.ONSHORE:.0f} m/s, {totals['snow']} with snow lying.")
    print("days showing: " + ", ".join(f"{k} {totals[k]}" for k in ("wall", "branch", "logs", "driftwood", "drifts", "spade", "garden")))
    costs.sort()
    print(f"story per date: median {costs[len(costs) // 2]:.1f} ms, max {costs[-1]:.1f} ms (this process, its caches warm as it goes)")


if __name__ == "__main__":
    main()
