#!/usr/bin/env python3
"""Keep the live wallpaper's frames ready on a laptop that sleeps a lot. launchd runs this every
15 minutes while the Mac is awake, and the helper starts it on wake when frames are missing.

- First, every run: sends whatever the menu-bar controls queued while offline (`listener.py drain`).
- Then, once the shore is set up (the controls' key is in the Keychain): at most hourly, fetches and checks
  the shore (`shore_sync.py`), and renders again the frames the shore or the lamp has changed since they
  were made: from an object's landing (or the moment the sea took one) on, and the dark minutes from the
  moment the lamp was lit. Every frame is rendered with the synced cache (--shore) and the lamp (--lamp).
- On power: the rest of today (from the current minute on), then all of tomorrow.
- On battery with at least half a charge: when less than an hour is ready, the next three hours,
  with one worker.
- Frames go straight into DAYS/YYYY-MM-DD as they are made, so the helper can use them at once;
  an interrupted render resumes where it stopped.
- After 18:00 on power, tomorrow is re-rendered if the evening forecast has changed meaningfully.
- Keeps yesterday, today and tomorrow; deletes older days.
- Packs today's on-the-hour frames into the hourly system wallpaper (lock screen, Mission Control,
  Space switches): daily when the helper can clear the wallpaper agent's cache, else monthly. The
  file is replaced in place and WallpaperAgent restarted so it rereads it.

usage: nightly.py [--root DIR] [--force] [--date YYYY-MM-DD] [--jobs N] [--hourly-only]
"""
import argparse
import datetime as dt
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROC = os.path.normpath(os.path.join(HERE, "..", "renderers", "procedural"))
RENDERER = os.path.join(PROC, "listening_point.py")
ROOT = os.path.expanduser("~/Pictures/Wallpapers/The Listening Point")
LOG = os.path.expanduser("~/Library/Logs/listening-point.log")
CACHE = os.path.expanduser("~/Library/Caches/listening-point")
HEIC = "The Listening Point.heic"
PACKER = os.path.join(HERE, "..", "..", "make_h24")
sys.path.insert(0, PROC)
sys.path.insert(1, HERE)

import shore_sync  # noqa: E402  (stdlib and the kit only)

SYNC = os.path.join(HERE, "shore_sync.py")
SHORE = shore_sync.cache_dir(shore_sync.HOME)       # the synced shore, in the kit's layout
LAMP = shore_sync.lamp_file(shore_sync.HOME)        # the lamp state the controls (and sync) keep


def log(*a):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    if os.path.exists(LOG) and os.path.getsize(LOG) > 5e6:
        os.replace(LOG, LOG + ".1")
    with open(LOG, "a") as f:
        f.write(line + "\n")


def power():
    """('ac' | 'battery', percent)."""
    try:
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return "ac", 100
    pct = re.search(r"(\d+)%", out)
    return ("battery" if "Battery Power" in out else "ac"), int(pct.group(1)) if pct else 100


def workers(asked):
    """Two render processes (about 1.2 GB each) when memory is easy, one when the Mac is short of it."""
    try:
        free = int(subprocess.run(["sysctl", "-n", "kern.memorystatus_level"], capture_output=True, text=True, timeout=5).stdout)
    except Exception:
        return 1
    return asked if free >= 45 else 1


def missing(folder, minutes):
    return [m for m in minutes if not os.path.exists(os.path.join(folder, f"{m // 60:02d}{m % 60:02d}.jpg"))]


def render(days, d, minutes, jobs, why):
    folder = os.path.join(days, d.isoformat())
    todo = missing(folder, minutes)
    if not todo:
        return True
    os.makedirs(folder, exist_ok=True)
    t0 = time.time()
    log(f"rendering {len(todo)} frames of {d} ({why})")
    spans = []
    for m in todo:      # contiguous runs, so the renderer can share its keyframes
        if spans and m == spans[-1][1] + 1:
            spans[-1][1] = m
        else:
            spans.append([m, m])
    ok = True
    for a, b in spans:
        cmd = [sys.executable, RENDERER, folder, "--date", d.isoformat(), "--minutes", f"{a}-{b}", "--scale", "0.75",
               "--jobs", str(workers(jobs)), "--cache", CACHE, "--skip-existing", "--quality", "90"] + shore_args()
        with open(LOG, "a") as f:
            r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
        ok = ok and r.returncode == 0
        if r.returncode:
            log(f"render of {d} {a}-{b} failed with exit code {r.returncode}; will retry next run")
    if ok:
        log(f"{d}: {len(todo)} frames in {time.time() - t0:.0f} s")
    return ok


