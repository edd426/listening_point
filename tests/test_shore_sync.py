#!/usr/bin/env python3
"""Offline tests for tools/shore_sync.py: this Mac's copy of the shore, and what nightly.py renders again.

usage: /usr/bin/python3 -m unittest tests.test_shore_sync      (from the repo root; standard library only)

Every request goes to a mock of GitHub's contents API on 127.0.0.1, run in a thread, holding a shore made
by the kit itself on its synthetic reference set (shorekit/tests/support.py). The Keychain and
notifications are faked by replacing subprocess.run inside listener.py (whose key helper sync reuses),
which also records every argv, so the tests can show the key is never on a command line, in a file or in
output. Nothing reaches the network, the real Keychain or ~/Library.
"""
import base64
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "shorekit", "tests"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)
import listener  # noqa: E402
import shore_sync  # noqa: E402
import support as K  # noqa: E402  (the kit's synthetic reference set and fixture objects)
from shorekit.ledger import Shore, ledger_bytes, ledger_sha256, load_shore  # noqa: E402
from shorekit.manifest import manifest_from_obj  # noqa: E402

KEY = "github_pat_TESTONLY_" + uuid.uuid4().hex     # a made-up key; never a real one
CET = dt.timezone(dt.timedelta(hours=1))
NOW = dt.datetime(2026, 11, 3, 21, 15, 0, tzinfo=CET)
DAY1, DAY2, DAY3 = "2026-11-02T04:30:00Z", "2026-11-03T04:30:00Z", "2026-11-03T15:00:00Z"
PREFIX = "/repos/edd426/shore/contents/"


def closed_port_url():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


class MockShore:
    """GETs of the contents API: raw files and folder listings, each with an ETag and 304 on If-None-Match."""

    def __init__(self, key):
        self.key = key
        self.files = {}
        self.requests = []
        self.status = None              # answer every request with this status instead
        self.lock = threading.Lock()
        mock_gh = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def answer(self, status, body=b"", etag=None, ctype="application/json"):
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                if etag:
                    self.send_header("ETag", etag)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                url = urllib.parse.urlsplit(self.path)
                with mock_gh.lock:
                    mock_gh.requests.append({"path": url.path, "query": url.query,
                                             "headers": {k.lower(): v for k, v in self.headers.items()}})
                if (self.headers.get("Authorization") != "Bearer " + mock_gh.key
                        or self.headers.get("X-GitHub-Api-Version") != "2022-11-28"):
                    return self.answer(401, b'{"message":"Bad credentials"}')
                if mock_gh.status:
                    return self.answer(mock_gh.status, b'{"message":"forced"}')
                if not url.path.startswith(PREFIX) or urllib.parse.parse_qs(url.query).get("ref") != ["main"]:
                    return self.answer(404, b'{"message":"Not Found"}')
                path = urllib.parse.unquote(url.path[len(PREFIX):])
                with mock_gh.lock:
                    files = dict(mock_gh.files)
                if path in files:
                    if self.headers.get("Accept") != "application/vnd.github.raw+json":
                        return self.answer(415, b'{"message":"want raw"}')
                    body, ctype = files[path], "application/vnd.github.raw+json"
                else:
                    names = sorted(p[len(path) + 1:] for p in files if p.startswith(path + "/") and "/" not in p[len(path) + 1:])
                    if not names:
                        return self.answer(404, b'{"message":"Not Found"}')
                    body = json.dumps([{"name": n, "path": f"{path}/{n}", "type": "file", "size": len(files[f"{path}/{n}"])}
                                       for n in names]).encode()
                    ctype = "application/json"
                etag = 'W/"%s"' % hashlib.sha1(body).hexdigest()
                if self.headers.get("If-None-Match") == etag:
                    return self.answer(304, etag=etag)
                self.answer(200, body, etag, ctype)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, args=(0.02,), daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def publish(self, shore, objects=None):
        """Put a kit Shore's ledger and objects where the carrier mirrors them."""
        with self.lock:
            self.files["ledger/ledger.json"] = ledger_bytes(shore.events)
            for oid, m in (objects or shore.manifests).items():
                self.files[f"ledger/objects/{oid}.json"] = m.canonical

    def gets(self, path):
        return [r for r in self.requests if r["path"] == PREFIX + path]


