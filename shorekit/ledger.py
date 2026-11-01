"""The ledger: an append-only list of add and sea events, and its replay.

Replaying the ledger against a reference set rebuilds the shore exactly: which objects are live,
in what order they draw, and who covers whom. Rule 7 (one object per maker per UTC day; at most
48 live, with a storm taking the oldest down to 40 when room is needed) is enforced here.

A `sea` event says what the sea took and never why: a storm and the owner's veto look the same.
Whoever keeps the reasons (the carrier, privately) can hand them to replay, which then holds each
storm and veto to its exact rule as well (SCHEMA section 6.6).
"""
import hashlib
import os
import re

from . import KIT_VERSION, MAX_LIVE, STORM_TO
from .errors import ShoreError
from .geometry import SURFACE_PIER, SURFACE_SHINGLE, place
from .manifest import (ID_RE, KIT_RE, MAKER_RE, REF_RE, WORLD_RE, check_id, id_date, kit_major, parse_manifest,
                       valid_date)
from .rules import draw_order, evaluate
from .strictjson import canonical, is_int, is_str, loads

LEDGER_MAX_BYTES = 16 * 1024 * 1024
LEDGER_MAX_EVENTS = 200000
QUEUE_MAX_BYTES = 65536
QUEUE_MAX = 64
OBJECT_MAX_BYTES = 16384
REASONS_MAX_BYTES = 4 * 1024 * 1024

TS_RE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z", re.ASCII)
SHA_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)
COMMIT_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}", re.ASCII)

KEYS = {
    "add": ("at", "commit", "event", "id", "kit", "lands", "maker", "reference", "seq", "sha256", "world"),
    "sea": ("at", "event", "seq", "takes"),
}
# Why the sea took what a sea event took: kept by the carrier, never on a shore branch.
WHY = {
    "storm": ("for", "seq", "why"),     # room for the add `for`, which must be the next event
    "veto": ("id", "seq", "why"),       # the owner took `id`, and whatever rests on it went with it
}


def _bad(text):
    return ShoreError("E_LEDGER", text)


def check_ts(v, what):
    m = TS_RE.fullmatch(v) if is_str(v) else None
    if m is None:
        raise _bad("%s must be a UTC time like 2026-11-02T04:30:00Z" % what)
    y, mo, d, h, mi, s = (int(g) for g in m.groups())
    if not valid_date(y, mo, d) or h > 23 or mi > 59 or s > 59:
        raise _bad("%s %s is not a real time" % (what, v))
    return v


