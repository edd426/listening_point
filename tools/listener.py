#!/usr/bin/env python3
"""The owner's two controls for the live wallpaper: light the lamp, and leave a note.

The menu-bar item in tools/live_wallpaper.swift runs this script off its main thread (15 s timeout), and
tools/nightly.py runs `listener.py drain` on every pass, so whatever was queued while the Mac was offline
goes out within about 15 minutes of it coming back. Standard library only; see docs/LISTENER.md.

usage: listener.py [--home DIR] [--api URL] [--json] COMMAND
  light                         light the lamp for today's local date: one bit a day
  note --to KEY [--to KEY ...]  leave a note, its text on stdin (at most 500 characters, 12 lines and
                                3 notes a day); --to all sends it to everyone in listener.json
  drain                         send whatever is queued (nightly.py runs this every time)
  status                        the lamp, the queue, the last send, the key and the recipients
  check                         ask the server whether the key can see the repository

Files, under --home (default ~/Library/Application Support/The Listening Point):
  listener.json                 the local config: recipients, and optionally repo, branch, api, keychain
  listener/lamp.json            the dates the lamp is lit, for the renderer (schema in docs/LISTENER.md)
  listener/outbox/<uuid>.json   items waiting to be sent, each the exact bytes of the file to create
  listener/rejected/            items the server will never take (a different file already at the path)
  listener/state.json           the last send, the last error, the key's expiry, today's note count

The access key is read from the login Keychain (service listening-point-github, account listener) through
/usr/bin/security, into memory only: never into argv, the environment, a file or a log.
Exit status: 0 done or queued, 1 refused (nothing stored), 2 stored but not sent (key or server error),
3 failed.
"""
import argparse
import base64
import contextlib
import datetime as dt
import fcntl
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid

HOME = os.path.expanduser("~/Library/Application Support/The Listening Point")
API = "https://api.github.com"
API_VERSION = "2022-11-28"
REPO = "edd426/shore"
BRANCH = "main"
KEYCHAIN = {"service": "listening-point-github", "account": "listener"}
SECURITY = "/usr/bin/security"
OSASCRIPT = "/usr/bin/osascript"

NOTE_MAX = 500           # characters (Unicode code points after NFC)
NOTE_LINES = 12          # the carrier caps a note at 12 lines; refuse more here rather than lose them there
NOTES_PER_DAY = 3        # per local date; the server-side quota is the same
STDIN_MAX = 64 * 1024
KEEP_DAYS = 60           # lamp dates and note counts older than this are dropped from local state

REQUEST_TIMEOUT = 8.0    # one HTTP request
KEYCHAIN_TIMEOUT = 3.0
SEND_BUDGET = 10.0       # light / note: everything inside the helper's 15 s, start-up included
DRAIN_BUDGET = 45.0      # drain: nightly.py allows 90 s

RECIPIENT_KEY = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
REPO_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
BRANCH_NAME = re.compile(r"[A-Za-z0-9_./-]{1,100}")
ITEM_NAME = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.json")
REMOTE_PATH = re.compile(r"listener/(lamp/\d{4}-\d{2}-\d{2}|notes/\d{4}-\d{2}-\d{2}-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}"
                         r"-[0-9a-f]{4}-[0-9a-f]{12})\.json")
TOKEN_SHAPE = re.compile(r"[\x21-\x7e]{1,512}")
EXPIRY = re.compile(r"(\d{4}-\d{2}-\d{2})")
# Bidirectional formatting characters, the byte-order mark and the line/paragraph separators: invisible, and
# able to make a note read differently from what was typed. (Cc control characters are stripped as a class.)
INVISIBLE = {chr(c) for c in [0x061C, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
                              0x2066, 0x2067, 0x2068, 0x2069, 0xFEFF]}


def _now():
    """The local time, timezone-aware. Tests replace this."""
    return dt.datetime.now().astimezone()


def iso(t):
    return t.isoformat(timespec="seconds")


def log(*a):
    """One line on stderr (nightly.py sends it to the render log). Never pass the key or a note's text."""
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + "listener: " + " ".join(str(x) for x in a), file=sys.stderr, flush=True)