def landed(*names):
    """A kit Shore with the fixture objects accepted one a day, the way the carrier lands them."""
    shore = Shore(K.reference())
    for oid in names:
        at = DAY1 if oid.startswith("2026-11-02") else DAY2
        shore.accept(manifest_from_obj(K.fixture_obj(oid)), at, at, "world-1", "0" * 40)
    return shore


FIRST = ("2026-11-02-cairn", "2026-11-02-flag")
MORE = FIRST + ("2026-11-03-shell", "2026-11-03-log")


class SyncTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shore-sync-test-")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        self.cache = shore_sync.cache_dir(self.home)
        shutil.copytree(K.reference_dir(), shore_sync.reference_dir(self.cache))
        self.gh = MockShore(KEY)
        self.addCleanup(self.gh.close)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.key = KEY
        self.calls = []
        self.notifications = []
        self.outputs = []
        for target, name, value in [(listener.subprocess, "run", self.fake_run), (listener, "_now", lambda: NOW),
                                    # a test that forgot --home or --api still cannot touch the real ones
                                    (listener, "HOME", os.path.join(self.tmp, "no-such-home")),
                                    (shore_sync, "HOME", os.path.join(self.tmp, "no-such-home")),
                                    (listener, "API", closed_port_url())]:
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)

    def fake_run(self, args, **kw):
        self.calls.append((list(args), dict(kw)))
        if args[0] == listener.SECURITY:
            if self.key is None:
                return subprocess.CompletedProcess(args, 44, b"", b"")
            if "-w" in args:
                return subprocess.CompletedProcess(args, 0, (self.key + "\n").encode(), b"")
            return subprocess.CompletedProcess(args, 0, None, None)
        if args[0] == listener.OSASCRIPT:
            self.notifications.append(args[-1])
            return subprocess.CompletedProcess(args, 0, None, None)
        raise AssertionError(f"unexpected subprocess {args[0]}")

    def sync(self, *extra, api=None, force=True):
        argv = ["--home", self.home, "--api", api or self.gh.url, "--json"] + (["--force"] if force else []) + list(extra)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = shore_sync.main(argv)
        self.outputs += [out.getvalue(), err.getvalue()]
        return code, json.loads(out.getvalue()), err.getvalue()

    def state(self):
        with open(os.path.join(self.cache, "sync.json")) as f:
            return json.load(f)

    def cached(self):
        with open(os.path.join(self.cache, "ledger.json"), "rb") as f:
            return f.read()

    def replayed(self):
        return load_shore(K.reference(), os.path.join(self.cache, "ledger.json"), os.path.join(self.cache, "objects"))


