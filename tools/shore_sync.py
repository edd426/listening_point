#!/usr/bin/env python3
"""Keep this Mac's copy of the shore: the ledger and its objects, checked by the kit before they are used.

tools/nightly.py runs this on every pass (it does nothing more than once an hour unless --force), then
passes the cache to the renderer as --shore and the lamp-state file as --lamp. It never renders: when the
shore changes, nightly.py sees it in each day's record (`day_record`, `stale_from`) and renders again the
frames from the moment the change shows (an object's `lands`, the time the sea took something) onward.

- Fetch. GET ledger/ledger.json from the private shore repository (default edd426/shore) with the raw
  media type and If-None-Match, so most runs get a 304; then each object the cache does not already
  hold, ledger/objects/<id>.json, whose bytes must hash to the sha256 the ledger names for it.
- Verify. The new ledger must extend the cached one event for event (the cache only grows: a ledger that
  drops or changes a known event is refused; what the sea takes arrives as a new `sea` event, an append
  like any other), and the kit must replay all of it against this Mac's own reference set.
- Keep. Only a ledger that passes replaces the cached one; until then, offline or refused, the last good
  ledger stays in use. New objects are written before the ledger, each file atomically, so a renderer
  reading the cache at any moment sees a whole, consistent shore.
- Lamp. A file at listener/lamp/<date>.json in the repository means that day is lit (however it got
  there). Any lit day missing from the local lamp-state file (listener/lamp.json, which the renderer reads)
  is added, from the moment it was seen (or noon, for an earlier day): the window shows from dusk.

usage: shore_sync.py [--home DIR] [--api URL] [--force] [--json] [status]

Files, under --home (default ~/Library/Application Support/The Listening Point):
  shore/ledger.json, shore/objects/<id>.json   the last good shore, in the kit's layout
  shore/reference/r3/                          this Mac's own reference set (nightly.py builds it once)
  shore/sync.json                              when it last tried and last reached the repository, the
                                               ETags, the ledger it holds, and any trouble
  listener/lamp.json                           the lamp state, shared with tools/listener.py

The access key is the controls' own (tools/listener.py reads it from the Keychain, into memory only; it is
never in argv, the environment, a file or a log). Exit status: 0 done, unchanged or not due; 1 a problem
with the local setup; 2 kept the last good ledger (offline, the key, the server, or no reference set yet);
3 refused the repository's ledger (it shrank, changed, or does not replay), or failed.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # the repo, or the installed src/: shorekit/ sits beside tools/
for _p in (HERE, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import listener  # noqa: E402  (the key, the API client, the lamp-state file and the file helpers)
from shorekit.errors import ShoreError  # noqa: E402
from shorekit.ledger import (LEDGER_MAX_BYTES, OBJECT_MAX_BYTES, Shore, ledger_bytes, ledger_sha256,  # noqa: E402
                             parse_ledger, read_bounded)
from shorekit.manifest import parse_manifest  # noqa: E402
from shorekit.reference import load_reference  # noqa: E402
from shorekit.strictjson import canonical  # noqa: E402

HOME = listener.HOME
REFERENCE = "r3"                # the reference set this Mac judges with, and renders against (r2: v3 grass;
                                # r3: the same pictures, and each condition's cast shadow, for kit 1.3.0)
LEDGER = "ledger/ledger.json"   # in the shore repository: the carrier's mirror of its ledger
OBJECTS = "ledger/objects"
LAMPS = "listener/lamp"
EVERY = 3600                    # at most hourly...
RETRY = 600                     # ...and after a failed try, not again for ten minutes
BUDGET = 60.0                   # seconds for the whole sync (nightly.py allows 120)
LAMP_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})\.json")


def log(*a):
    """One line on stderr (nightly.py sends it to the render log). Never pass the key."""
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + "shore: " + " ".join(str(x) for x in a), file=sys.stderr, flush=True)


class Refused(Exception):
    """The repository's ledger cannot be used; the last good one stays."""


# ---------------------------------------------------------------------------------------------- files

def cache_dir(home):
    return os.path.join(home, "shore")


def reference_dir(cache):
    return os.path.join(cache, "reference", REFERENCE)


def lamp_file(home):
    return listener.Paths(home).lamp


def ready(cache):
    """Whether the renderer can draw this cache: a reference set and a ledger that sync has accepted."""
    return os.path.isdir(reference_dir(cache)) and os.path.isfile(os.path.join(cache, "ledger.json"))