class Refused(Exception):
    """The request was refused before anything was stored."""


class Transient(Exception):
    """Offline, timed out, rate-limited or a server error: keep the item and try again later."""


class AuthError(Exception):
    """The key is missing, refused or cannot see the repository: keep the item, tell the owner once."""


class Rejected(Exception):
    """The server holds a different file at this item's path; it can never be sent."""


class Failed(Exception):
    """Any other answer: keep the item, show the error."""


# ---------------------------------------------------------------------------------------------- files

class Paths:
    def __init__(self, home):
        self.home = home
        self.config = os.path.join(home, "listener.json")
        self.dir = os.path.join(home, "listener")
        self.outbox = os.path.join(self.dir, "outbox")
        self.rejected = os.path.join(self.dir, "rejected")
        self.lamp = os.path.join(self.dir, "lamp.json")
        self.state = os.path.join(self.dir, "state.json")
        self.lock = os.path.join(self.dir, ".lock")
        self.drain_lock = os.path.join(self.dir, ".drain.lock")


def ensure_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)


def write_atomic(path, data):
    """Write bytes to path as mode 0600 via a temporary file in the same folder and a rename."""
    folder = os.path.dirname(path)
    ensure_dir(folder)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def write_json(path, obj):
    write_atomic(path, (json.dumps(obj, indent=1, sort_keys=True) + "\n").encode("utf-8"))


def read_json(path, default):
    try:
        with open(path, "rb") as f:
            obj = json.loads(f.read(1 << 20).decode("utf-8"))
    except FileNotFoundError:
        return default
    except (ValueError, OSError) as e:
        log(f"ignoring unreadable {os.path.basename(path)}: {type(e).__name__}")
        return default
    return obj if isinstance(obj, dict) else default


@contextlib.contextmanager
def locked(path, wait=5.0):
    """An exclusive flock on path, waiting up to `wait` seconds (state changes hold it for milliseconds)."""
    ensure_dir(os.path.dirname(path))
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise Failed("the listener's files are busy; try again")
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)


def try_lock(path):
    """A non-blocking flock: the open fd, or None when another process holds it."""
    ensure_dir(os.path.dirname(path))
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        os.close(fd)
        return None