class FetchTest(SyncTestCase):
    def test_new_objects_are_fetched_checked_and_kept(self):
        shore = landed(*FIRST)
        self.gh.publish(shore)
        code, r, err = self.sync()
        self.assertEqual(code, 0, r)
        self.assertEqual(r["message"], "ledger 2 events (+2), 2 live, 2 new objects")
        self.assertIn("shore: ledger 2 events (+2)", err)
        self.assertEqual(self.cached(), ledger_bytes(shore.events))
        for oid in FIRST:
            with open(os.path.join(self.cache, "objects", oid + ".json"), "rb") as f:
                self.assertEqual(f.read(), shore.manifests[oid].canonical)
        self.assertEqual([a.id for a in self.replayed().live], list(FIRST))
        st = self.state()
        self.assertEqual(st["ledger"], {"events": 2, "sha256": ledger_sha256(shore.events), "live": 2, "misfits": 0})
        self.assertEqual(st["reference"]["digest"], K.reference().digest)
        self.assertIsNone(st["error"])
        self.assertTrue(st["etag"].startswith('W/"'))
        self.assertTrue(shore_sync.ready(self.cache))
        # every request: raw media type, the API version, the key in the Authorization header, the main branch
        for q in self.gh.requests:
            self.assertEqual(q["headers"]["authorization"], "Bearer " + KEY)
            self.assertEqual(q["query"], "ref=main")
        # the next day's ledger: only the new objects are fetched
        more = landed(*MORE)
        self.gh.publish(more)
        code, r, _ = self.sync()
        self.assertEqual((code, r["message"]), (0, "ledger 4 events (+2), 4 live, 2 new objects"))
        self.assertEqual(len(self.gh.gets("ledger/objects/2026-11-02-cairn.json")), 1)

    def test_an_unchanged_ledger_answers_304(self):
        self.gh.publish(landed(*FIRST))
        self.sync()
        before = len(self.gh.requests)
        code, r, _ = self.sync()
        self.assertEqual((code, r["message"]), (0, "unchanged (2 events)"))
        q = self.gh.gets("ledger/ledger.json")[-1]
        self.assertEqual(q["headers"]["if-none-match"], self.state()["etag"])
        self.assertEqual(q["headers"]["accept"], "application/vnd.github.raw+json")
        self.assertEqual(len(self.gh.requests) - before, 2, "the ledger and the lamp folder, both 304; no object")
        # a cache that lost its ledger asks again without the ETag
        os.remove(os.path.join(self.cache, "ledger.json"))
        code, r, _ = self.sync()
        self.assertEqual((code, r["message"]), (0, "ledger 2 events (+2), 2 live, 0 new objects"))
        self.assertNotIn("if-none-match", self.gh.gets("ledger/ledger.json")[-1]["headers"])

    def test_at_most_hourly_unless_forced(self):
        self.gh.publish(landed(*FIRST))
        self.assertEqual(self.sync(force=False)[0], 0)
        n = len(self.gh.requests)
        code, r, err = self.sync(force=False)
        self.assertEqual(code, 0)
        self.assertTrue(r["message"].startswith("not due"))
        self.assertEqual((len(self.gh.requests), err), (n, ""), "no request, and nothing in the log")
        st = self.state()
        st["last_ok_unix"] -= 3601
        st["last_attempt_unix"] -= 3601
        shore_sync.save_state(self.cache, st)
        self.sync(force=False)
        self.assertGreater(len(self.gh.requests), n)
        # offline: tried again after ten minutes, not every run
        api = closed_port_url()
        st = self.state()
        st["last_ok_unix"] -= 7200
        shore_sync.save_state(self.cache, st)
        self.assertEqual(self.sync(api=api, force=False)[0], 0, "last tried just now")
        st["last_attempt_unix"] -= 601
        shore_sync.save_state(self.cache, st)
        self.assertEqual(self.sync(api=api, force=False)[0], 2)

    def test_no_ledger_yet(self):
        code, r, _ = self.sync()
        self.assertEqual((code, r["message"]), (0, "no ledger in the repository yet"))
        self.assertFalse(shore_sync.ready(self.cache))

    def test_no_reference_set_yet(self):
        shutil.rmtree(shore_sync.reference_dir(self.cache))
        self.gh.publish(landed(*FIRST))
        code, r, _ = self.sync()
        self.assertEqual(code, 2)
        self.assertIn("no reference set yet", r["message"])
        self.assertEqual(self.gh.requests, [], "nothing to check against, so nothing is fetched")