def weather_digest(d):
    """Hourly cloud, rain, snow and fog for date d from the newest forecast, to notice when it changes."""
    import weather
    w = weather.day_weather(d, cache_dir=CACHE)
    a = np.stack([w.cloud_total, np.maximum(w.rain, w.drizzle), w.snow, w.fog]).reshape(4, 24, 60).mean(-1)
    return w.source, w.fetched_at, a.round(2).tolist()


def refresh_tomorrow(days, d, jobs):
    """After 18:00, re-render tomorrow if the evening forecast differs from the one it was made with."""
    folder = os.path.join(days, d.isoformat())
    meta = os.path.join(folder, "weather.json")
    try:
        src, fetched, now = weather_digest(d)
    except Exception as e:
        log(f"forecast check failed: {e}")
        return
    old = json.load(open(meta)) if os.path.exists(meta) else None
    if old and old.get("evening"):
        return
    changed = old is None or np.abs(np.array(old["digest"]) - np.array(now)).max() > 0.3
    if changed and old is not None:
        for n in os.listdir(folder):
            if n.endswith(".jpg"):
                os.remove(os.path.join(folder, n))
        log(f"the forecast for {d} changed; rendering it again")
    json.dump({"digest": now, "source": src, "fetched_at": fetched, "evening": True}, open(meta, "w"))
    if changed:
        render(days, d, range(1440), jobs, "evening forecast")


def note_weather(days, d):
    meta = os.path.join(days, d.isoformat(), "weather.json")
    if not os.path.exists(meta):
        try:
            src, fetched, digest = weather_digest(d)
            os.makedirs(os.path.dirname(meta), exist_ok=True)
            json.dump({"digest": digest, "source": src, "fetched_at": fetched, "evening": dt.datetime.now().hour >= 18},
                      open(meta, "w"))
        except Exception as e:
            log(f"could not note the forecast: {e}")


def prune(days, keep):
    for name in os.listdir(days):
        base = name.lstrip(".").replace(".partial", "")
        try:
            d = dt.date.fromisoformat(base)
        except ValueError:
            continue
        if d not in keep:
            shutil.rmtree(os.path.join(days, name), ignore_errors=True)
            log(f"removed {name}")


def hourly_due(root, today):
    """Rebuild the hourly wallpaper daily when the helper can clear the wallpaper cache behind us,
    else monthly (each version leaves ~0.5 GB of stale bitmaps until tools/clean_wallpaper_cache.py)."""
    path = os.path.join(root, HEIC)
    if not os.path.exists(path):
        return True
    made = dt.date.fromtimestamp(os.path.getmtime(path))
    try:
        ok = open(os.path.join(root, ".cache-clean")).read().startswith("ok")
    except OSError:
        ok = False
    return made != today if ok else made.replace(day=1) != today.replace(day=1)


def refresh_hourly(days, root, today, force=False):
    """Pack today's 24 on-the-hour frames into the system wallpaper (lock screen, Mission Control, Spaces)."""
    if not (force or hourly_due(root, today)):
        return
    folder = os.path.join(days, today.isoformat())
    hours = [h * 60 for h in range(24)]
    if missing(folder, hours):
        os.makedirs(folder, exist_ok=True)
        cmd = [sys.executable, RENDERER, folder, "--date", today.isoformat(), "--hours", "0-23", "--scale", "0.75",
               "--jobs", "1", "--cache", CACHE, "--skip-existing", "--quality", "90"] + shore_args()
        with open(LOG, "a") as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    frames = [os.path.join(folder, f"{h:02d}00.jpg") for h in range(24)]
    if not all(os.path.exists(f) for f in frames):
        log("hourly wallpaper: some on-the-hour frames are missing; will try again")
        return
    path = os.path.join(root, HEIC)
    tmp = path + ".tmp.heic"
    r = subprocess.run([PACKER, tmp] + frames, capture_output=True, text=True)
    if r.returncode or not os.path.exists(tmp):
        log(f"hourly wallpaper: packing failed: {r.stderr.strip()[:200]}")
        return
    os.replace(tmp, path)
    subprocess.run(["killall", "WallpaperAgent"], check=False)
    log(f"hourly wallpaper rebuilt for {today}")


