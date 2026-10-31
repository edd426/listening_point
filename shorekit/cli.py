"""shorekit status | check | preview | import | replay

Exit codes: 0 pass (or OK); 1 the object fails a rule, or the kit does not match kit.lock;
2 a usage, file or reference-data problem; 3 the ledger is inconsistent.
"""
import argparse
import hashlib
import os
import sys
import tempfile

from . import KIT_VERSION, MAX_LIVE
from .compose import pixels_sha256, plan_sha256, sheet, write, zoom
from .errors import ShoreError
from .geometry import SURFACE_PIER, SURFACE_SHINGLE, place
from .importer import png_to_manifest, pretty
from .ledger import (Shore, check_ts, ledger_bytes, ledger_sha256, load_shore, parse_ledger, parse_queue,
                     read_bounded, run_queue)
from .manifest import REF_RE, check_id, parse_manifest
from .reference import load_reference
from .strictjson import canonical, is_int, is_str, loads

LOCK = "kit.lock"


class Usage(Exception):
    pass


def out(line):
    sys.stdout.write(line + "\n")


# ------------------------------------------------------------------ locating --
def archive_path():
    arch = getattr(globals().get("__loader__"), "archive", None)
    return arch if arch and os.path.isfile(arch) else None


def find_shore(arg):
    if arg:
        if not os.path.isdir(arg):
            raise Usage("no shore directory at %s" % arg)
        return arg
    arch = archive_path()
    if arch:
        kit = os.path.dirname(os.path.abspath(arch))
        root = os.path.dirname(kit)
        if os.path.basename(kit) == "kit" and os.path.exists(os.path.join(root, LOCK)):
            return root
    cwd = os.getcwd()
    if os.path.exists(os.path.join(cwd, LOCK)) or os.path.exists(os.path.join(cwd, "ledger.json")):
        return cwd
    return None


def read_lock(shore_dir):
    if shore_dir is None:
        return None
    p = os.path.join(shore_dir, LOCK)
    if not os.path.exists(p):
        return None
    lock = loads(read_bounded(p, 4096, "E_LOCK", LOCK), 4096, 2, LOCK)
    keys = ["commit", "kit", "pyz_sha256", "reference", "shore_kit_lock"]
    if sorted(lock) != keys or not is_int(lock["shore_kit_lock"]) or lock["shore_kit_lock"] != 1 or \
            not all(is_str(lock[k]) for k in keys[:4]) or not REF_RE.fullmatch(lock["reference"]):
        raise ShoreError("E_LOCK", "kit.lock must be {shore_kit_lock: 1, kit, commit, pyz_sha256, reference}")
    return lock


def reference_dir(args, shore_dir, lock):
    if getattr(args, "reference", None):
        return args.reference
    if shore_dir is None:
        raise Usage("no shore found: pass --shore DIR (the extracted shore branch) or --reference DIR")
    base = os.path.join(shore_dir, "reference")
    if lock is not None:
        return os.path.join(base, lock["reference"])
    subs = sorted(d for d in os.listdir(base) if REF_RE.fullmatch(d)) if os.path.isdir(base) else []
    if len(subs) != 1:
        raise Usage("cannot tell which reference set to use: pass --reference DIR")
    return os.path.join(base, subs[0])


def open_shore(args):
    shore_dir = find_shore(getattr(args, "shore", None))
    lock = read_lock(shore_dir)
    ref = load_reference(reference_dir(args, shore_dir, lock))
    ledger = getattr(args, "ledger", None) or (os.path.join(shore_dir, "ledger.json") if shore_dir else None)
    objects = getattr(args, "objects", None) or (os.path.join(shore_dir, "objects") if shore_dir else None)
    return shore_dir, lock, ref, load_shore(ref, ledger, objects)


def read_manifest(path):
    return parse_manifest(read_bounded(path, 16384, "E_PARSE", os.path.basename(path)))