def cache_events(cache):
    """The cached ledger's events (sync only ever writes one that replays), or [] when there is none."""
    path = os.path.join(cache, "ledger.json")
    if not os.path.exists(path):
        return []
    return parse_ledger(read_bounded(path, LEDGER_MAX_BYTES, "E_LEDGER", "ledger.json"))


def load_state(cache):
    return listener.read_json(os.path.join(cache, "sync.json"), {})


def save_state(cache, state):
    state["version"] = 1
    listener.write_json(os.path.join(cache, "sync.json"), state)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_object(cache, oid):
    try:
        with open(os.path.join(cache, "objects", oid + ".json"), "rb") as f:
            return f.read(OBJECT_MAX_BYTES + 1)
    except FileNotFoundError:
        return None


# -------------------------------------------------------------------------------------------- verify

def verify(cache, ref, data, fetch):
    """Check the repository's ledger bytes against the cache and the kit. `fetch(id)` returns an object's
    bytes from the repository. Returns (events, new objects {id: bytes}, the replayed Shore); raises Refused."""
    try:
        events = parse_ledger(data)
    except ShoreError as e:
        raise Refused("its ledger does not parse: " + e.text)
    try:
        old = cache_events(cache)
    except ShoreError:
        old = []        # a cached ledger that no longer parses is no reference: the new one must replay
    if len(events) < len(old):
        raise Refused("its ledger has %d events, fewer than the %d this Mac holds: it dropped some" % (len(events), len(old)))
    for a, b in zip(old, events):
        if canonical(a) != canonical(b):
            raise Refused("its ledger changes event %d, which this Mac already holds" % a["seq"])
    staged = {}
    for ev in events:
        if ev["event"] != "add":
            continue
        have = read_object(cache, ev["id"])
        if have is not None and sha256(have) == ev["sha256"]:
            continue
        got = fetch(ev["id"])
        if len(got) > OBJECT_MAX_BYTES:
            raise Refused("objects/%s.json is over %d bytes" % (ev["id"], OBJECT_MAX_BYTES))
        if sha256(got) != ev["sha256"]:
            raise Refused("objects/%s.json does not hash to the sha256 the ledger names for it" % ev["id"])
        staged[ev["id"]] = got
    shore = Shore(ref, os.path.join(cache, "objects"))
    try:
        for ev in events:
            m = parse_manifest(staged[ev["id"]]) if ev["event"] == "add" and ev["id"] in staged else None
            shore.apply(ev, m)
        shore.finish()
    except ShoreError as e:
        raise Refused("the kit refuses its ledger: " + e.line())
    return events, staged, shore


def keep(cache, events, staged):
    """Write the new objects, then the ledger: whoever reads the cache meanwhile sees a whole shore."""
    folder = os.path.join(cache, "objects")
    for oid, data in sorted(staged.items()):
        listener.write_atomic(os.path.join(folder, oid + ".json"), data)
    data = ledger_bytes(events)
    path = os.path.join(cache, "ledger.json")
    with contextlib.suppress(OSError), open(path, "rb") as f:
        if f.read(len(data) + 1) == data:
            return
    listener.write_atomic(path, data)


# ---------------------------------------------------------------------------------------------- lamp

def merge_lamp(paths, dates, now):
    """Add every lit day in `dates` that the local lamp state lacks: from `now` if it is today, else from
    noon that day (the window only shows from dusk). Never removes one. Returns the dates added."""
    today = now.date()
    oldest = (today - dt.timedelta(days=listener.KEEP_DAYS)).isoformat()
    with listener.locked(paths.lock):
        lamp = listener.load_lamp(paths)
        added = []
        for d in sorted(dates):
            day = dt.date.fromisoformat(d)
            if d in lamp["lit"] or d < oldest or day > today + dt.timedelta(days=1):
                continue
            when = now if day == today else dt.datetime.combine(day, dt.time(12, 0), now.tzinfo)
            lamp["lit"][d] = listener.iso(when)
            added.append(d)
        if added:
            lamp["version"] = 1
            lamp["lit"] = listener.prune_days(lamp["lit"], today)
            listener.write_json(paths.lamp, lamp)
    return added