def canonical(obj):
    """The exact text of a file we create: sorted keys, no spaces, UTF-8, one trailing newline."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def prune_days(mapping, today):
    cut = (today - dt.timedelta(days=KEEP_DAYS)).isoformat()
    return {k: v for k, v in mapping.items() if isinstance(k, str) and k >= cut}


# --------------------------------------------------------------------------------------------- config

def load_config(paths, api_override=None):
    """(config, problem). A missing listener.json is fine for the lamp; notes need its recipients."""
    cfg = {"api": API, "repo": REPO, "branch": BRANCH, "keychain": dict(KEYCHAIN), "recipients": None}
    problem = None
    try:
        with open(paths.config, "rb") as f:
            raw = f.read(65537)
    except FileNotFoundError:
        raw = None
        problem = f"no listener.json in {paths.home} (see docs/LISTENER.md)"
    except OSError as e:
        raise Refused(f"cannot read listener.json: {e.strerror}")
    if raw is not None:
        cfg.update(parse_config(raw))
    if api_override:
        cfg["api"] = api_override
    check_api(cfg["api"])
    return cfg, problem


def parse_config(raw):
    def bad(why):
        return Refused(f"listener.json: {why}")
    if len(raw) > 65536:
        raise bad("larger than 64 KiB")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise bad(f"not valid JSON ({e})")
    if not isinstance(obj, dict):
        raise bad("must be a JSON object")
    known = {"recipients", "repo", "branch", "api", "keychain"}
    unknown = sorted(k for k in obj if k not in known and not k.startswith("_"))
    if unknown:
        raise bad(f"unknown key(s) {', '.join(unknown)} (comments go in keys starting with _)")
    out = {}
    rs = obj.get("recipients")
    if not isinstance(rs, list) or not rs:
        raise bad('"recipients" must be a non-empty list of {"key": ..., "label": ...}')
    seen, recipients = set(), []
    for r in rs:
        if not isinstance(r, dict) or set(r) != {"key", "label"}:
            raise bad('each recipient is exactly {"key": ..., "label": ...}')
        k, label = r["key"], r["label"]
        if not isinstance(k, str) or not RECIPIENT_KEY.fullmatch(k) or k == "all":
            raise bad(f"recipient key {k!r} must be 1-32 of a-z, 0-9 and -, and not 'all'")
        if not isinstance(label, str) or not 1 <= len(label) <= 40 or not label.isprintable():
            raise bad(f"recipient label {label!r} must be 1-40 printable characters")
        if k in seen:
            raise bad(f"recipient key {k!r} appears twice")
        seen.add(k)
        recipients.append({"key": k, "label": label})
    out["recipients"] = recipients
    if "repo" in obj:
        if not isinstance(obj["repo"], str) or not REPO_NAME.fullmatch(obj["repo"]):
            raise bad('"repo" must look like owner/name')
        out["repo"] = obj["repo"]
    if "branch" in obj:
        if not isinstance(obj["branch"], str) or not BRANCH_NAME.fullmatch(obj["branch"]):
            raise bad('"branch" is not a branch name')
        out["branch"] = obj["branch"]
    if "api" in obj:
        if not isinstance(obj["api"], str):
            raise bad('"api" must be a URL')
        out["api"] = obj["api"]
    if "keychain" in obj:
        kc = obj["keychain"]
        if (not isinstance(kc, dict) or set(kc) != {"service", "account"}
                or not all(isinstance(v, str) and 0 < len(v) <= 100 and v.isprintable() for v in kc.values())):
            raise bad('"keychain" must be {"service": ..., "account": ...}')
        out["keychain"] = dict(kc)
    return out


def check_api(api):
    """HTTPS only, except to this machine (the tests' mock server): the key never crosses a network in clear."""
    u = urllib.parse.urlsplit(api)
    if u.scheme == "https" and u.hostname:
        return
    if u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1"):
        return
    raise Refused(f"the API address must be https:// (got {api!r})")


# ------------------------------------------------------------------------------------------- the key

def keychain_args(cfg, secret):
    a = [SECURITY, "find-generic-password", "-s", cfg["keychain"]["service"], "-a", cfg["keychain"]["account"]]
    return a + ["-w"] if secret else a


def key_present(cfg):
    """Whether the Keychain holds the key, without reading it (no -w: attributes only, never the secret)."""
    try:
        r = subprocess.run(keychain_args(cfg, False), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=KEYCHAIN_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def read_key(cfg):
    """The key, into memory only. Raises AuthError when it is missing or malformed."""
    try:
        r = subprocess.run(keychain_args(cfg, True), stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=KEYCHAIN_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        raise AuthError("could not read the key from the Keychain")
    if r.returncode != 0:
        raise AuthError("no key in the Keychain (see docs/LISTENER.md)")
    key = r.stdout.decode("utf-8", "replace").strip()
    if not TOKEN_SHAPE.fullmatch(key):
        raise AuthError("the key in the Keychain is malformed")
    return key


# ------------------------------------------------------------------------------------------- the API

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None     # a 3xx becomes an HTTPError: the key is never sent anywhere else


class GitHub:
    def __init__(self, cfg, key, deadline):
        self.api = cfg["api"].rstrip("/")
        self.repo = cfg["repo"]
        self.branch = cfg["branch"]
        self._key = key
        self.deadline = deadline
        self.expires = None
        handlers = [_NoRedirect()]
        if urllib.parse.urlsplit(self.api).hostname in ("127.0.0.1", "localhost", "::1"):
            handlers.append(urllib.request.ProxyHandler({}))
        self._opener = urllib.request.build_opener(*handlers)

    def __repr__(self):
        return f"GitHub({self.api}, {self.repo})"

    def _request(self, method, url, data=None, accept="application/vnd.github+json"):
        left = self.deadline - time.monotonic()
        if left < 1.0:
            raise Transient("out of time")
        req = urllib.request.Request(url, data=data, method=method)
        req.add_unredirected_header("Authorization", "Bearer " + self._key)
        req.add_header("Accept", accept)
        req.add_header("X-GitHub-Api-Version", API_VERSION)
        req.add_header("User-Agent", "listening-point-listener")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with self._opener.open(req, timeout=min(REQUEST_TIMEOUT, left)) as r:
                status, headers, body = r.status, r.headers, r.read(1 << 20)
        except urllib.error.HTTPError as e:
            status, headers = e.code, e.headers
            try:
                body = e.read(65536)
            except (OSError, http.client.HTTPException):
                body = b""
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            raise Transient(f"offline ({getattr(e, 'reason', None) or type(e).__name__})")
        m = EXPIRY.search(headers.get("github-authentication-token-expiration", "") if headers else "")
        if m:
            self.expires = m.group(1)
        return status, headers, body

    def contents_url(self, path):
        return f"{self.api}/repos/{self.repo}/contents/{urllib.parse.quote(path)}"

    def create(self, path, message, data):
        """PUT a new file (no sha, so it can only create). Returns the HTTP status."""
        body = json.dumps({"message": message, "content": base64.b64encode(data).decode("ascii"),
                           "branch": self.branch}).encode("utf-8")
        status, headers, _ = self._request("PUT", self.contents_url(path), body)
        return status, headers

    def get_raw(self, path):
        url = self.contents_url(path) + "?" + urllib.parse.urlencode({"ref": self.branch})
        status, headers, body = self._request("GET", url, accept="application/vnd.github.raw+json")
        return status, headers, body

    def repo_info(self):
        status, headers, _ = self._request("GET", f"{self.api}/repos/{self.repo}")
        return status, headers


def classify(status, headers):
    """Raise the exception an unsuccessful answer means."""
    h = headers or {}
    if status == 401:
        raise AuthError("the key was refused (401): it may have expired or been revoked")
    if status == 403:
        if h.get("x-ratelimit-remaining") == "0" or h.get("retry-after"):
            raise Transient("rate-limited (403)")
        raise AuthError("the key may not write to the repository (403)")
    if status == 404:
        raise AuthError("the repository is not visible to this key (404)")
    if status in (408, 409, 429) or status >= 500:
        raise Transient(f"the server answered {status}")
    if 300 <= status < 400:
        raise Failed(f"the server redirected ({status}); check the repo name in listener.json")
    raise Failed(f"unexpected answer {status}")


def send(gh, item):
    """Create the item's file. Returns 'sent', or 'already' when the server already holds it."""
    data = item["body"].encode("utf-8")
    status, headers = gh.create(item["path"], f"listener: {item['kind']}", data)
    if status in (200, 201):
        return "sent"
    if status != 422:
        classify(status, headers)
    # 422: a file is already there (we never send a sha). Look at it.
    gstatus, gheaders, existing = gh.get_raw(item["path"])
    if gstatus == 200:
        if existing == data:
            return "already"       # an earlier attempt landed but its answer was lost
        if item["kind"] == "lamp":
            return "already"       # any file at a lamp path means that day is lit
        raise Rejected(f"a different file is already at {item['path']}")
    if gstatus == 404:
        raise Failed("the server refused the file (422)")
    classify(gstatus, gheaders)


# ------------------------------------------------------------------------------------------- the queue

def new_item(kind, path, body, now, item_id=None):
    if not REMOTE_PATH.fullmatch(path):
        raise Failed(f"bad remote path {path}")
    return {"version": 1, "kind": kind, "id": item_id or str(uuid.uuid4()), "created": iso(now), "path": path,
            "body": body}


def put_item(paths, item):
    write_json(os.path.join(paths.outbox, item["id"] + ".json"), item)


def valid_item(name, item):
    if not isinstance(item, dict) or item.get("version") != 1:
        return False
    kind, path = item.get("kind"), item.get("path")
    if kind not in ("lamp", "note") or not isinstance(path, str) or not REMOTE_PATH.fullmatch(path):
        return False
    if not path.startswith("listener/lamp/" if kind == "lamp" else "listener/notes/"):
        return False
    return (isinstance(item.get("id"), str) and item["id"] + ".json" == name
            and isinstance(item.get("body"), str) and isinstance(item.get("created"), str))


def outbox_items(paths):
    """The queued items, oldest first. Unreadable or malformed files are moved to rejected/."""
    try:
        names = os.listdir(paths.outbox)
    except FileNotFoundError:
        return []
    items = []
    for name in names:
        full = os.path.join(paths.outbox, name)
        if name.startswith(".tmp-"):
            with contextlib.suppress(OSError):
                if time.time() - os.path.getmtime(full) > 3600:
                    os.unlink(full)     # left by a process killed mid-write
            continue
        if not ITEM_NAME.fullmatch(name):
            continue
        item = read_json(full, None)
        if item is None and not os.path.exists(full):
            continue                    # sent by another process meanwhile
        if not valid_item(name, item):
            log(f"moving malformed outbox item {name} to rejected/")
            reject_file(paths, name)
            continue
        items.append(item)
    items.sort(key=lambda i: (i["created"], i["id"]))
    return items


def reject_file(paths, name):
    ensure_dir(paths.rejected)
    with contextlib.suppress(FileNotFoundError):
        os.replace(os.path.join(paths.outbox, name), os.path.join(paths.rejected, name))


def remove_item(paths, item):
    with contextlib.suppress(FileNotFoundError):
        os.unlink(os.path.join(paths.outbox, item["id"] + ".json"))


def load_state(paths):
    s = read_json(paths.state, {})
    s.setdefault("version", 1)
    if not isinstance(s.get("notes"), dict):
        s["notes"] = {}
    return s


def load_lamp(paths):
    lamp = read_json(paths.lamp, {})
    if not isinstance(lamp.get("lit"), dict):
        lamp = {"version": 1, "lit": {}}
    return lamp


def record(paths, **changes):
    """Merge changes into state.json under the lock; an `error` of None clears the last error."""
    with locked(paths.lock):
        s = load_state(paths)
        s.update(changes)
        write_json(paths.state, s)
        return s


def notify(message):
    """One macOS notification (message passed as an argument to the script, never spliced into it)."""
    script = ['on run argv', 'display notification (item 1 of argv) with title "The Listening Point"', 'end run']
    args = [OSASCRIPT]
    for line in script:
        args += ["-e", line]
    try:
        subprocess.run(args + [message], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


def set_error(paths, kind, message):
    """Record an error; the first key error of an episode also sends one notification."""
    now = _now()
    with locked(paths.lock):
        s = load_state(paths)
        old = s.get("error") or {}
        same_episode = old.get("kind") == kind
        tell = kind == "auth" and not (same_episode and old.get("notified"))
        s["error"] = {"kind": kind, "message": message, "at": iso(now),
                      "notified": bool(tell or (same_episode and old.get("notified")))}
        s["last_attempt"] = {"at": iso(now), "outcome": message}
        write_json(paths.state, s)
    if tell:
        notify(f"The lamp and notes can't be sent: {message}.")


def drain(paths, cfg, budget, first=None):
    """Send queued items, `first` before the rest. Returns {item id: outcome} for this pass, where an
    outcome is 'sent', 'already', 'queued', 'error' or 'rejected', plus 'busy' when another drain runs."""
    fd = try_lock(paths.drain_lock)
    if fd is None:
        return {"busy": True}
    outcomes = {}
    try:
        deadline = time.monotonic() + budget
        gh = None
        while True:
            pending = [i for i in outbox_items(paths) if i["id"] not in outcomes]
            if not pending:
                break
            pending.sort(key=lambda i: i["id"] != first)
            item = pending[0]
            try:
                if gh is None:
                    if deadline - time.monotonic() < 1.5:
                        raise Transient("out of time")
                    gh = GitHub(cfg, read_key(cfg), deadline)
                outcome = send(gh, item)
            except Transient as e:
                outcomes[item["id"]] = "queued"
                record(paths, last_attempt={"at": iso(_now()), "outcome": str(e)})
                break           # offline or the server is struggling: everything waits for the next pass
            except AuthError as e:
                outcomes[item["id"]] = "error"
                set_error(paths, "auth", str(e))
                break
            except Rejected as e:
                outcomes[item["id"]] = "rejected"
                log(f"{item['kind']} {item['id']}: {e}; moved to rejected/")
                reject_file(paths, item["id"] + ".json")
                set_error(paths, "rejected", str(e))
            except Failed as e:
                outcomes[item["id"]] = "error"
                set_error(paths, "failed", str(e))
            else:
                outcomes[item["id"]] = outcome
                remove_item(paths, item)
                what = "lamp " + item["path"][14:24] if item["kind"] == "lamp" else "note"
                changes = {"last_send": {"at": iso(_now()), "what": what}, "error": None,
                           "last_attempt": {"at": iso(_now()), "outcome": outcome}}
                if gh.expires:
                    changes["token_expires"] = gh.expires
                record(paths, **changes)
                log(f"{what} {outcome}")
        if gh is not None and gh.expires and load_state(paths).get("token_expires") != gh.expires:
            record(paths, token_expires=gh.expires)
    finally:
        os.close(fd)
    return outcomes


# ------------------------------------------------------------------------------------------ the text

def clean_text(raw):
    """NFC, with control and invisible formatting characters removed; tabs become spaces, line breaks
    become \\n, trailing spaces and leading/trailing blank lines go."""
    t = unicodedata.normalize("NFC", raw)
    t = t.replace("\r\n", "\n").replace("\r", "\n").replace(" ", "\n").replace(" ", "\n")
    t = t.replace("\t", " ")
    kept = [ch for ch in t if ch == "\n" or (unicodedata.category(ch) not in ("Cc", "Cs") and ch not in INVISIBLE)]
    lines = [line.rstrip() for line in "".join(kept).split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return unicodedata.normalize("NFC", "\n".join(lines))


def check_note(text):
    if not text.strip():
        raise Refused("the note is empty")
    if len(text) > NOTE_MAX:
        raise Refused(f"the note is {len(text)} characters long; the most is {NOTE_MAX}")
    n = text.count("\n") + 1
    if n > NOTE_LINES:
        raise Refused(f"the note has {n} lines; the most is {NOTE_LINES}")


# -------------------------------------------------------------------------------------------- commands

def status(paths, cfg, problem):
    today = _now().date()
    s = load_state(paths)
    lamp = load_lamp(paths)
    items = outbox_items(paths)
    err = s.get("error") or None
    present = key_present(cfg)
    expires = s.get("token_expires")
    days_left = None
    if isinstance(expires, str):
        with contextlib.suppress(ValueError):
            days_left = (dt.date.fromisoformat(expires) - today).days
    if not present:
        token = "missing"
    elif err and err.get("kind") == "auth":
        token = "rejected"
    elif days_left is not None and days_left < 0:
        token = "expired"
    else:
        token = "present"
    try:
        rejected = len([n for n in os.listdir(paths.rejected) if ITEM_NAME.fullmatch(n)])
    except FileNotFoundError:
        rejected = 0
    last = s.get("last_send") if isinstance(s.get("last_send"), dict) else {}
    lamp_item = any(i["kind"] == "lamp" and i["path"] == lamp_path(today) for i in items)
    return {
        "today": today.isoformat(),
        "lamp_lit_today": today.isoformat() in lamp["lit"],
        "lamp_queued": lamp_item,
        "queued": len(items),
        "rejected": rejected,
        "last_send": last.get("at"),
        "last_send_what": last.get("what"),
        "token": token,
        "token_expires": expires if isinstance(expires, str) else None,
        "token_days_left": days_left,
        "error": err.get("message") if err else None,
        "notes_today": len(s["notes"].get(today.isoformat(), [])),
        "notes_per_day": NOTES_PER_DAY,
        "note_max": NOTE_MAX,
        "note_lines": NOTE_LINES,
        "recipients": cfg["recipients"],
        "config_error": problem,
    }


def lamp_path(day):
    return f"listener/lamp/{day.isoformat()}.json"


def outcome_reply(outcome, sent_msg, queued_msg):
    """(exit status, result, message) for the outcome of this command's own item."""
    if outcome in ("sent", "already"):
        return 0, outcome, sent_msg
    if outcome in ("queued", None, "busy"):
        return 0, "queued", queued_msg
    return 2, "error", None


def cmd_light(paths, cfg):
    now = _now()
    day = now.date()
    with locked(paths.lock):
        lamp = load_lamp(paths)
        new = day.isoformat() not in lamp["lit"]
        if new:
            # The outbox first: a process killed between the two writes leaves a queued lamp that is not
            # yet shown, never a lamp that is shown and will never be sent.
            item = new_item("lamp", lamp_path(day), canonical({"date": day.isoformat(), "lit": True}), now)
            put_item(paths, item)
            lamp["lit"][day.isoformat()] = iso(now)
            lamp["lit"] = prune_days(lamp["lit"], day)
            lamp["version"] = 1
            write_json(paths.lamp, lamp)
    if not new:
        waiting = [i for i in outbox_items(paths) if i["kind"] == "lamp" and i["path"] == lamp_path(day)]
        if not waiting:
            return 0, "already", "The lamp is already lit tonight."
        item = waiting[0]
    out = drain(paths, cfg, SEND_BUDGET, first=item["id"])
    code, result, msg = outcome_reply(out.get(item["id"], "busy" if out.get("busy") else None),
                                      "The lamp is lit tonight.",
                                      "The lamp is lit here; it will be sent when the Mac is next online.")
    if result == "error":
        msg = "The lamp is lit here, but it was not sent: " + (load_state(paths).get("error") or {}).get("message", "error")
    return code, result, msg


def cmd_note(paths, cfg, problem, to, raw):
    if cfg["recipients"] is None:
        raise Refused(problem or "no recipients configured")
    keys = [r["key"] for r in cfg["recipients"]]
    chosen = set()
    for k in to:
        if k == "all":
            chosen.update(keys)
        elif k in keys:
            chosen.add(k)
        else:
            raise Refused(f"no recipient {k!r} in listener.json")
    if not chosen:
        raise Refused("say who the note is for (--to)")
    text = clean_text(raw)
    check_note(text)
    now = _now()
    day = now.date().isoformat()
    with locked(paths.lock):
        s = load_state(paths)
        today = s["notes"].get(day, [])
        if len(today) >= NOTES_PER_DAY:
            raise Refused(f"{NOTES_PER_DAY} notes have been left today, the most for one day; try tomorrow")
        nid = str(uuid.uuid4())
        body = canonical({"id": nid, "opened": day, "to": [k for k in keys if k in chosen], "text": text})
        put_item(paths, new_item("note", f"listener/notes/{day}-{nid}.json", body, now, item_id=nid))
        s["notes"][day] = today + [nid]
        s["notes"] = prune_days(s["notes"], now.date())
        write_json(paths.state, s)
    out = drain(paths, cfg, SEND_BUDGET, first=nid)
    code, result, msg = outcome_reply(out.get(nid, "busy" if out.get("busy") else None),
                                      "The note is sent.",
                                      "The note is saved; it will be sent when the Mac is next online.")
    if result == "error":
        msg = "The note is saved, but it was not sent: " + (load_state(paths).get("error") or {}).get("message", "error")
    return code, result, msg


def cmd_drain(paths, cfg):
    out = drain(paths, cfg, DRAIN_BUDGET)
    if out.get("busy"):
        return 0, "busy", "another send is in progress"
    if not out:
        return 0, "empty", "nothing queued"
    counts = {}
    for v in out.values():
        counts[v] = counts.get(v, 0) + 1
    summary = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
    bad = any(v in ("error", "rejected") for v in out.values())
    return (2 if bad else 0), ("error" if bad else "drained"), summary


def cmd_check(paths, cfg):
    gh = GitHub(cfg, read_key(cfg), time.monotonic() + SEND_BUDGET)
    status_code, headers = gh.repo_info()
    if status_code != 200:
        classify(status_code, headers)
    changes = {"error": None, "last_attempt": {"at": iso(_now()), "outcome": "key checked"}}
    if gh.expires:
        changes["token_expires"] = gh.expires
    record(paths, **changes)
    return 0, "ok", f"the key can see {cfg['repo']}" + (f"; it expires {gh.expires}" if gh.expires else "")


def human_status(st):
    lines = [f"lamp: {'lit' if st['lamp_lit_today'] else 'not lit'} for {st['today']}"
             + (" (waiting to send)" if st["lamp_queued"] else ""),
             f"queued: {st['queued']}" + (f", rejected: {st['rejected']}" if st["rejected"] else ""),
             f"last send: {st['last_send'] or 'never'}" + (f" ({st['last_send_what']})" if st["last_send_what"] else ""),
             f"key: {st['token']}" + (f", expires {st['token_expires']}" if st["token_expires"] else ""),
             f"notes today: {st['notes_today']} of {st['notes_per_day']}"]
    if st["error"]:
        lines.append(f"error: {st['error']}")
    if st["recipients"] is not None:
        lines.append("recipients: " + ", ".join(f"{r['key']} ({r['label']})" for r in st["recipients"]))
    else:
        lines.append(f"recipients: none ({st['config_error']})")
    return "\n".join(lines)


def main(argv=None, stdin=None):
    ap = argparse.ArgumentParser(prog="listener.py", description="Light the lamp, leave a note.")
    ap.add_argument("--home", default=HOME, help="where listener.json and listener/ live")
    ap.add_argument("--api", default=None, help="API base URL (default: listener.json's api, else %s)" % API)
    ap.add_argument("--json", action="store_true", help="print one JSON object (for the menu-bar helper)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("light")
    n = sub.add_parser("note")
    n.add_argument("--to", action="append", required=True, help="a recipient key, or all")
    sub.add_parser("drain")
    sub.add_parser("status")
    sub.add_parser("check")
    a = ap.parse_args(argv)
    paths = Paths(os.path.abspath(os.path.expanduser(a.home)))
    reply = {"ok": True, "command": a.cmd}
    code = 0
    try:
        cfg, problem = load_config(paths, a.api)
        if a.cmd == "status":
            st = status(paths, cfg, problem)
            if a.json:
                print(json.dumps(dict(reply, result="status", status=st)))
            else:
                print(human_status(st))
            return 0
        if a.cmd == "light":
            code, result, msg = cmd_light(paths, cfg)
        elif a.cmd == "note":
            src = stdin if stdin is not None else sys.stdin.buffer
            raw = src.read(STDIN_MAX + 1)
            if len(raw) > STDIN_MAX:
                raise Refused("the note is far too long")
            code, result, msg = cmd_note(paths, cfg, problem, a.to, raw.decode("utf-8", "replace"))
        elif a.cmd == "drain":
            code, result, msg = cmd_drain(paths, cfg)
        else:
            code, result, msg = cmd_check(paths, cfg)
    except Refused as e:
        code, result, msg = 1, "refused", str(e)
    except (AuthError, Failed, Transient, Rejected) as e:
        code, result, msg = 2, "error", str(e)
    except Exception as e:      # noqa: BLE001 - report, never crash the caller
        import traceback
        traceback.print_exc()
        code, result, msg = 3, "failed", f"listener.py failed: {type(e).__name__}"
    reply.update(ok=code == 0, result=result, message=msg)
    if a.json:
        try:
            reply["status"] = status(paths, *load_config(paths, a.api))
        except Exception:       # noqa: BLE001
            reply["status"] = None
        print(json.dumps(reply))
    elif a.cmd == "drain":
        if result not in ("empty", "busy"):
            log("drain: " + msg)        # timestamped, as nightly.py appends it to the render log
    else:
        print(msg, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