# -------------------------------------------------------------------- status --
def cmd_status(args):
    arch = archive_path()
    sha = None
    if arch:
        with open(arch, "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()
    shore_dir = find_shore(args.shore)
    lock = read_lock(shore_dir)
    code = 0
    if lock is None:
        where = "sha256=%s" % sha if sha else "unpacked (not a zipapp)"
        out("KIT %s %s (no kit.lock found: nothing to check this copy against)" % (KIT_VERSION, where))
    elif sha == lock["pyz_sha256"] and lock["kit"] == KIT_VERSION:
        out("KIT OK %s sha256=%s commit=%s" % (KIT_VERSION, sha, lock["commit"]))
    else:
        out("KIT MISMATCH this copy is %s sha256=%s; kit.lock pins %s sha256=%s"
            % (KIT_VERSION, sha or "unpacked", lock["kit"], lock["pyz_sha256"]))
        code = 1
    if shore_dir is not None:
        try:
            ref = load_reference(reference_dir(args, shore_dir, lock))
            shore = load_shore(ref, os.path.join(shore_dir, "ledger.json"), os.path.join(shore_dir, "objects"))
            out("SHORE reference=%s digest=%s ledger=%d events live=%d/%d taken-by-the-sea=%d misfits=%d"
                % (ref.id, ref.digest[:16], len(shore.events), len(shore.live), MAX_LIVE, len(shore.taken),
                   len(shore.misfits)))
        except (ShoreError, Usage) as e:
            out("SHORE ERROR %s" % (e.line() if isinstance(e, ShoreError) else e))
            code = code or 2
    return code


# --------------------------------------------------------------------- check --
def judge_and_report(shore, m, day):
    errs, takes, p = shore.judge(m, day)
    if takes:
        out("NOTE the shore holds %d objects: to make room a storm will take %s" % (len(shore.live), ", ".join(takes)))
    for e in errs:
        out(e.line())
    if errs:
        out("FAIL %s: %d problem%s" % (m.id, len(errs), "" if len(errs) == 1 else "s"))
        return 1, p, takes
    order = sorted(shore.live + [p], key=lambda o: (o.ground_y, o.seq))
    out("PASS %s: seq %d, draws %d of %d, %d solid px, %d shadow px"
        % (m.id, p.seq, order.index(p) + 1, len(order), len(p.solid), len(p.shadow)))
    return 0, p, takes


def cmd_check(args):
    _, _, ref, shore = open_shore(args)
    m = read_manifest(args.object)
    day = args.day
    if day is not None:
        check_ts(day + "T00:00:00Z", "--day")
    code, _, _ = judge_and_report(shore, m, day)
    return code


# ------------------------------------------------------------------- preview --
def cmd_preview(args):
    _, _, ref, shore = open_shore(args)
    objs = list(shore.live)
    focus = None
    code = 0
    if args.object:
        m = read_manifest(args.object)
        code, focus, takes = judge_and_report(shore, m, args.day)
        gone = set(takes)
        objs = [a for a in objs if a.id not in gone]
        if focus is None:
            support = next((a for a in objs if a.id == m.on), None)
            if m.on in (SURFACE_SHINGLE, SURFACE_PIER) or support is not None:
                focus = place(m, ref, support, len(shore.events) + 1)
        if focus is not None:
            objs.append(focus)
    outdir = args.out or os.path.join(tempfile.gettempdir(), "shore-preview")
    os.makedirs(outdir, exist_ok=True)
    w, h, px, panels = sheet(ref, objs)
    path = os.path.join(outdir, "sheet.png")
    write(path, w, h, px)
    out("SHEET %s %dx%d (%s) pixels-sha256=%s" % (path, w, h, ", ".join(c.name for c in ref.conditions), pixels_sha256(px)))
    z = zoom(ref, panels[0], focus, objs)
    if z is not None:
        path = os.path.join(outdir, "zoom.png")
        write(path, z[0], z[1], z[2])
        out("ZOOM %s %dx%d (x4, %s; keep-out red, dry band green, deck cyan) pixels-sha256=%s"
            % (path, z[0], z[1], ref.conditions[0].name, pixels_sha256(z[2])))
    out("PLAN sha256=%s" % plan_sha256(ref, objs))
    return code


# -------------------------------------------------------------------- import --
def _pair(s, what):
    try:
        a, b = s.split(",")
        return int(a), int(b)
    except ValueError:
        raise Usage("%s must be two integers like 3,8" % what)


def cmd_import(args):
    reference = args.ref_id
    if reference is None:
        shore_dir = find_shore(args.shore)
        lock = read_lock(shore_dir)
        if lock is None:
            raise Usage("pass --ref-id (e.g. r1), or --shore DIR holding kit.lock")
        reference = lock["reference"]
    x, y = _pair(args.at, "--at")
    anchor = _pair(args.anchor, "--anchor") if args.anchor else None
    data = read_bounded(args.png, 65536, "E_IMPORT", os.path.basename(args.png))
    obj, notes = png_to_manifest(data, args.id, args.maker, args.on, x, y, reference, anchor, args.scale,
                                 args.label, args.side)
    body = pretty(obj)
    if args.output == "-":
        sys.stdout.write(body.decode("ascii"))
    else:
        with open(args.output, "wb") as f:
            f.write(body)
        out("WROTE %s: %dx%d cells, %d colours, anchor (%d,%d)"
            % (args.output, len(obj["rows"][0]), len(obj["rows"]), len(obj["palette"]), obj["anchor"][0], obj["anchor"][1]))
    for n in notes:
        out("NOTE " + n)
    return 0


# -------------------------------------------------------------------- replay --
def cmd_replay(args):
    shore_dir, lock, ref, shore = open_shore(args)
    before = list(shore.events)
    out("LEDGER OK %d events, %d/%d live, %d taken by the sea, %d misfits; sha256=%s"
        % (len(before), len(shore.live), MAX_LIVE, len(shore.taken), len(shore.misfits), ledger_sha256(before)))
    for mf in shore.misfits:
        out("MISFIT seq %d %s: %s" % (mf["seq"], mf["id"], "; ".join(mf["messages"])))
    if args.previous:
        old = parse_ledger(read_bounded(args.previous, 16 * 1024 * 1024, "E_LEDGER", "previous ledger"))
        if len(old) > len(before) or any(canonical(a) != canonical(b) for a, b in zip(old, before)):
            raise ShoreError("E_LEDGER", "the ledger does not extend the previous one: it dropped or changed an event")
        out("EXTENDS the previous ledger (%d events) by %d" % (len(old), len(before) - len(old)))
    appended, returned, accepted = [], [], []
    if args.queue:
        q = parse_queue(read_bounded(args.queue, 65536, "E_QUEUE", "queue"))
        appended, returned, accepted = run_queue(shore, q, os.path.dirname(os.path.abspath(args.queue)))
    if args.veto:
        if not args.at:
            raise Usage("--veto needs --at TIME")
        check_id(args.veto)
        check_ts(args.at, "--at")
        appended.append(shore.veto(args.veto, args.at))
    for ev in appended:
        if ev["event"] == "add":
            out("ACCEPT %s/%s seq %d" % (ev["world"], ev["id"], ev["seq"]))
        elif ev["event"] == "storm":
            out("STORM seq %d takes %s (room for %s)" % (ev["seq"], ", ".join(ev["takes"]), ev["for"]))
        else:
            out("VETO seq %d takes %s" % (ev["seq"], ", ".join(ev["takes"])))
    for r in returned:
        out("RETURN %s/%s%s: %s" % (r["world"], r["id"], " (race)" if r["race"] else "", "; ".join(r["messages"])))
    if args.out:
        os.makedirs(os.path.join(args.out, "objects"), exist_ok=True)
        for m in accepted:
            with open(os.path.join(args.out, "objects", m.id + ".json"), "wb") as f:
                f.write(m.canonical)
        with open(os.path.join(args.out, "ledger.json"), "wb") as f:
            f.write(ledger_bytes(shore.events))
        result = {"shore_replay": 1, "kit": KIT_VERSION, "reference": ref.id, "reference_digest": ref.digest,
                  "ledger_in": {"events": len(before), "sha256": ledger_sha256(before)},
                  "ledger_out": {"events": len(shore.events), "sha256": ledger_sha256(shore.events)},
                  "append": appended, "returned": returned, "misfits": shore.misfits,
                  "live": [a.id for a in shore.live], "draw_order": [a.id for a in shore.ordered()],
                  "plan_sha256": plan_sha256(ref, shore.live)}
        with open(os.path.join(args.out, "result.json"), "wb") as f:
            f.write(canonical(result) + b"\n")
        out("WROTE %s (ledger.json, result.json, %d object%s)" % (args.out, len(accepted), "" if len(accepted) == 1 else "s"))
    out("LEDGER NOW %d events, %d/%d live; sha256=%s" % (len(shore.events), len(shore.live), MAX_LIVE,
                                                         ledger_sha256(shore.events)))
    return 0


# ---------------------------------------------------------------------- main --
def parser():
    p = argparse.ArgumentParser(prog="shorekit", description="The shore kit: check, preview and replay shore objects.")
    sub = p.add_subparsers(dest="cmd")

    def common(sp):
        sp.add_argument("--shore", help="the extracted shore branch (default: found from kit.lock)")
        sp.add_argument("--reference", help="a reference set directory (default: the one kit.lock names)")

    s = sub.add_parser("status", help="is this copy the pinned kit? what is on the shore?")
    common(s)
    s = sub.add_parser("check", help="run every rule on a manifest against the shore")
    common(s)
    s.add_argument("object")
    s.add_argument("--day", help="the UTC date of the pass (default: the date in the id)")
    s = sub.add_parser("preview", help="draw sheet.png (four conditions) and zoom.png")
    common(s)
    s.add_argument("object", nargs="?")
    s.add_argument("--day")
    s.add_argument("--out", help="where to write the pictures (default: a temp directory, never a repo)")
    s = sub.add_parser("import", help="turn a small PNG (<=64x64) into a manifest")
    s.add_argument("png")
    s.add_argument("-o", "--output", required=True, help="manifest path, or - for stdout")
    s.add_argument("--id", required=True)
    s.add_argument("--maker", required=True)
    s.add_argument("--on", required=True, help="shingle, pier, or the id of an object to build onto")
    s.add_argument("--at", required=True, help="x,y in frame pixels where the anchor's bottom-centre lands")
    s.add_argument("--anchor", help="column,row of the anchor cell (default: middle of the bottom row)")
    s.add_argument("--scale", type=int, choices=(1, 2), default=1)
    s.add_argument("--label")
    s.add_argument("--side", choices=("left", "right"), default="right")
    s.add_argument("--ref-id", help="reference id, e.g. r1 (default: from kit.lock)")
    s.add_argument("--shore")
    s = sub.add_parser("replay", help="replay the ledger; optionally judge a queue or add a veto")
    common(s)
    s.add_argument("--ledger", help="ledger file (default: SHORE/ledger.json)")
    s.add_argument("--objects", help="objects directory (default: SHORE/objects)")
    s.add_argument("--queue", help="queue.json of candidates (carrier)")
    s.add_argument("--veto", help="id to take off the shore (owner)")
    s.add_argument("--at", help="UTC time of the veto")
    s.add_argument("--previous", help="a previous ledger this one must extend")
    s.add_argument("--out", help="write ledger.json, result.json and objects/ here")
    return p


COMMANDS = {"status": cmd_status, "check": cmd_check, "preview": cmd_preview, "import": cmd_import, "replay": cmd_replay}


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if not args.cmd:
        p.print_help()
        return 2
    try:
        return COMMANDS[args.cmd](args)
    except Usage as e:
        out("ERROR %s" % e)
        return 2
    except ShoreError as e:
        out(e.line())
        if e.code == "E_LEDGER":
            return 3
        if args.cmd == "check" and e.code in ("E_PARSE", "E_SCHEMA", "E_ID"):
            out("FAIL: the manifest does not parse")
            return 1
        return 2
    except OSError as e:
        out("ERROR %s" % e)
        return 2