def drain_listener():
    """Send whatever the menu-bar controls left queued (the lamp, notes) while the Mac was offline.
    listener.py keeps its own lock and time budget; this never holds up or breaks a render."""
    listener = os.path.join(HERE, "listener.py")
    if not os.path.exists(listener):
        return
    try:
        with open(LOG, "a") as f:
            subprocess.run([sys.executable, "-I", listener, "drain"], stdin=subprocess.DEVNULL, stdout=f,
                           stderr=subprocess.STDOUT, timeout=90)
    except Exception as e:
        log(f"listener drain failed: {e}")


def shore_args():
    """What the renderer draws the shore and the lamp from: the synced cache, once it has a reference set and
    a ledger sync accepted, and the lamp-state file. Without either the frames are what they always were."""
    return (["--shore", SHORE] if shore_sync.ready(SHORE) else []) + ["--lamp", LAMP]


def shore_on():
    """The shore is set up once the controls' key is in the Keychain (docs/LISTENER.md); until then nightly
    leaves it alone: no reference set, no sync."""
    try:
        cfg, _ = shore_sync.listener.load_config(shore_sync.listener.Paths(shore_sync.HOME))
    except Exception:
        return False
    return shore_sync.listener.key_present(cfg)


def ensure_reference():
    """This Mac's own reference set, which sync replays the ledger against (and the set the owner publishes
    to the shore repository): rendered once, about a minute, into a hidden folder that is renamed into place
    only when it is complete. A failed build waits a day before it is tried again."""
    dst = shore_sync.reference_dir(SHORE)
    if os.path.isdir(dst):
        return
    base, name = os.path.split(dst)
    tmp, failed = os.path.join(base, f".{name}.partial"), os.path.join(base, f".{name}.failed")
    if os.path.exists(failed) and time.time() - os.path.getmtime(failed) < 86400:
        return
    os.makedirs(base, exist_ok=True)
    shutil.rmtree(tmp, ignore_errors=True)
    log(f"building this Mac's shore reference set {name}")
    with open(LOG, "a") as f:
        r = subprocess.run([sys.executable, os.path.join(HERE, "shore_reference.py"), tmp, "--reference", name],
                           stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, timeout=1800)
    if r.returncode == 0:
        os.replace(tmp, dst)
        if os.path.exists(failed):
            os.remove(failed)
    else:
        shutil.rmtree(tmp, ignore_errors=True)
        open(failed, "w").close()
        log(f"the shore reference set failed (exit {r.returncode}); trying again tomorrow")


def sync_shore():
    """Fetch and check the shore (shore_sync.py does nothing more than hourly). It never renders, and a
    failure only means the last good shore stays in use."""
    try:
        with open(LOG, "a") as f:
            subprocess.run([sys.executable, "-I", SYNC], stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT,
                           timeout=120)
    except Exception as e:
        log(f"shore sync failed: {e}")


def dark_minutes(d, tzname, since):
    """The clock minutes of d from `since` on in which the listener's window can show: it follows the
    scene's lights_on, which is nought while the sun is 2 degrees up or more (a degree's margin here)."""
    import astro
    from day import BUDAPEST
    tz = ZoneInfo(tzname)
    mid = dt.datetime.combine(d, dt.time(0, 0), tz)
    local = [mid + dt.timedelta(minutes=m) for m in range(1440)]
    jd = astro.jd_from_unix(np.array([t.astimezone(dt.timezone.utc).timestamp() for t in local]))
    ra, dec, _ = astro.sun_radec(jd)
    alt, _ = astro.altaz(ra, dec, jd, BUDAPEST["lat"], BUDAPEST["lon"])
    alt = alt + astro.refraction(alt)
    return [m for m in range(1440) if local[m] >= since and alt[m] < 3.0]