class RefuseTest(SyncTestCase):
    def setUp(self):
        SyncTestCase.setUp(self)
        self.good = landed(*FIRST)
        self.gh.publish(self.good)
        self.assertEqual(self.sync()[0], 0)
        self.kept = self.cached()

    def refused(self, text):
        code, r, err = self.sync()
        self.assertEqual(code, 3, r)
        self.assertIn(text, r["message"])
        self.assertIn("refused the shore's ledger", err)
        self.assertEqual(self.cached(), self.kept, "the last good ledger stays")
        self.assertTrue(self.replayed().live, "and still replays, objects and all")
        self.assertIn(text, self.state()["error"])
        return r

    def test_a_tampered_object_is_refused(self):
        more = landed(*MORE)
        self.gh.publish(more)
        bad = more.manifests["2026-11-03-shell"].canonical.replace(b'"x":2600', b'"x":2601')
        self.gh.files["ledger/objects/2026-11-03-shell.json"] = bad
        self.refused("objects/2026-11-03-shell.json does not hash to the sha256 the ledger names for it")
        self.assertFalse(os.path.exists(os.path.join(self.cache, "objects", "2026-11-03-shell.json")))
        self.assertEqual(len(self.notifications), 1)
        self.refused("does not hash")
        self.assertEqual(len(self.notifications), 1, "told once for each ledger refused")
        # a ledger and object swapped together cannot pass either: the sha256 is the object's identity, and
        # the kit judges what it describes
        self.gh.publish(more)
        self.assertEqual(self.sync()[0], 0)

    def test_a_tampered_cached_object_is_fetched_again(self):
        path = os.path.join(self.cache, "objects", "2026-11-02-flag.json")
        with open(path, "wb") as f:
            f.write(b"{}")
        self.gh.publish(landed(*MORE))
        code, r, _ = self.sync()
        self.assertEqual((code, r["message"]), (0, "ledger 4 events (+2), 4 live, 3 new objects"))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), self.good.manifests["2026-11-02-flag"].canonical)

    def test_a_shrinking_ledger_is_refused(self):
        self.gh.files["ledger/ledger.json"] = ledger_bytes(self.good.events[:1])
        self.refused("its ledger has 1 events, fewer than the 2 this Mac holds: it dropped some")
        self.gh.files["ledger/ledger.json"] = ledger_bytes([])
        self.refused("fewer than the 2 this Mac holds")
        del self.gh.files["ledger/ledger.json"]
        self.refused("the repository has no ledger, and this Mac holds one")

    def test_a_changed_event_is_refused(self):
        events = [dict(e) for e in landed(*MORE).events]
        events[1]["lands"] = "2026-11-02T05:00:00Z"
        self.gh.files["ledger/ledger.json"] = ledger_bytes(events)
        self.refused("its ledger changes event 2, which this Mac already holds")

    def test_a_ledger_the_kit_does_not_replay_is_refused(self):
        events = self.good.events + [{"seq": 3, "event": "sea", "at": DAY3, "takes": ["2026-11-09-gone"]}]
        self.gh.files["ledger/ledger.json"] = ledger_bytes(events)
        self.refused("the kit refuses its ledger: E_LEDGER seq 3: the sea takes 2026-11-09-gone, which is not on the shore")
        self.gh.files["ledger/ledger.json"] = b'{"events":[1],"shore_ledger":1}'
        self.refused("its ledger does not parse")

    def test_a_sea_event_is_accepted(self):
        more = landed(*MORE)
        self.gh.publish(more)
        self.assertEqual(self.sync()[0], 0)
        self.kept = self.cached()
        # the owner's veto of the cairn takes the shell resting on it; a world (and this Mac) sees one sea event
        sea = more.veto("2026-11-02-cairn", DAY3)
        self.assertEqual(sea, {"seq": 5, "event": "sea", "at": DAY3, "takes": ["2026-11-02-cairn", "2026-11-03-shell"]})
        # one that would leave the shell floating is refused
        events = [dict(e) for e in more.events]
        events[4]["takes"] = ["2026-11-02-cairn"]
        self.gh.files["ledger/ledger.json"] = ledger_bytes(events)
        self.refused("leaves 2026-11-03-shell, which rests on it")
        self.gh.publish(more)
        code, r, _ = self.sync()
        self.assertEqual((code, r["message"]), (0, "ledger 5 events (+1), 2 live, 0 new objects"))
        self.assertEqual([a.id for a in self.replayed().live], ["2026-11-02-flag", "2026-11-03-log"])
        self.assertEqual(sorted(self.replayed().taken), ["2026-11-02-cairn", "2026-11-03-shell"])
        self.assertNotIn(b"veto", self.cached())