def days_from_civil(y, m, d):
    """Days since 1970-01-01 (proleptic Gregorian), integers only."""
    if m <= 2:
        y -= 1
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    mp = m - 3 if m > 2 else m + 9
    doy = (153 * mp + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def day_number(ts):
    return days_from_civil(int(ts[0:4]), int(ts[5:7]), int(ts[8:10]))


def _ids(v, what):
    if type(v) is not list or not 1 <= len(v) <= MAX_LIVE:
        raise _bad("%s must list 1-%d ids" % (what, MAX_LIVE))
    for x in v:
        try:
            check_id(x)
        except ShoreError:
            raise _bad("%s holds a bad id" % what)
    if len(set(v)) != len(v):
        raise _bad("%s repeats an id" % what)
    return v


def check_event(ev, n):
    """Schema of one ledger event (the n-th, 1-based). Raises E_LEDGER."""
    where = "event %d" % n
    if type(ev) is not dict:
        raise _bad("%s must be an object" % where)
    kind = ev.get("event")
    if not is_str(kind) or kind not in KEYS:
        raise _bad('%s: "event" must be add or sea' % where)
    if sorted(ev) != sorted(KEYS[kind]):
        raise _bad("%s (%s): keys must be exactly %s" % (where, kind, ", ".join(KEYS[kind])))
    if not is_int(ev["seq"]) or ev["seq"] != n:
        raise _bad("%s: seq must be %d" % (where, n))
    check_ts(ev["at"], where + " at")
    if kind == "add":
        check_ts(ev["lands"], where + " lands")
        if ev["lands"] < ev["at"]:
            raise _bad("%s: lands before it was accepted" % where)
        try:
            check_id(ev["id"])
        except ShoreError as e:
            raise _bad("%s: %s" % (where, e.text))
        for k, rx in (("maker", MAKER_RE), ("world", WORLD_RE), ("commit", COMMIT_RE), ("sha256", SHA_RE),
                      ("reference", REF_RE), ("kit", KIT_RE)):
            if not is_str(ev[k]) or not rx.fullmatch(ev[k]):
                raise _bad("%s: bad %s" % (where, k))
    else:
        _ids(ev["takes"], where + " takes")
    return ev


def check_reason(r, n):
    """Schema of the n-th (1-based) entry of a reasons file. Raises E_LEDGER."""
    where = "sea reason %d" % n
    if type(r) is not dict:
        raise _bad("%s must be an object" % where)
    why = r.get("why")
    if not is_str(why) or why not in WHY:
        raise _bad('%s: "why" must be storm or veto' % where)
    if sorted(r) != sorted(WHY[why]):
        raise _bad("%s (%s): keys must be exactly %s" % (where, why, ", ".join(WHY[why])))
    if not is_int(r["seq"]) or not 1 <= r["seq"] <= LEDGER_MAX_EVENTS:
        raise _bad("%s: bad seq" % where)
    try:
        check_id(r["for" if why == "storm" else "id"])
    except ShoreError:
        raise _bad("%s: bad %s" % (where, "for" if why == "storm" else "id"))
    return r


def _loads(data, limit, what, code):
    try:
        return loads(data, limit, 4, what)
    except ShoreError as e:
        raise ShoreError(code, e.text)


def parse_ledger(data):
    obj = _loads(data, LEDGER_MAX_BYTES, "ledger", "E_LEDGER")
    if sorted(obj) != ["events", "shore_ledger"] or not is_int(obj["shore_ledger"]) or obj["shore_ledger"] != 1:
        raise _bad('the ledger must be {"shore_ledger": 1, "events": [...]}')
    evs = obj["events"]
    if type(evs) is not list or len(evs) > LEDGER_MAX_EVENTS:
        raise _bad("events must be a list of at most %d" % LEDGER_MAX_EVENTS)
    return [check_event(ev, n) for n, ev in enumerate(evs, 1)]


def parse_reasons(data):
    """A reasons file, {"shore_sea": 1, "sea": [...]}, as {seq: reason}. Raises E_LEDGER."""
    obj = _loads(data, REASONS_MAX_BYTES, "sea reasons", "E_LEDGER")
    if sorted(obj) != ["sea", "shore_sea"] or not is_int(obj["shore_sea"]) or obj["shore_sea"] != 1:
        raise _bad('the reasons must be {"shore_sea": 1, "sea": [...]}')
    rs = obj["sea"]
    if type(rs) is not list or len(rs) > LEDGER_MAX_EVENTS:
        raise _bad("sea must be a list of at most %d" % LEDGER_MAX_EVENTS)
    out = {}
    for n, r in enumerate(rs, 1):
        check_reason(r, n)
        if out and r["seq"] <= max(out):
            raise _bad("sea reason %d: seq %d is out of order" % (n, r["seq"]))
        out[r["seq"]] = r
    return out


def reason_line(r):
    """How a reason reads in the kit's report (only the carrier, which has the reasons, sees it)."""
    if r["why"] == "storm":
        return "a storm, to make room for %s" % r["for"]
    return "the owner's veto of %s" % r["id"]


def ledger_bytes(events):
    """The canonical ledger file: one canonical event per line."""
    if not events:
        return b'{"events":[],"shore_ledger":1}\n'
    return b'{"events":[\n' + b",\n".join(canonical(e) for e in events) + b'\n],"shore_ledger":1}\n'


def read_bounded(path, limit, err, what):
    try:
        with open(path, "rb") as f:
            data = f.read(limit + 1)
    except OSError:
        raise ShoreError(err, "cannot read %s" % what)
    if len(data) > limit:
        raise ShoreError(err, "%s is over %d bytes" % (what, limit))
    return data


class Shore:
    """The shore as the ledger leaves it, replayed against one reference set.

    `reasons` ({seq: reason}, from parse_reasons) makes replay strict: every sea event must have one,
    and each storm and veto is held to its own rule. Without it (a world, the Mac) a sea event need
    only take live objects and everything resting on them."""

    def __init__(self, ref, objects_dir=None, reasons=None):
        self.ref = ref
        self.objects_dir = objects_dir
        self.reasons = reasons
        self.why = {}           # seq -> reason, for every sea event whose reason is known here
        self.events = []
        self.live = []          # Placed, in seq order
        self.byid = {}
        self.info = {}          # id -> its add event
        self.ids = set()        # every id ever added
        self.taken = set()      # ids the sea took
        self.maker_days = {}    # (maker, YYYY-MM-DD) -> id
        self.last_at = ""
        self.pending = None     # a storm's "for", until its add follows
        self.misfits = []
        self.manifests = {}     # id -> Manifest

    # ---------------------------------------------------------------- objects --
    def load_object(self, oid, sha):
        if self.objects_dir is None:
            raise _bad("no objects directory to read %s from" % oid)
        data = read_bounded(os.path.join(self.objects_dir, oid + ".json"), OBJECT_MAX_BYTES, "E_LEDGER",
                            "objects/%s.json" % oid)
        try:
            m = parse_manifest(data)
        except ShoreError as e:
            raise _bad("objects/%s.json: %s" % (oid, e.line()))
        if m.sha256 != sha:
            raise _bad("objects/%s.json has sha256 %s, the ledger says %s" % (oid, m.sha256, sha))
        if m.id != oid:
            raise _bad("objects/%s.json holds id %s" % (oid, m.id))
        return m

    # ------------------------------------------------------------------ piles --
    def pile(self, oid):
        """oid and every live object resting on it, directly or not, in seq order."""
        out = [oid]
        inpile = {oid}
        for a in self.live:
            if a.on in inpile and a.id not in inpile:
                out.append(a.id)
                inpile.add(a.id)
        return sorted(out, key=lambda i: self.byid[i].seq)

    def storm_takes(self):
        """What a storm takes: the oldest live objects, each with its pile, until at most STORM_TO
        remain (fewer when the last one taken had things resting on it)."""
        taken = []
        seen = set()
        for a in self.live:
            if len(self.live) - len(taken) <= STORM_TO:
                break
            if a.id in seen:
                continue
            for oid in self.pile(a.id):
                if oid not in seen:
                    seen.add(oid)
                    taken.append(oid)
        return sorted(taken, key=lambda i: self.byid[i].seq)

    def _remove(self, ids):
        gone = set(ids)
        self.live = [a for a in self.live if a.id not in gone]
        for i in ids:
            del self.byid[i]
            self.taken.add(i)

    # ----------------------------------------------------------------- replay --
    def apply(self, ev, manifest=None, why=None):
        """Apply one event. `manifest` supplies an add's object when it is not yet in objects/; `why`
        is a sea event's reason when the caller is the one making it (accept, veto)."""
        n = len(self.events) + 1
        ev = check_event(ev, n)
        if ev["at"] < self.last_at:
            raise _bad("seq %d: at %s is before the previous event's %s" % (n, ev["at"], self.last_at))
        kind = ev["event"]
        if self.pending is not None and (kind != "add" or ev["id"] != self.pending):
            raise _bad("seq %d: the storm before it was for %s, which must come next" % (n, self.pending))
        if self.reasons is not None and why is None:
            why = self.reasons.get(n)
            if kind == "sea" and why is None:
                raise _bad("seq %d: the sea event has no reason" % n)
            if kind == "add" and why is not None:
                raise _bad("the reasons name seq %d, which is an add" % n)
        if why is not None and why["seq"] != n:
            raise _bad("seq %d: its reason is for seq %d" % (n, why["seq"]))
        if kind == "add":
            self._add(ev, n, manifest)
        else:
            self._sea(ev, n, why)
        self.events.append(ev)
        self.last_at = ev["at"]

    def _sea(self, ev, n, why):
        """The sea takes live objects, and everything resting on them goes too: nothing floats. With
        a reason, a storm must be exactly the storm rule 7 makes, and a veto exactly the pile."""
        takes = ev["takes"]
        for oid in takes:
            if oid not in self.byid:
                raise _bad("seq %d: the sea takes %s, which is not on the shore" % (n, oid))
        if takes != sorted(takes, key=lambda i: self.byid[i].seq):
            raise _bad("seq %d: the sea's takes must be listed in seq order" % n)
        gone = set(takes)
        for a in self.live:
            if a.id not in gone and a.on in gone:
                raise _bad("seq %d: the sea takes %s but leaves %s, which rests on it" % (n, a.on, a.id))
        if why is not None:
            if why["why"] == "storm":
                if len(self.live) != MAX_LIVE:
                    raise _bad("seq %d: a storm with %d live; a storm comes only when %d are" % (n, len(self.live), MAX_LIVE))
                want = self.storm_takes()
                if takes != want:
                    raise _bad("seq %d: the storm must take %s" % (n, ", ".join(want)))
                self.pending = why["for"]
            else:
                oid = why["id"]
                if oid not in self.byid:
                    raise _bad("seq %d: veto of %s, which is not on the shore" % (n, oid))
                want = self.pile(oid)
                if takes != want:
                    raise _bad("seq %d: the veto of %s must take %s" % (n, oid, ", ".join(want)))
            self.why[n] = why
        self._remove(takes)

    def _add(self, ev, n, m=None):
        oid = ev["id"]
        self.pending = None
        if oid in self.ids:
            raise _bad("seq %d: id %s was already used" % (n, oid))
        if len(self.live) >= MAX_LIVE:
            raise _bad("seq %d: adding %s would make %d live; the sea must make room first" % (n, oid, len(self.live) + 1))
        day = ev["at"][:10]
        if (ev["maker"], day) in self.maker_days:
            raise _bad("seq %d: %s already added %s on %s" % (n, ev["maker"], self.maker_days[(ev["maker"], day)], day))
        if id_date(oid) > day:
            raise _bad("seq %d: id %s is dated after the day it was accepted" % (n, oid))
        if m is None:
            m = self.load_object(oid, ev["sha256"])
        elif m.sha256 != ev["sha256"] or m.id != oid:
            raise _bad("seq %d: the object given for %s does not match its sha256" % (n, oid))
        if m.maker != ev["maker"] or m.reference != ev["reference"]:
            raise _bad("seq %d: objects/%s.json disagrees with the ledger about maker or reference" % (n, oid))
        errs, p = evaluate(m, self.ref, self.live, n, self.taken)
        if errs:
            if ev["reference"] == self.ref.id and ev["kit"] == KIT_VERSION:
                raise _bad("seq %d: %s fails against its own reference and kit: %s" % (n, oid, errs[0].line()))
            self.misfits.append({"seq": n, "id": oid, "messages": [e.line() for e in errs]})
            if p is None:
                support = self.byid.get(m.on)
                if m.on not in (SURFACE_SHINGLE, SURFACE_PIER) and support is None:
                    raise _bad("seq %d: %s rests on %s, which is not on the shore" % (n, oid, m.on))
                p = place(m, self.ref, support, n)
        self.live.append(p)
        self.byid[oid] = p
        self.info[oid] = ev
        self.manifests[oid] = m
        self.ids.add(oid)
        self.maker_days[(ev["maker"], day)] = oid

    def finish(self):
        if self.pending is not None:
            raise _bad("the ledger ends after a storm for %s, with no add" % self.pending)
        if self.reasons is not None:
            extra = sorted(s for s in self.reasons if s > len(self.events))
            if extra:
                raise _bad("the reasons name seq %d, which the ledger does not reach" % extra[0])
        return self

    # ------------------------------------------------------------- candidates --
    def judge(self, m, day=None):
        """Every rule for m as the next object. `day` is the UTC date of the pass (YYYY-MM-DD); in a
        sandbox check it defaults to the id's own date. Returns (errors, storm_takes, placed)."""
        errs = []
        day = day or id_date(m.id)
        if m.id in self.ids:
            errs.append(ShoreError("E_TAKEN", "id %s is already used (ids are never reused)" % m.id))
        if (m.maker, day) in self.maker_days:
            errs.append(ShoreError("E_QUOTA", "%s already has %s on %s (one object per maker per day)"
                                   % (m.maker, self.maker_days[(m.maker, day)], day)))
        if id_date(m.id) > day:
            errs.append(ShoreError("E_ID", "id is dated %s, after the pass on %s" % (id_date(m.id), day)))
        if kit_major(m.kit) != kit_major(KIT_VERSION):
            errs.append(ShoreError("E_KIT", "made for kit %s, this kit is %s" % (m.kit, KIT_VERSION)))
        if m.reference != self.ref.id:
            errs.append(ShoreError("E_REFERENCE", "made against reference %s, the shore is on %s" % (m.reference, self.ref.id)))
        if errs:
            return errs, [], None
        takes = self.storm_takes() if len(self.live) >= MAX_LIVE else []
        gone = set(takes)
        live = [a for a in self.live if a.id not in gone]
        if m.on in gone:
            return [ShoreError("E_ON", "%s would be taken by the sea that makes room" % m.on)], takes, None
        errs, p = evaluate(m, self.ref, live, len(self.events) + 1 + (1 if takes else 0), self.taken)
        return errs, takes, p

    def accept(self, m, at, lands, world, commit):
        """Append the events for an accepted candidate (the sea first, as a storm, if room is needed)."""
        errs, takes, _ = self.judge(m, at[:10])
        if errs:
            raise errs[0]
        out = []
        if takes:
            n = len(self.events) + 1
            out.append({"seq": n, "event": "sea", "at": at, "takes": takes})
            self.apply(out[-1], why={"seq": n, "why": "storm", "for": m.id})
        ev = {"seq": len(self.events) + 1, "event": "add", "at": at, "lands": lands, "id": m.id, "maker": m.maker,
              "world": world, "commit": commit, "sha256": m.sha256, "reference": m.reference, "kit": KIT_VERSION}
        self.apply(ev, m)
        out.append(ev)
        return out

    def veto(self, oid, at):
        """The sea event for the owner's veto, taking oid and its pile off the shore."""
        if oid not in self.byid:
            raise _bad("%s is not on the shore" % oid)
        n = len(self.events) + 1
        ev = {"seq": n, "event": "sea", "at": at, "takes": self.pile(oid)}
        self.apply(ev, why={"seq": n, "why": "veto", "id": oid})
        return ev

    def fork(self):
        """An independent copy of the state (shares immutable Placed objects)."""
        s = Shore(self.ref, self.objects_dir, self.reasons)
        s.why = dict(self.why)
        s.events = list(self.events)
        s.live = list(self.live)
        s.byid = dict(self.byid)
        s.info = dict(self.info)
        s.ids = set(self.ids)
        s.taken = set(self.taken)
        s.maker_days = dict(self.maker_days)
        s.last_at = self.last_at
        s.pending = self.pending
        s.misfits = list(self.misfits)
        s.manifests = dict(self.manifests)
        return s

    def ordered(self):
        return draw_order(self.live)


def load_shore(ref, ledger_path, objects_dir, reasons=None):
    """Replay a ledger file (missing = empty) against ref, strictly if `reasons` ({seq: reason}) is
    given. Raises E_LEDGER if it is inconsistent."""
    shore = Shore(ref, objects_dir, reasons)
    if ledger_path is not None and os.path.exists(ledger_path):
        events = parse_ledger(read_bounded(ledger_path, LEDGER_MAX_BYTES, "E_LEDGER", "ledger.json"))
        for ev in events:
            shore.apply(ev)
    return shore.finish()


# --------------------------------------------------------------------- queue --
def parse_queue(data):
    q = _loads(data, QUEUE_MAX_BYTES, "queue", "E_QUEUE")
    if sorted(q) != ["at", "candidates", "lands", "shore_queue"] or not is_int(q["shore_queue"]) or q["shore_queue"] != 1:
        raise ShoreError("E_QUEUE", 'the queue must be {"shore_queue": 1, "at", "lands", "candidates"}')
    try:
        check_ts(q["at"], "queue at")
        check_ts(q["lands"], "queue lands")
    except ShoreError as e:
        raise ShoreError("E_QUEUE", e.text)
    if q["lands"] < q["at"]:
        raise ShoreError("E_QUEUE", "lands is before at")
    cands = q["candidates"]
    if type(cands) is not list or len(cands) > QUEUE_MAX:
        raise ShoreError("E_QUEUE", "candidates must be a list of at most %d" % QUEUE_MAX)
    seen = set()
    for c in cands:
        if type(c) is not dict or sorted(c) != ["commit", "id", "world"]:
            raise ShoreError("E_QUEUE", "each candidate must be {world, id, commit}")
        if not is_str(c["world"]) or not WORLD_RE.fullmatch(c["world"]):
            raise ShoreError("E_QUEUE", "bad world")
        if not is_str(c["id"]) or not ID_RE.fullmatch(c["id"]):
            raise ShoreError("E_QUEUE", "bad id")
        if not is_str(c["commit"]) or not COMMIT_RE.fullmatch(c["commit"]):
            raise ShoreError("E_QUEUE", "bad commit")
        if (c["world"], c["id"]) in seen:
            raise ShoreError("E_QUEUE", "candidate %s/%s is listed twice" % (c["world"], c["id"]))
        seen.add((c["world"], c["id"]))
    return q


def priority(q):
    """Candidates in judging order: worlds sorted by name, rotated by the pass's day number (so with
    two worlds, priority alternates with the parity of the UTC date); within a world, by id."""
    worlds = sorted(set(c["world"] for c in q["candidates"]))
    if not worlds:
        return []
    k = day_number(q["at"]) % len(worlds)
    rank = {w: i for i, w in enumerate(worlds[k:] + worlds[:k])}
    return sorted(q["candidates"], key=lambda c: (rank[c["world"]], c["id"]))


def run_queue(shore, q, qdir):
    """Judge the queued candidates in priority order, appending accepted ones to `shore`.

    Returns (appended_events, returned, accepted_manifests)."""
    start = shore.fork()
    appended = []
    returned = []
    accepted = []
    for c in priority(q):
        rec = {"world": c["world"], "id": c["id"], "commit": c["commit"], "maker": None, "sha256": None,
               "race": False, "messages": []}
        try:
            data = read_bounded(os.path.join(qdir, c["world"], c["id"] + ".json"), 16384, "E_PARSE",
                                "%s/%s.json" % (c["world"], c["id"]))
            m = parse_manifest(data)
            rec["maker"], rec["sha256"] = m.maker, m.sha256
            if m.id != c["id"]:
                raise ShoreError("E_ID", "the file holds id %s" % m.id)
        except ShoreError as e:
            rec["messages"] = [e.line()]
            returned.append(rec)
            continue
        errs, takes, _ = shore.judge(m, q["at"][:10])
        if errs:
            rec["messages"] = [e.line() for e in errs]
            others = [ev["id"] for ev in appended if ev["event"] == "add" and ev["world"] != c["world"]]
            if others and not any(e.code == "E_QUOTA" for e in errs) and not start.judge(m, q["at"][:10])[0]:
                rec["race"] = True
                rec["messages"].append("E_RACE it passes against yesterday's ledger, but %s landed first in this pass"
                                       % ", ".join(others))
            returned.append(rec)
            continue
        appended += shore.accept(m, q["at"], q["lands"], c["world"], c["commit"])
        accepted.append(m)
    return appended, returned, accepted


def ledger_sha256(events):
    return hashlib.sha256(ledger_bytes(events)).hexdigest()