def refresh_shore(days, d):
    """Delete the frames of d that the shore or the lamp has changed since they were rendered, so render()
    makes them again. Each day folder's shore.json says what its frames were rendered with; it is written
    before they are, so frames are never older than their record."""
    import shore as shore_draw
    from day import BUDAPEST
    folder = os.path.join(days, d.isoformat())
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "shore.json")
    old = shore_sync.read_record(path)
    try:
        events = shore_sync.cache_events(SHORE) if shore_sync.ready(SHORE) else []
    except Exception as e:
        log(f"cannot read the shore cache ({e}); the frames of {d} are left as they are")
        return
    tzname = BUDAPEST["tz"]
    lit = shore_draw.lamp_lit(LAMP, d, ZoneInfo(tzname))
    new = shore_sync.day_record(events, lit.isoformat() if lit else None)
    if new == old:
        return
    stale = set()
    first = shore_sync.stale_from(d, tzname, old, events)
    if first is not None:
        stale.update(range(first, 1440))
    since = shore_sync.lamp_from(old, new["lamp"])
    if since:
        stale.update(dark_minutes(d, tzname, dt.datetime.fromisoformat(since)))
    gone = 0
    for m in sorted(stale):
        f = os.path.join(folder, f"{m // 60:02d}{m % 60:02d}.jpg")
        if os.path.exists(f):
            os.remove(f)
            gone += 1
    shore_sync.write_record(path, new)
    if gone:
        m = min(stale)
        log(f"{d}: the shore or the lamp changed; {gone} frames from {m // 60:02d}:{m % 60:02d} will be rendered again")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--force", action="store_true", help="render the whole plan even on battery")
    ap.add_argument("--date", default=None, help="render just this whole date")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--hourly-only", action="store_true", help="just rebuild the hourly system wallpaper")
    a = ap.parse_args()
    days = os.path.join(a.root, "days")
    os.makedirs(days, exist_ok=True)
    drain_listener()    # first, and on every run, even one that finds another render under way
    lock = open(os.path.join(a.root, ".render.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    try:
        os.nice(10)
    except OSError:
        pass
    now = dt.datetime.now()
    today, tomorrow = now.date(), now.date() + dt.timedelta(days=1)
    if a.hourly_only:
        refresh_hourly(days, a.root, today, force=True)
        return
    if shore_on():      # then the shore: never during a render (this holds the render lock), always before one
        ensure_reference()
        sync_shore()
    for d in ([dt.date.fromisoformat(a.date)] if a.date else [today, tomorrow]):
        refresh_shore(days, d)
    if a.date:
        render(days, dt.date.fromisoformat(a.date), range(1440), a.jobs, "asked for")
        return
    src, pct = power()
    m_now = now.hour * 60 + now.minute
    if src == "ac" or a.force:
        render(days, today, range(max(0, m_now - 2), 1440), a.jobs, "the rest of today")
        note_weather(days, today)
        if now.hour >= 18:
            refresh_tomorrow(days, tomorrow, a.jobs)
        refresh_hourly(days, a.root, today)
        render(days, tomorrow, range(1440), a.jobs, "tomorrow")
        note_weather(days, tomorrow)
    elif pct >= 50:
        # on battery, work in batches: when less than an hour is ready, make the next three
        ahead = os.path.join(days, today.isoformat())
        if missing(ahead, range(max(0, m_now - 2), min(1440, m_now + 60))):
            render(days, today, range(max(0, m_now - 2), min(1440, m_now + 180)), 1, f"next three hours, on battery at {pct}%")
        refresh_hourly(days, a.root, today)
    prune(days, {today - dt.timedelta(days=1), today, tomorrow})


if __name__ == "__main__":
    main()