class OfflineTest(SyncTestCase):
    def test_offline_keeps_the_last_good_ledger(self):
        self.gh.publish(landed(*FIRST))
        self.assertEqual(self.sync()[0], 0)
        kept, ok = self.cached(), self.state()["last_ok"]
        self.gh.publish(landed(*MORE))
        code, r, err = self.sync(api=closed_port_url())
        self.assertEqual(code, 2)
        self.assertTrue(r["message"].startswith("kept the last good ledger: offline"), r)
        self.assertEqual(self.cached(), kept)
        self.assertTrue(shore_sync.ready(self.cache))
        st = self.state()
        self.assertEqual(st["last_ok"], ok)
        self.assertIn("offline", st["error"])
        for status in (500, 401):
            self.gh.status = status
            code, r, _ = self.sync()
            self.assertEqual(code, 2, status)
            self.assertEqual(self.cached(), kept)
        self.gh.status = None
        self.key = None
        code, r, _ = self.sync()
        self.assertEqual(code, 2)
        self.assertIn("no key in the Keychain", r["message"])
        self.key = KEY
        code, r, _ = self.sync()
        self.assertEqual((code, r["message"]), (0, "ledger 4 events (+2), 4 live, 2 new objects"))
        self.assertIsNone(self.state()["error"])


class LampTest(SyncTestCase):
    def test_lit_days_on_the_shore_are_added_to_the_lamp_state(self):
        paths = listener.Paths(self.home)
        listener.write_json(paths.lamp, {"version": 1, "lit": {"2026-11-01": "2026-11-01T20:00:00+01:00"}})
        for d in ("2026-11-01", "2026-11-02", "2026-11-03", "2026-08-01"):
            self.gh.files[f"listener/lamp/{d}.json"] = json.dumps({"date": d, "lit": True}).encode()
        self.gh.files["listener/lamp/notes.txt"] = b"not a lamp"
        code, r, _ = self.sync()
        self.assertEqual(code, 0)
        self.assertTrue(r["message"].endswith("; lamp lit on 2026-11-02, 2026-11-03"), r)
        with open(paths.lamp) as f:
            lamp = json.load(f)
        self.assertEqual(lamp, {"version": 1, "lit": {"2026-11-01": "2026-11-01T20:00:00+01:00",    # never changed
                                                      "2026-11-02": "2026-11-02T12:00:00+01:00",    # an earlier day: from dusk
                                                      "2026-11-03": "2026-11-03T21:15:00+01:00"}})  # today: from now
        self.assertEqual(oct(os.stat(paths.lamp).st_mode & 0o777), "0o600")
        before = len(self.gh.requests)
        self.assertEqual(self.sync()[1]["message"], "no ledger in the repository yet")
        self.assertEqual(self.gh.gets("listener/lamp")[-1]["headers"]["if-none-match"], self.state()["lamp_etag"])
        self.assertEqual(len(self.gh.requests) - before, 2)
        # a lamp folder that cannot be read does not undo a good ledger
        self.gh.publish(landed(*FIRST))
        self.gh.files["listener/lamp/2026-11-04.json"] = b"{}"
        with mock.patch.object(shore_sync, "lit_dates", side_effect=listener.Failed("broken")):
            code, r, _ = self.sync()
        self.assertEqual(code, 0)
        self.assertTrue(r["message"].endswith("; the lamp folder could not be read (broken)"), r)
        self.assertTrue(shore_sync.ready(self.cache))