def lit_dates(body):
    """The dates of a listing of listener/lamp/: every <date>.json file there means that day is lit."""
    try:
        entries = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise listener.Failed("the lamp folder's listing is not JSON")
    if not isinstance(entries, list):
        raise listener.Failed("the lamp folder's listing is not a list")
    out = set()
    for e in entries:
        m = LAMP_NAME.fullmatch(e.get("name", "")) if isinstance(e, dict) and isinstance(e.get("name"), str) else None
        if m and e.get("type") == "file":
            with contextlib.suppress(ValueError):
                dt.date.fromisoformat(m.group(1))
                out.add(m.group(1))
    return out


# ---------------------------------------------------------------------------------------------- sync

def due(state, force):
    if force:
        return True
    t = time.time()
    return t - state.get("last_ok_unix", 0) >= EVERY and t - state.get("last_attempt_unix", 0) >= RETRY


def sync(home, api=None, force=False):
    """One sync. Returns (exit status, a one-line summary)."""
    paths = listener.Paths(home)
    cache = cache_dir(home)
    listener.ensure_dir(cache)
    fd = listener.try_lock(os.path.join(cache, ".sync.lock"))
    if fd is None:
        return 0, "another sync is running"
    try:
        return _sync(paths, cache, api, force)
    finally:
        os.close(fd)


def _sync(paths, cache, api, force):
    now = listener._now()
    state = load_state(cache)
    if not due(state, force):
        return 0, "not due (last reached the shore at %s)" % state.get("last_ok", "never")
    state.update(last_attempt=listener.iso(now), last_attempt_unix=int(time.time()))
    save_state(cache, state)
    if not os.path.isdir(reference_dir(cache)):
        state["error"] = "no reference set yet at %s (nightly.py builds it)" % reference_dir(cache)
        save_state(cache, state)
        return 2, state["error"]
    try:
        cfg, _ = listener.load_config(paths, api)
        gh = listener.GitHub(cfg, listener.read_key(cfg), time.monotonic() + BUDGET)
        code, summary = fetch_ledger(gh, cache, state)
    except listener.Refused as e:
        state["error"] = str(e)
        save_state(cache, state)
        return 1, str(e)
    except (listener.Transient, listener.AuthError, listener.Failed) as e:
        state["error"] = str(e)
        save_state(cache, state)
        return 2, "kept the last good ledger: %s" % e
    state.update(last_ok=listener.iso(now), last_ok_unix=int(time.time()))
    if code == 0:
        state["error"] = None
    try:
        summary += fetch_lamp(gh, paths, state, now)
    except (listener.Transient, listener.AuthError, listener.Failed) as e:
        summary += "; the lamp folder could not be read (%s)" % e
    save_state(cache, state)
    return code, summary


def held(cache):
    """How many events the cached ledger holds (0 when it is missing or no longer parses)."""
    try:
        return len(cache_events(cache))
    except ShoreError:
        return 0


def fetch_ledger(gh, cache, state):
    path = os.path.join(cache, "ledger.json")
    have = os.path.exists(path)
    status, headers, body = gh.get_raw(LEDGER, etag=state.get("etag") if have else None, limit=LEDGER_MAX_BYTES)
    if status == 304:
        return 0, "unchanged (%s events)" % (state.get("ledger") or {}).get("events", 0)
    before = held(cache)
    if status == 404 and not before:
        return 0, "no ledger in the repository yet"
    if status == 404:
        return refuse(cache, state, "the repository has no ledger, and this Mac holds one: it dropped everything", "")
    if status != 200:
        listener.classify(status, headers)
    if len(body) > LEDGER_MAX_BYTES:
        return refuse(cache, state, "its ledger is over %d bytes" % LEDGER_MAX_BYTES, "")

    def fetch(oid):
        s, h, data = gh.get_raw("%s/%s.json" % (OBJECTS, oid), limit=OBJECT_MAX_BYTES)
        if s == 404:
            raise Refused("its ledger names %s, and the repository has no object for it" % oid)
        if s != 200:
            listener.classify(s, h)
        return data
    try:
        ref = load_reference(reference_dir(cache))
    except ShoreError as e:
        raise listener.Failed("this Mac's reference set does not load: " + e.line())
    try:
        events, staged, shore = verify(cache, ref, body, fetch)
    except Refused as e:
        return refuse(cache, state, str(e), sha256(body))
    keep(cache, events, staged)
    state["etag"] = headers.get("ETag") if headers else None
    state["ledger"] = {"events": len(events), "sha256": ledger_sha256(events), "live": len(shore.live),
                       "misfits": len(shore.misfits)}
    state["reference"] = {"id": ref.id, "digest": ref.digest}
    state.pop("refused", None)
    return 0, "ledger %d events (+%d), %d live, %d new object%s%s" % (
        len(events), len(events) - before, len(shore.live), len(staged), "" if len(staged) == 1 else "s",
        ", %d misfits" % len(shore.misfits) if shore.misfits else "")


