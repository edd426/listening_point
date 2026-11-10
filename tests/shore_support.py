"""Shared by the shore's renderer tests: a reference set to test against, synthetic objects found a valid
spot by the kit itself, and a local shore cache in shorekit's layout. Everything is made at run time in
temporary folders, so no shore data ever sits in this repository.
"""
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "renderers", "procedural"), ROOT):
    if p not in sys.path:
        sys.path.append(p)
from shorekit.ledger import Shore, ledger_bytes  # noqa: E402
from shorekit.manifest import manifest_from_obj  # noqa: E402
from shorekit.reference import load_reference  # noqa: E402

_ref = {}


def reference_dir():
    """SHORE_REFERENCE if set, else a set built once for this run by tools/shore_reference.py."""
    if "dir" not in _ref:
        path = os.environ.get("SHORE_REFERENCE")
        if not path:
            tmp = tempfile.mkdtemp(prefix="shore-ref-")
            atexit.register(shutil.rmtree, tmp, True)
            path = os.path.join(tmp, "r1")
            p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "shore_reference.py"), path],
                               capture_output=True, text=True)
            assert p.returncode == 0, p.stderr[-3000:]
        _ref["dir"] = path
        _ref["ref"] = load_reference(path)
    return _ref["dir"]


def reference():
    reference_dir()
    return _ref["ref"]


def manifest(oid, maker, rows, palette, on, x, y, anchor=None, scale=1, label=None, ref=None):
    """A manifest made against the reference set in use (SHORE_REFERENCE may be a set of any id)."""
    obj = {"shore": 1, "id": oid, "maker": maker, "kit": "1.0.0", "reference": ref or reference().id,
           "palette": {k: list(v) for k, v in palette.items()}, "rows": list(rows), "scale": scale,
           "anchor": list(anchor if anchor is not None else (len(rows[0]) // 2, len(rows) - 1)),
           "place": {"on": on, "x": x, "y": y}}
    if label:
        obj["label"] = {"text": label[0], "side": label[1]}
    return manifest_from_obj(json.loads(json.dumps(obj)))


def place_first(shore, make, spots):
    """The first spot (x, y) where make(x, y) passes every rule on this shore: (manifest, placed)."""
    for x, y in spots:
        m = make(x, y)
        errs, _, p = shore.judge(m)
        if not errs:
            return m, p
    raise AssertionError("no spot passes for %s" % make(*spots[0]).id)


def dry_spots(ref, x0, x1, step=3, frac=(1, 2)):
    """Points on the dry band from column x0 to x1: a fraction of the way down the band."""
    out = []
    for x in range(x0, x1, step):
        b = ref.dry(x)
        if b:
            out.append((x, b[0] + (b[1] - b[0]) * frac[0] // frac[1]))
    return out


def deck_spots(ref, x0, x1, step=3):
    """Points across the deck's middle from column x0 to x1."""
    out = []
    for x in range(x0, x1, step):
        ys = [y for y in range(ref.cy, ref.cy + ref.ch) if ref.deck_mask[ref.index(x, y)]]
        if ys:
            out.append((x, (min(ys) + max(ys)) // 2))
    return out


def new_shore(ref):
    return Shore(ref)


def write_cache(path, ref_dir, shore, extra_events=()):
    """A local shore cache holding `shore`'s ledger (plus any extra events, e.g. a veto) and objects."""
    os.makedirs(os.path.join(path, "objects"), exist_ok=True)
    os.makedirs(os.path.join(path, "reference"), exist_ok=True)
    link = os.path.join(path, "reference", shore.ref.id)
    if not os.path.exists(link):
        os.symlink(os.path.abspath(ref_dir), link)
    events = list(shore.events) + list(extra_events)
    with open(os.path.join(path, "ledger.json"), "wb") as f:
        f.write(ledger_bytes(events))
    for oid, m in shore.manifests.items():
        with open(os.path.join(path, "objects", oid + ".json"), "wb") as f:
            f.write(m.canonical)
    return path


def twice(rows):
    """A bitmap with every cell doubled each way."""
    return [line for row in rows for line in ("".join(c * 2 for c in row),) * 2]


# Look C (kit 1.2.0): a thing must be big enough to notice (its sides average min_h, about 50 px on the near
# shingle) and stand out from the ground (rule 7), so the cairn is whitewashed and drawn twice the size, the
# post is taller and painted red, and the log is longer and painted yellow.
STONES = {"a": (232, 230, 222), "b": (214, 208, 196), "c": (186, 176, 156), "d": (240, 236, 222)}
CAIRN = twice(["..dd..", ".daab.", ".aabb.", "aabbcc", "abbacc", "bbaacc", "cbbccb"])
LOG = {"w": (226, 186, 52), "v": (196, 132, 46)}


def fixtures(shore, ref):
    """Four synthetic objects accepted one after another, as the carrier would: a labelled cairn on the
    shingle, a post on the pier, a flag built onto the cairn and a painted log further left (at scale 4, big
    enough to clear the floor on size; the flag, built onto the cairn, may stay small).
    Returns their manifests in seq order."""
    out = []

    def accept(m, at):
        shore.accept(m, at, at, "world-1", "0" * 40)
        out.append(m)
    m, _ = place_first(shore, lambda x, y: manifest("2027-03-18-cairn", "maker-a", CAIRN, STONES, "shingle", x, y,
                                                     scale=4, label=("CAIRN", "right")), dry_spots(ref, 2520, 2800))
    accept(m, "2027-03-18T04:30:00Z")
    post = ["ooo"] * 2 + ["ttt"] * 18
    m, _ = place_first(shore, lambda x, y: manifest("2027-03-18-post", "maker-b", post, {"o": (232, 230, 222), "t": (196, 52, 40)},
                                                     "pier", x, y, anchor=(1, 19), scale=4), deck_spots(ref, 2200, 2400))
    accept(m, "2027-03-18T04:31:00Z")
    cairn = shore.byid["2027-03-18-cairn"]
    top = cairn.top
    cols = sorted(set(i % ref.cw + ref.cx for i in cairn.solid if i // ref.cw + ref.cy == top and i not in cairn.label))
    flag = ["rrrr.", "rrrrr", "rrrr.", "rr...", "m....", "m....", "m....", "m....", "m...."]
    pal = {"r": (210, 60, 48), "m": (70, 62, 55)}
    m, _ = place_first(shore, lambda x, y: manifest("2027-03-19-flag", "maker-a", flag, pal, "2027-03-18-cairn", x, y,
                                                     anchor=(0, 8)), [(x, top - 1) for x in cols])
    accept(m, "2027-03-19T04:30:00Z")
    log = ["..wwwwwwwwwwwwwwww..", ".wwvvwwwwwwwwwwvvww.", "wvvwwwwvvwwwwwwwwwvw", "wwwwvvwwwwwwvvwwwwww", "wwvwwwwwwvwwwwwwvvww",
           ".wwwwvvwwwwwwvwwwww.", "..wwwwwwwwwwwwwwww.."]
    m, _ = place_first(shore, lambda x, y: manifest("2027-03-19-log", "maker-b", log, LOG,
                                                     "shingle", x, y, scale=4, anchor=(10, 6)), dry_spots(ref, 2240, 2460))
    accept(m, "2027-03-19T04:31:00Z")
    return out