class RerenderTest(unittest.TestCase):
    """What nightly.py renders again: each day folder's record against the cache now."""

    def test_records_and_the_first_stale_minute(self):
        shore = landed(*FIRST)
        tz = "Europe/Budapest"
        d = dt.date(2026, 11, 2)
        empty = shore_sync.EMPTY
        rec = shore_sync.day_record(shore.events, None)
        self.assertEqual(rec, {"version": 1, "events": 2, "sha256": ledger_sha256(shore.events), "lamp": None})
        # both landed 04:30 UTC, 05:30 in Budapest that day: minute 330 onward, and all of the next day
        self.assertEqual(shore_sync.stale_from(d, tz, empty, shore.events), 330)
        self.assertEqual(shore_sync.stale_from(d + dt.timedelta(1), tz, empty, shore.events), 0)
        self.assertIsNone(shore_sync.stale_from(d - dt.timedelta(1), tz, empty, shore.events), "the day before is untouched")
        self.assertIsNone(shore_sync.stale_from(d, tz, rec, shore.events), "nothing new")
        # the sea takes one at 15:00 UTC on the 3rd: from 16:00 local; an add's moment is its `lands`
        shore.accept(manifest_from_obj(K.fixture_obj("2026-11-03-shell")), DAY2, DAY2, "world-1", "0" * 40)
        shore.veto("2026-11-02-flag", DAY3)
        later = shore_sync.day_record(shore.events[:3], None)
        self.assertEqual(shore_sync.stale_from(d + dt.timedelta(1), tz, later, shore.events), 16 * 60)
        self.assertEqual(shore_sync.stale_from(d + dt.timedelta(1), tz, rec, shore.events), 5 * 60 + 30)
        # a record the ledger does not extend: all of the day
        forged = dict(rec, sha256="0" * 64)
        self.assertEqual(shore_sync.stale_from(d, tz, forged, shore.events), 0)
        self.assertEqual(shore_sync.stale_from(d, tz, dict(rec, events=9), shore.events), 0)
        # the clock minutes are the renderer's, DST included (2026-10-25: 03:00 CEST is 02:00 CET)
        utc = shore_sync.instants(dt.date(2026, 10, 25), tz)
        self.assertEqual((utc[0], utc[120], utc[180], utc[1439]),
                         ("2026-10-24T22:00:00Z", "2026-10-25T00:00:00Z", "2026-10-25T02:00:00Z", "2026-10-25T22:59:00Z"))

    def test_the_lamp(self):
        rec = dict(shore_sync.EMPTY)
        self.assertIsNone(shore_sync.lamp_from(rec, None))
        self.assertEqual(shore_sync.lamp_from(rec, "2026-11-02T19:04:11+01:00"), "2026-11-02T19:04:11+01:00")
        lit = dict(rec, lamp="2026-11-02T19:04:11+01:00")
        self.assertIsNone(shore_sync.lamp_from(lit, "2026-11-02T19:04:11+01:00"))
        self.assertEqual(shore_sync.lamp_from(lit, "2026-11-02T18:30:00+00:00"), "2026-11-02T19:04:11+01:00")
        self.assertEqual(shore_sync.lamp_from(lit, "2026-11-02T18:00:00+00:00"), "2026-11-02T18:00:00+00:00",
                         "the earlier moment, whatever the offsets")
        self.assertEqual(shore_sync.lamp_from(lit, None), "2026-11-02T19:04:11+01:00")
        tmp = tempfile.mkdtemp(prefix="shore-rec-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "shore.json")
        self.assertEqual(shore_sync.read_record(path), shore_sync.EMPTY, "frames from before the shore")
        shore_sync.write_record(path, lit)
        self.assertEqual(shore_sync.read_record(path), lit)
        with open(path, "w") as f:
            f.write('{"version": 1}')
        self.assertEqual(shore_sync.read_record(path), shore_sync.EMPTY)


class WiringTest(unittest.TestCase):
    def read(self, *p):
        with open(os.path.join(ROOT, *p)) as f:
            return f.read()

    def test_nightly_drains_then_syncs_then_renders_with_the_shore_and_the_lamp(self):
        src = self.read("tools", "nightly.py")
        main = src[src.index("def main():"):]
        order = [main.index(s) for s in ("drain_listener()", "fcntl.flock", "ensure_reference()", "sync_shore()",
                                         "refresh_shore(days, d)", "render(days, dt.date.fromisoformat(a.date)",
                                         'render(days, today, range(max(0, m_now - 2), 1440)')]
        self.assertEqual(order, sorted(order))
        self.assertIn('[sys.executable, "-I", SYNC]', src)
        self.assertEqual(src.count("+ shore_args()"), 2, "every render: the day's spans and the hourly frames")
        self.assertIn('["--shore", SHORE] if shore_sync.ready(SHORE) else []) + ["--lamp", LAMP]', src)

    def test_install_copies_the_kit_and_the_helper_kicks_a_stale_sync_on_wake(self):
        self.assertRegex(self.read("tools", "install.sh"), r"rsync -a --delete --exclude __pycache__ renderers tools shorekit ")
        swift = self.read("tools", "live_wallpaper.swift")
        wake = swift[swift.index("NSWorkspace.didWakeNotification"):]
        wake = wake[:wake.index("\n}\n")]
        self.assertIn("if shoreSyncStale() { live.kick() }", wake)
        self.assertIn('"last_attempt_unix"', swift)
        self.assertIn("Library/Application Support/The Listening Point/shore/sync.json", swift)
        self.assertEqual(shore_sync.cache_dir(listener.HOME), os.path.join(listener.HOME, "shore"))


class KeyTest(SyncTestCase):
    def test_key_never_in_argv_files_or_output(self):
        listener.write_json(listener.Paths(self.home).lamp, {"version": 1, "lit": {}})
        self.gh.files["listener/lamp/2026-11-03.json"] = b'{"date":"2026-11-03","lit":true}\n'
        self.gh.publish(landed(*FIRST))
        self.sync()                                         # sent, with new objects and a lamp
        self.sync()                                         # 304
        self.gh.publish(landed(*MORE))
        self.gh.files["ledger/objects/2026-11-03-log.json"] = b"{}"
        self.sync()                                         # refused, with a notification
        self.sync(api=closed_port_url())                    # offline
        self.key = "github_pat_REVOKED"
        self.sync()                                         # 401
        self.key = KEY
        self.sync("status")
        reads = [c for c in self.calls if c[0][0] == listener.SECURITY and "-w" in c[0]]
        self.assertTrue(reads, "the witness is not vacuous: the key was read from the Keychain...")
        self.assertEqual(reads[0][0], [listener.SECURITY, "find-generic-password", "-s", "listening-point-github",
                                       "-a", "listener", "-w"])
        self.assertTrue(any(q["headers"].get("authorization") == "Bearer " + KEY for q in self.gh.requests),
                        "...and reached the server")
        self.assertTrue(self.notifications)
        for argv, kw in self.calls:
            for a in argv:
                self.assertNotIn(KEY, a)
                self.assertNotIn("REVOKED", a)
            self.assertNotIn("env", kw)
            self.assertNotIn("input", kw)
        seen = 0
        for folder, _, names in os.walk(self.tmp):
            for name in names:
                with open(os.path.join(folder, name), "rb") as f:
                    data = f.read()
                self.assertNotIn(KEY.encode(), data, name)
                self.assertNotIn(base64.b64encode(KEY.encode()), data, name)
                self.assertNotIn(b"REVOKED", data, name)
                seen += 1
        self.assertGreaterEqual(seen, 6)
        for text in self.outputs:
            self.assertNotIn(KEY, text)
            self.assertNotIn("REVOKED", text)
        self.assertTrue(any("shore: " in t for t in self.outputs), "the log lines were captured")
        self.assertFalse(any(KEY in v for v in os.environ.values()))


if __name__ == "__main__":
    unittest.main()