def refuse(cache, state, why, digest):
    """Keep the last good ledger, and tell the owner once for each ledger refused."""
    state["error"] = "refused the shore's ledger: " + why
    if (state.get("refused") or {}).get("sha256") != digest:
        state["refused"] = {"sha256": digest, "at": listener.iso(listener._now())}
        listener.notify("The shore's ledger was refused; this Mac keeps its last good copy. See the render log.")
    log(state["error"])
    return 3, state["error"]


def fetch_lamp(gh, paths, state, now):
    status, headers, body = gh.get_listing(LAMPS, etag=state.get("lamp_etag"))
    if status == 304:
        return ""
    if status == 404:
        dates = set()
    elif status == 200:
        dates = lit_dates(body)
    else:
        listener.classify(status, headers)
    added = merge_lamp(paths, dates, now)
    state["lamp_etag"] = headers.get("ETag") if headers and status == 200 else None
    return "; lamp lit on %s" % ", ".join(added) if added else ""


# ----------------------------------------------------------------------- what to render again (nightly.py)

def day_record(events, lamp):
    """What a day's frames are rendered with: the ledger (its length and sha256) and the lamp's lit time."""
    return {"version": 1, "events": len(events), "sha256": ledger_sha256(events), "lamp": lamp}


EMPTY = day_record([], None)      # frames rendered before there was a shore, or without one


def write_record(path, rec):
    listener.write_json(path, rec)


def read_record(path):
    rec = listener.read_json(path, None)
    if not rec or rec.get("version") != 1 or set(rec) != set(EMPTY):
        return dict(EMPTY)
    return rec


def instants(day, tzname):
    """The UTC time of each clock minute 0-1439 of local `day`, as the renderer's Day counts them."""
    tz = ZoneInfo(tzname)
    mid = dt.datetime.combine(day, dt.time(0, 0), tz)
    return [(mid + dt.timedelta(minutes=m)).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            for m in range(1440)]


def stale_from(day, tzname, old, events):
    """The first clock minute of `day` whose frame may differ from one rendered with record `old`, now the
    shore holds `events`; None when none can. Each event since `old` shows from its own moment on: an
    add from `lands`, a sea event from `at`. A record this ledger does not extend means all of the day."""
    n = old["events"]
    if n > len(events) or ledger_sha256(events[:n]) != old["sha256"]:
        return 0
    times = [ev["lands"] if ev["event"] == "add" else ev["at"] for ev in events[n:]]
    if not times:
        return None
    first = min(times)
    for m, t in enumerate(instants(day, tzname)):
        if t >= first:
            return m
    return None


def lamp_from(old, lamp):
    """When the lamp's change shows, if it changed: the earlier of the two lit times (None if unchanged)."""
    if old["lamp"] == lamp:
        return None
    times = [t for t in (old["lamp"], lamp) if t]
    return min(times, key=lambda t: dt.datetime.fromisoformat(t)) if times else None


# ---------------------------------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(prog="shore_sync.py", description="Keep this Mac's copy of the shore.")
    ap.add_argument("--home", default=HOME, help="where listener.json, listener/ and shore/ live")
    ap.add_argument("--api", default=None, help="API base URL (default: listener.json's api, else %s)" % listener.API)
    ap.add_argument("--force", action="store_true", help="sync now, even if the last one was less than an hour ago")
    ap.add_argument("--json", action="store_true", help="print one JSON object")
    ap.add_argument("cmd", nargs="?", default="sync", choices=("sync", "status"))
    a = ap.parse_args(argv)
    home = os.path.abspath(os.path.expanduser(a.home))
    if a.cmd == "status":
        st = load_state(cache_dir(home))
        print(json.dumps(st, sort_keys=True) if a.json else "\n".join("%s: %s" % kv for kv in sorted(st.items())))
        return 0
    try:
        code, summary = sync(home, a.api, a.force)
    except Exception as e:      # noqa: BLE001 - report, never break the render job
        import traceback
        traceback.print_exc()
        code, summary = 3, "shore_sync.py failed: %s" % type(e).__name__
    if a.json:
        print(json.dumps({"ok": code == 0, "code": code, "message": summary}))
    if not summary.startswith("not due"):
        log(summary)
    return code


if __name__ == "__main__":
    sys.exit(main())
