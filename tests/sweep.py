#!/usr/bin/env python3
"""Render small frames of random dates and minutes, to find the day the renderer crashes on before the
render job meets it. (2026-11-04: the contrails crashed on one forecast at 09:27, and the job's retry
hid it until the forecast changed.)

usage: ./venv/bin/python tests/sweep.py [--seed N] [--dates 10] [--scale 0.2] [--from 2026-01-01] [--years 6]
       ./venv/bin/python tests/sweep.py --live      today and tomorrow with the live forecast, on the hour

Each date gets made-up weather (`--weather synthetic`: the date decides it, so a failure repeats), four
scattered minutes and one run of six, which crosses a keyframe. Every command is printed; a failure
prints the renderer's last lines and the command that repeats it, and the exit code is the number of
failed commands. Nothing is drawn from a shore.
"""
import argparse
import datetime as dt
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENDERER = os.path.join(ROOT, "renderers", "procedural", "listening_point.py")


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def plan(seed, dates, start, years):
    """[(date, [renderer arguments])]: the same for the same seed."""
    rng = random.Random(seed)
    out = []
    for _ in range(dates):
        d = start + dt.timedelta(days=rng.randrange(int(365.25 * years)))
        times = sorted(rng.sample(range(1440), 4))
        a = rng.randrange(1440 - 6) // 10 * 10 + 7          # six minutes across a ten-minute keyframe
        out.append((d, ["--times", ",".join(hhmm(m) for m in times)]))
        out.append((d, ["--minutes", f"{a}-{a + 5}"]))
    return out


def frames_asked(args):
    kind, value = args
    if kind == "--times":
        return len(value.split(","))
    lo, _, hi = value.partition("-")
    return int(hi) - int(lo) + 1


def run(n, d, args, scale, weather, tmp):
    out = os.path.join(tmp, f"{n:03d}")
    cmd = [sys.executable, RENDERER, out, "--date", d.isoformat(), "--scale", str(scale), "--jobs", "1",
           "--weather", weather, "--cache", os.path.join(tmp, "weather")] + args
    shown = [c for i, c in enumerate(cmd[3:]) if weather == "auto" or "--cache" not in (c, cmd[3:][i - 1])]
    show = " ".join(["./venv/bin/python", os.path.relpath(RENDERER, ROOT), "OUT"] + shown)
    t0 = time.time()
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    frames = [f for f in os.listdir(out) if f.endswith(".jpg") and ".tmp" not in f] if os.path.isdir(out) else []
    want = frames_asked(args)
    ok = r.returncode == 0 and len(frames) == want
    print(f"{'ok  ' if ok else 'FAIL'} {time.time() - t0:5.1f} s  {show}", flush=True)
    if not ok:
        print("     exit code %d, %d of %d frames; the renderer's last lines:" % (r.returncode, len(frames), want))
        for line in r.stdout.splitlines()[-25:]:
            print("     | " + line)
    shutil.rmtree(out, ignore_errors=True)
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None, help="default: today's date, so each day tries new dates")
    ap.add_argument("--dates", type=int, default=10)
    ap.add_argument("--scale", type=float, default=0.2)
    ap.add_argument("--from", dest="start", default="2026-01-01")
    ap.add_argument("--years", type=float, default=6)
    ap.add_argument("--live", action="store_true", help="today and tomorrow with the live forecast, on the hour")
    a = ap.parse_args(argv)
    tmp = tempfile.mkdtemp(prefix="lp-sweep-")
    failed = 0
    try:
        if a.live:
            today = dt.date.today()
            jobs = [(today + dt.timedelta(days=i), ["--hours", "0-23"]) for i in (0, 1)]
            weather = "auto"
            print(f"sweep: today and tomorrow ({today}) with the live forecast, scale {a.scale}", flush=True)
        else:
            seed = a.seed if a.seed is not None else int(dt.date.today().strftime("%Y%m%d"))
            jobs = plan(seed, a.dates, dt.date.fromisoformat(a.start), a.years)
            weather = "synthetic"
            print(f"sweep: seed {seed}, {a.dates} dates, scale {a.scale}", flush=True)
        for n, (d, args) in enumerate(jobs):
            failed += not run(n, d, args, a.scale, weather, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"sweep: {len(jobs) - failed} of {len(jobs)} commands passed", flush=True)
    return failed


if __name__ == "__main__":
    sys.exit(main())
