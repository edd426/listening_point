#!/usr/bin/env python3
"""Offline tests for tools/listener.py, the owner controls (light the lamp, leave a note).

usage: /usr/bin/python3 -m unittest tests.test_listener      (from the repo root; standard library only)

Every request goes to a mock of GitHub's contents API on 127.0.0.1, run in a thread. The Keychain and
notifications are faked by replacing subprocess.run inside listener.py, which also records every argv, so
the tests can show the key is never on a command line, in a file or in output. Nothing reaches the network,
the real Keychain or ~/Library.
"""
import base64
import contextlib
import datetime as dt
import io
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import unicodedata
import unittest
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import listener  # noqa: E402

KEY = "github_pat_TESTONLY_" + uuid.uuid4().hex     # a made-up key; never a real one
CET = dt.timezone(dt.timedelta(hours=1))
NOW = dt.datetime(2026, 11, 2, 19, 4, 11, tzinfo=CET)
LAMP_PATH = "listener/lamp/2026-11-02.json"
LAMP_BYTES = b'{"date":"2026-11-02","lit":true}\n'
CONFIG = {"recipients": [{"key": "world-a", "label": "World A"}, {"key": "world-b", "label": "World B"}]}


def closed_port_url():
    """An address on this machine where nothing listens: connection refused, like being offline."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


class MockGitHub:
    """Just enough of the contents API: create-only PUT (422 when the file exists), raw GET, repo GET."""

    def __init__(self, key):
        self.key = key
        self.files = {}
        self.requests = []
        self.put_status = None          # answer every PUT with this status instead
        self.extra_headers = {}         # sent with every answer
        self.drop_responses = 0         # store the next N files, then hang up without answering
        self.expiration = "2027-10-30 12:00:00 UTC"
        self.lock = threading.Lock()
        mock_gh = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def answer(self, status, body=b"", ctype="application/json"):
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                if mock_gh.expiration:
                    self.send_header("github-authentication-token-expiration", mock_gh.expiration)
                for k, v in mock_gh.extra_headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def setup_request(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                url = urllib.parse.urlsplit(self.path)
                with mock_gh.lock:
                    mock_gh.requests.append({"method": self.command, "path": url.path, "query": url.query,
                                             "headers": {k.lower(): v for k, v in self.headers.items()},
                                             "body": body})
                ok = (self.headers.get("Authorization") == "Bearer " + mock_gh.key
                      and self.headers.get("X-GitHub-Api-Version") == "2022-11-28")
                if not ok:
                    self.answer(401, b'{"message":"Bad credentials"}')
                return ok, url, body

            def do_PUT(self):
                ok, url, body = self.setup_request()
                if not ok:
                    return
                if mock_gh.put_status:
                    self.answer(mock_gh.put_status, b'{"message":"forced"}')
                    return
                m = re.fullmatch(r"/repos/edd426/shore/contents/(.+)", url.path)
                if not m:
                    self.answer(404, b'{"message":"Not Found"}')
                    return
                path = urllib.parse.unquote(m.group(1))
                obj = json.loads(body)
                assert set(obj) == {"message", "content", "branch"}, obj
                with mock_gh.lock:
                    if path in mock_gh.files:
                        self.answer(422, b'{"message":"Invalid request.\\n\\n\\"sha\\" wasn\'t supplied."}')
                        return
                    mock_gh.files[path] = base64.b64decode(obj["content"])
                    if mock_gh.drop_responses:
                        mock_gh.drop_responses -= 1
                        self.close_connection = True
                        return              # the file landed, but its answer is lost
                self.answer(201, json.dumps({"content": {"path": path}, "commit": {"sha": "0" * 40}}).encode())

            def do_GET(self):
                ok, url, _ = self.setup_request()
                if not ok:
                    return
                if url.path == "/repos/edd426/shore":
                    self.answer(200, b'{"full_name":"edd426/shore","private":true}')
                    return
                m = re.fullmatch(r"/repos/edd426/shore/contents/(.+)", url.path)
                path = urllib.parse.unquote(m.group(1)) if m else None
                if path in mock_gh.files and self.headers.get("Accept") == "application/vnd.github.raw+json":
                    self.answer(200, mock_gh.files[path], "application/vnd.github.raw+json")
                else:
                    self.answer(404, b'{"message":"Not Found"}')

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, args=(0.02,), daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def of(self, method):
        return [r for r in self.requests if r["method"] == method]


class ListenerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="listener-test-")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        self.write_config(CONFIG)
        self.gh = MockGitHub(KEY)
        self.addCleanup(self.gh.close)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.key = KEY                  # what the fake Keychain holds (None: no entry)
        self.calls = []                 # (argv, kwargs) of every subprocess.run
        self.notifications = []
        self.outputs = []
        self.now = NOW
        for target, value in [(listener.subprocess, ("run", self.fake_run)),
                              (listener, ("_now", lambda: self.now)),
                              # a test that forgot --home or --api still cannot touch the real ones
                              (listener, ("HOME", os.path.join(self.tmp, "no-such-home"))),
                              (listener, ("API", closed_port_url()))]:
            p = mock.patch.object(target, value[0], value[1])
            p.start()
            self.addCleanup(p.stop)

    def write_config(self, cfg):
        with open(os.path.join(self.home, "listener.json"), "w") as f:
            json.dump(cfg, f)

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

    def cli(self, *args, text=None, api=None):
        argv = ["--home", self.home, "--api", api or self.gh.url, "--json"] + list(args)
        out, err = io.StringIO(), io.StringIO()
        stdin = io.BytesIO((text or "").encode("utf-8"))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = listener.main(argv, stdin=stdin)
        self.outputs += [out.getvalue(), err.getvalue()]
        return code, json.loads(out.getvalue())

    def outbox(self):
        d = os.path.join(self.home, "listener", "outbox")
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def lamp_state(self):
        with open(os.path.join(self.home, "listener", "lamp.json")) as f:
            return json.load(f)

    def note_files(self):
        return {p: v for p, v in self.gh.files.items() if p.startswith("listener/notes/")}


class LampTest(ListenerTestCase):
    def test_lamp_201_sent(self):
        code, r = self.cli("light")
        self.assertEqual((code, r["result"]), (0, "sent"), r)
        self.assertEqual(self.gh.files, {LAMP_PATH: LAMP_BYTES})
        put, = self.gh.of("PUT")
        self.assertEqual(put["path"], "/repos/edd426/shore/contents/" + LAMP_PATH)
        self.assertEqual(put["headers"]["authorization"], "Bearer " + KEY)
        self.assertEqual(put["headers"]["x-github-api-version"], "2022-11-28")
        body = json.loads(put["body"])
        self.assertEqual(body["message"], "listener: lamp")
        self.assertEqual(body["branch"], "main")
        self.assertNotIn("sha", body)                 # create-only
        self.assertTrue(r["status"]["lamp_lit_today"])
        self.assertEqual(r["status"]["queued"], 0)
        self.assertEqual(self.outbox(), [])
        self.assertIn("2026-11-02", self.lamp_state()["lit"])
        self.assertEqual(r["status"]["last_send_what"], "lamp 2026-11-02")
        # one bit a day: a second press sends nothing
        code, r = self.cli("light")
        self.assertEqual((code, r["result"]), (0, "already"))
        self.assertEqual(len(self.gh.requests), 1)

    def test_lamp_422_already_lit(self):
        self.gh.files[LAMP_PATH] = LAMP_BYTES        # lit from another run whose local record was lost
        code, r = self.cli("light")
        self.assertEqual((code, r["result"]), (0, "already"), r)
        self.assertEqual([q["method"] for q in self.gh.requests], ["PUT", "GET"])
        self.assertEqual(self.outbox(), [])
        self.assertTrue(r["status"]["lamp_lit_today"])
        self.assertIsNone(r["status"]["error"])

    def test_lamp_is_per_local_date(self):
        self.cli("light")
        self.now = NOW + dt.timedelta(days=1)
        code, r = self.cli("light")
        self.assertEqual(r["result"], "sent")
        self.assertIn("listener/lamp/2026-11-03.json", self.gh.files)
        self.assertEqual(sorted(self.lamp_state()["lit"]), ["2026-11-02", "2026-11-03"])


class NoteTest(ListenerTestCase):
    def test_note_sent(self):
        code, r = self.cli("note", "--to", "world-b", text="Saw the boat come in tonight.\n")
        self.assertEqual((code, r["result"]), (0, "sent"), r)
        (path, data), = self.note_files().items()
        m = re.fullmatch(r"listener/notes/2026-11-02-([0-9a-f-]{36})\.json", path)
        self.assertTrue(m, path)
        note = json.loads(data)
        self.assertEqual(set(note), {"id", "opened", "to", "text"})
        self.assertEqual(note, {"id": m.group(1), "opened": "2026-11-02", "to": ["world-b"],
                                "text": "Saw the boat come in tonight."})
        self.assertEqual(json.loads(self.gh.of("PUT")[0]["body"])["message"], "listener: note")
        self.assertEqual(self.outbox(), [])
        self.assertEqual(r["status"]["notes_today"], 1)

    def test_note_recipients(self):
        self.cli("note", "--to", "all", text="one")
        self.cli("note", "--to", "world-b", "--to", "world-a", text="two")
        tos = sorted(json.loads(v)["to"] for v in self.note_files().values())
        self.assertEqual(tos, [["world-a", "world-b"], ["world-a", "world-b"]])   # config order, no repeats
        code, r = self.cli("note", "--to", "nobody", text="three")
        self.assertEqual((code, r["result"]), (1, "refused"))
        self.assertIn("nobody", r["message"])

    def test_note_422_identical_retry_is_sent(self):
        self.gh.drop_responses = 1                     # the PUT lands but its answer never arrives
        code, r = self.cli("note", "--to", "world-a", text="Is anyone there?")
        self.assertEqual((code, r["result"]), (0, "queued"), r)
        self.assertEqual(len(self.note_files()), 1)
        self.assertEqual(len(self.outbox()), 1)
        code, r = self.cli("drain")
        self.assertEqual((code, r["result"]), (0, "drained"), r)
        self.assertEqual([q["method"] for q in self.gh.requests], ["PUT", "PUT", "GET"])
        self.assertEqual(self.outbox(), [])
        self.assertEqual(len(self.note_files()), 1)    # never sent twice
        self.assertIsNotNone(r["status"]["last_send"])
        self.assertIsNone(r["status"]["error"])

    def test_note_422_different_bytes_is_rejected(self):
        code, r = self.cli("note", "--to", "world-a", text="mine", api=closed_port_url())
        self.assertEqual(r["result"], "queued")
        name, = self.outbox()
        with open(os.path.join(self.home, "listener", "outbox", name)) as f:
            path = json.load(f)["path"]
        self.gh.files[path] = b'{"someone":"else"}\n'
        code, r = self.cli("drain")
        self.assertEqual((code, r["result"]), (2, "error"), r)
        self.assertEqual(self.outbox(), [])
        self.assertEqual(os.listdir(os.path.join(self.home, "listener", "rejected")), [name])
        self.assertEqual(self.gh.files[path], b'{"someone":"else"}\n')      # never overwritten
        self.assertIn("different file", r["status"]["error"])
        self.assertEqual(r["status"]["rejected"], 1)


class QueueTest(ListenerTestCase):
    def test_offline_queued_then_drained(self):
        offline = closed_port_url()
        code, r = self.cli("light", api=offline)
        self.assertEqual((code, r["result"]), (0, "queued"), r)
        self.assertTrue(r["status"]["lamp_lit_today"])          # the lamp shows locally at once
        self.assertTrue(r["status"]["lamp_queued"])
        code, r = self.cli("note", "--to", "all", text="Written on the train.", api=offline)
        self.assertEqual((code, r["result"]), (0, "queued"), r)
        self.assertEqual(r["status"]["queued"], 2)
        self.assertIsNone(r["status"]["error"])                 # offline is not an error
        out = os.path.join(self.home, "listener", "outbox")
        self.assertEqual(stat.S_IMODE(os.stat(out).st_mode), 0o700)
        for name in self.outbox():
            self.assertRegex(name, r"^[0-9a-f-]{36}\.json$")    # no temporary files left behind
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(out, name)).st_mode), 0o600)
        for name in os.listdir(os.path.join(self.home, "listener")):
            full = os.path.join(self.home, "listener", name)
            if os.path.isfile(full):
                self.assertEqual(stat.S_IMODE(os.stat(full).st_mode), 0o600, name)
        self.assertEqual(self.gh.requests, [])
        # back online: nightly.py's drain sends both
        code, r = self.cli("drain")
        self.assertEqual((code, r["result"], r["message"]), (0, "drained", "2 sent"), r)
        self.assertEqual(self.outbox(), [])
        self.assertIn(LAMP_PATH, self.gh.files)
        self.assertEqual(len(self.note_files()), 1)
        self.assertEqual(r["status"]["queued"], 0)
        self.assertFalse(r["status"]["lamp_queued"])
        self.assertIsNotNone(r["status"]["last_send"])
        code, r = self.cli("drain")
        self.assertEqual(r["result"], "empty")

    def test_server_error_stays_queued(self):
        self.gh.put_status = 503
        code, r = self.cli("light")
        self.assertEqual((code, r["result"]), (0, "queued"), r)
        self.assertEqual(len(self.outbox()), 1)
        self.assertEqual(self.notifications, [])
        self.gh.put_status = None
        code, r = self.cli("drain")
        self.assertEqual(r["message"], "1 sent")

    def test_rate_limit_403_is_not_a_key_error(self):
        self.gh.put_status = 403
        self.gh.extra_headers = {"x-ratelimit-remaining": "0"}
        code, r = self.cli("light")
        self.assertEqual(r["result"], "queued")
        self.assertEqual(self.notifications, [])
        self.assertEqual(r["status"]["token"], "present")

    def test_401_and_403_show_an_error_and_keep_the_queue(self):
        for status in (401, 403):
            with self.subTest(status=status):
                shutil.rmtree(os.path.join(self.home, "listener"), ignore_errors=True)
                self.notifications.clear()
                self.gh.files.clear()
                self.key, self.gh.put_status = KEY, None
                if status == 401:
                    self.key = "github_pat_REVOKED"            # the mock refuses it with a real 401
                else:
                    self.gh.put_status = 403
                code, r = self.cli("light")
                self.assertEqual((code, r["result"]), (2, "error"), r)
                self.assertIn(str(status), r["message"])
                self.assertEqual(len(self.outbox()), 1)          # the queue is kept
                self.assertTrue(r["status"]["lamp_lit_today"])
                self.assertEqual(r["status"]["token"], "rejected")
                self.assertIn(str(status), r["status"]["error"])
                code, r = self.cli("note", "--to", "world-a", text="still here")
                self.assertEqual((code, r["result"]), (2, "error"))
                self.assertEqual(len(self.outbox()), 2)
                code, r = self.cli("drain")
                self.assertEqual(code, 2)
                self.assertEqual(len(self.notifications), 1, self.notifications)   # one, not one per try
                self.assertIn(str(status), self.notifications[0])
                # the key is replaced: the next drain sends everything and clears the error
                self.key, self.gh.put_status = KEY, None
                code, r = self.cli("drain")
                self.assertEqual((code, r["message"]), (0, "2 sent"), r)
                self.assertIsNone(r["status"]["error"])
                self.assertEqual(r["status"]["token"], "present")
                self.assertEqual(len(self.notifications), 1)

    def test_missing_key(self):
        self.key = None
        code, r = self.cli("light")
        self.assertEqual((code, r["result"]), (2, "error"))
        self.assertEqual(r["status"]["token"], "missing")
        self.assertEqual(len(self.outbox()), 1)
        self.assertEqual(len(self.notifications), 1)
        self.assertEqual(self.gh.requests, [])

    def test_key_expiry_is_reported(self):
        code, r = self.cli("light")
        self.assertEqual(r["status"]["token_expires"], "2027-10-30")
        self.assertEqual(r["status"]["token"], "present")
        self.assertEqual(r["status"]["token_days_left"], (dt.date(2027, 10, 30) - NOW.date()).days)
        self.gh.expiration = "2026-11-01 09:00:00 +0100"
        self.cli("note", "--to", "world-a", text="x")
        code, r = self.cli("status")
        self.assertEqual(r["status"]["token"], "expired")

    def test_check(self):
        code, r = self.cli("check")
        self.assertEqual((code, r["result"]), (0, "ok"), r)
        self.assertEqual(self.gh.of("GET")[0]["path"], "/repos/edd426/shore")
        self.key = "github_pat_REVOKED"
        code, r = self.cli("check")
        self.assertEqual((code, r["result"]), (2, "error"))
        self.assertIn("401", r["message"])

    def test_malformed_outbox_item_is_set_aside(self):
        out = os.path.join(self.home, "listener", "outbox")
        os.makedirs(out)
        name = str(uuid.uuid4()) + ".json"
        with open(os.path.join(out, name), "w") as f:
            json.dump({"version": 1, "kind": "note", "id": name[:-5], "created": "x",
                       "path": "../../etc/passwd", "body": "x"}, f)
        code, r = self.cli("drain")
        self.assertEqual(self.gh.requests, [])
        self.assertEqual(self.outbox(), [])
        self.assertEqual(os.listdir(os.path.join(self.home, "listener", "rejected")), [name])

    def test_redirect_is_not_followed(self):
        other = MockGitHub(KEY)
        self.addCleanup(other.close)
        self.gh.put_status = 301
        self.gh.extra_headers = {"Location": other.url + "/repos/edd426/shore/contents/" + LAMP_PATH}
        code, r = self.cli("light")
        self.assertEqual(r["result"], "error")
        self.assertEqual(other.requests, [])
        self.assertEqual(len(self.outbox()), 1)

    def test_plain_http_to_another_host_is_refused(self):
        code, r = self.cli("light", api="http://example.invalid")
        self.assertEqual((code, r["result"]), (1, "refused"))
        self.assertEqual([c for c in self.calls if "-w" in c[0]], [])    # the key was never read
        self.assertEqual(self.outbox(), [])


class TextTest(ListenerTestCase):
    def queued_text(self, raw):
        code, r = self.cli("note", "--to", "world-a", text=raw, api=closed_port_url())
        self.assertEqual(r["result"], "queued", r)
        newest = max(self.outbox(), key=lambda n: os.path.getmtime(os.path.join(self.home, "listener", "outbox", n)))
        with open(os.path.join(self.home, "listener", "outbox", newest)) as f:
            return json.loads(json.load(f)["body"])["text"]

    def test_three_notes_a_day(self):
        offline = closed_port_url()
        for i in range(3):
            code, r = self.cli("note", "--to", "world-a", text=f"note {i}", api=offline)
            self.assertEqual((code, r["result"]), (0, "queued"))
        code, r = self.cli("note", "--to", "world-a", text="one too many", api=offline)
        self.assertEqual((code, r["result"]), (1, "refused"), r)
        self.assertIn("3 notes", r["message"])
        self.assertEqual(len(self.outbox()), 3)
        self.assertEqual(r["status"]["notes_today"], 3)
        self.cli("drain")                                       # sent notes still count
        code, r = self.cli("note", "--to", "world-a", text="one too many")
        self.assertEqual(r["result"], "refused")
        self.assertEqual(len(self.note_files()), 3)
        self.now = NOW + dt.timedelta(days=1)                   # a new local day
        code, r = self.cli("note", "--to", "world-a", text="tomorrow's")
        self.assertEqual(r["result"], "sent")

    def test_500_characters(self):
        self.assertEqual(self.queued_text("x" * 500), "x" * 500)
        code, r = self.cli("note", "--to", "world-a", text="x" * 501)
        self.assertEqual((code, r["result"]), (1, "refused"))
        self.assertIn("501", r["message"])
        # counted after NFC: 250 e + combining acute = 500 code points typed, 250 characters kept
        self.assertEqual(self.queued_text("é" * 250), "é" * 250)
        self.assertEqual(len(self.outbox()), 2)

    def test_line_cap_and_empty(self):
        self.assertEqual(self.queued_text("\n".join("abcdefghijkl")), "\n".join("abcdefghijkl"))
        for raw, why in [("\n".join("abcdefghijklm"), "13 lines"), ("   \n\t\n", "empty"), ("\x07\x1b\x00", "empty")]:
            code, r = self.cli("note", "--to", "world-a", text=raw)
            self.assertEqual((code, r["result"]), (1, "refused"), raw)
            self.assertIn(why, r["message"])
        self.assertEqual(len(self.outbox()), 1)

    def test_control_characters_are_stripped(self):
        raw = ("\n\nLine one\x00\x07\x1b[2J\r\nline\ttwo‮ evil⁦\x7f\x85 end   "
               "Café‏﻿\rthree\x0b\x0c\n\n\n")
        text = self.queued_text(raw)
        self.assertEqual(text, "Line one[2J\nline two evil end\nCafé\nthree")
        for ch in text:
            self.assertTrue(ch == "\n" or unicodedata.category(ch) not in ("Cc", "Cf"), repr(ch))


class ConfigTest(ListenerTestCase):
    def test_missing_config_disables_notes_not_the_lamp(self):
        os.remove(os.path.join(self.home, "listener.json"))
        code, r = self.cli("status")
        self.assertIsNone(r["status"]["recipients"])
        self.assertIn("listener.json", r["status"]["config_error"])
        code, r = self.cli("note", "--to", "all", text="hello")
        self.assertEqual((code, r["result"]), (1, "refused"))
        self.assertIn("listener.json", r["message"])
        code, r = self.cli("light")
        self.assertEqual(r["result"], "sent")

    def test_bad_config_is_named(self):
        self.write_config({"recipients": CONFIG["recipients"], "colour": "blue"})
        code, r = self.cli("light")
        self.assertEqual((code, r["result"]), (1, "refused"))
        self.assertIn("colour", r["message"])
        self.write_config({"recipients": [{"key": "All Of Them", "label": "x"}]})
        code, r = self.cli("status")
        self.assertEqual(r["result"], "refused")
        self.assertEqual(self.gh.requests, [])

    def test_status_lists_recipients(self):
        code, r = self.cli("status")
        self.assertEqual(r["status"]["recipients"], CONFIG["recipients"])
        self.assertIsNone(r["status"]["config_error"])
        self.assertEqual((r["status"]["note_max"], r["status"]["notes_per_day"]), (500, 3))

    def test_nightly_drains_every_run(self):
        with open(os.path.join(ROOT, "tools", "nightly.py")) as f:
            src = f.read()
        self.assertIn('"listener.py"', src)
        self.assertRegex(src, r'"drain"')
        main = src[src.index("def main():"):]
        self.assertIn("drain_listener()", main)


class KeyTest(ListenerTestCase):
    def files_without_key(self):
        """Every file under the test folder, asserting none holds the key, plain or base64."""
        seen = []
        for folder, _, names in os.walk(self.tmp):
            for name in names:
                with open(os.path.join(folder, name), "rb") as f:
                    data = f.read()
                seen.append(os.path.join(folder, name))
                self.assertNotIn(KEY.encode(), data, name)
                self.assertNotIn(base64.b64encode(KEY.encode()), data, name)
        return seen

    def test_key_never_in_argv_files_or_output(self):
        # everything that handles the key: sends, a lost answer, offline queueing, a refusal, a check
        self.cli("light")
        self.cli("note", "--to", "all", text="first")
        self.gh.drop_responses = 1
        self.cli("note", "--to", "world-a", text="second")
        self.cli("drain")
        self.now = NOW + dt.timedelta(days=1)
        self.cli("light", api=closed_port_url())
        self.key = "github_pat_REVOKED"
        self.cli("drain")
        self.assertEqual(len(self.outbox()), 1)
        queued_files = self.files_without_key()
        self.key = KEY
        self.cli("drain")
        self.cli("check")
        self.cli("status")
        # the witness is not vacuous: the key was read from the Keychain and reached the server
        reads = [c for c in self.calls if c[0][0] == listener.SECURITY and "-w" in c[0]]
        self.assertTrue(reads)
        self.assertEqual(reads[0][0], [listener.SECURITY, "find-generic-password", "-s", "listening-point-github",
                                       "-a", "listener", "-w"])
        self.assertTrue(any(q["headers"].get("authorization") == "Bearer " + KEY for q in self.gh.requests))
        self.assertTrue(self.notifications)
        for argv, kw in self.calls:
            for a in argv:
                self.assertNotIn(KEY, a)
                self.assertNotIn("REVOKED", a)
            self.assertNotIn("env", kw)                 # children inherit the environment unchanged
            self.assertNotIn("input", kw)
        self.assertIn("outbox", " ".join(queued_files))
        self.assertGreaterEqual(len(self.files_without_key()), 5)
        for text in self.outputs:
            self.assertNotIn(KEY, text)
        self.assertFalse(any(KEY in v for v in os.environ.values()))


if __name__ == "__main__":
    unittest.main()
