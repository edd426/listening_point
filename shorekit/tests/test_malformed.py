"""At least 200 malformed inputs, each refused with a ShoreError (never another exception), in
under a second, with under 50 MB traced at the peak (BUILD section 7, phase 1)."""
import os
import shutil
import struct
import tempfile
import time
import tracemalloc
import unittest
import zlib

import pngmake as P
import support as S
from shorekit.errors import ShoreError
from shorekit.importer import png_to_manifest
from shorekit.ledger import Shore, ledger_bytes, parse_ledger, parse_queue
from shorekit.manifest import manifest_from_obj, parse_manifest
from shorekit.png import read_reference_png, write_png
from shorekit.reference import load_reference
from shorekit.rules import evaluate
from shorekit.strictjson import canonical

LIMIT_S = 1.0
LIMIT_BYTES = 50 * 1024 * 1024


def judge_manifest(data):
    m = parse_manifest(data)
    errs = evaluate(m, S.reference(), [], 1)[0]
    if errs:
        raise errs[0]


def base():
    return S.fixture_obj("2026-11-02-cairn")


def mut(f):
    o = base()
    f(o)
    return canonical(o)


def setk(path, value):
    def f(o):
        d = o
        for k in path[:-1]:
            d = d[k]
        d[path[-1]] = value
    return f


def manifest_cases():
    good = canonical(base())
    raw = [b"", b"   ", b"[]", b'"x"', b"null", b"{", good[:-1], good + b"x", good + b"}", b"\xef\xbb\xbf" + good,
           good.replace(b"maker-a", b"maker-\xc3\xa9"), good.replace(b",", b",\x00", 1), good.replace(b",", b",\x7f", 1),
           good.replace(b"maker-a", b"maker-\\u0061"), good + b" " * 16384, b" " * (1 << 20), b"[" * (1 << 20),
           b"[" * 16000, b'{"a":' * 3000, b'{"a":[[[[[1]]]]]}', good.replace(b'"scale":1', b'"scale":NaN'),
           good.replace(b'"scale":1', b'"scale":Infinity'), good.replace(b'"scale":1', b'"scale":-Infinity'),
           good.replace(b'"scale":1', b'"scale":1.0'), good.replace(b'"scale":1', b'"scale":1e0'),
           good.replace(b'"x":2600', b'"x":2600.5'), good.replace(b'[122,118,110]', b'[1.22e2,118,110]'),
           good.replace(b'"anchor":[8,17]', b'"anchor":[-0.0,17]'), good.replace(b'"x":2600', b'"x":100000000000000000000'),
           good.replace(b'"x":2600', b'"x":' + b"9" * 5000), good.replace(b'{"anchor"', b'{"shore":1,"anchor"'),
           good.replace(b'"x":2600', b'"x":2600,"x":2601'), good.replace(b'"a":[122', b'"a":[1,2,3],"a":[122'),
           good.replace(b"}", b",}", 1), good.replace(b'"', b"'"), b"// c\n" + good,
           good.replace(b'"maker-a"', b'"maker\ta"'), good.replace(b'"maker-a"', b'"maker\na"')]
    cases = [("manifest bytes %d" % i, judge_manifest, d) for i, d in enumerate(raw)]
    schema = []
    for k in ("anchor", "id", "kit", "maker", "palette", "place", "reference", "rows", "scale", "shore"):
        schema.append(("missing " + k, lambda o, k=k: o.pop(k)))
    schema += [
        ("extra key", setk(["extra"], 1)), ("extra in place", setk(["place", "z"], 1)),
        ("extra in label", setk(["label"], {"text": "A", "side": "left", "z": 1})),
        ("shore 2", setk(["shore"], 2)), ("shore str", setk(["shore"], "1")), ("shore bool", setk(["shore"], True)),
        ("shore null", setk(["shore"], None)),
        ("id upper", setk(["id"], "2026-11-02-Cairn")), ("id no slug", setk(["id"], "2026-11-02-")),
        ("id long slug", setk(["id"], "2026-11-02-" + "a" * 41)), ("id month 13", setk(["id"], "2026-13-01-a")),
        ("id feb 29", setk(["id"], "2026-02-29-a")), ("id year", setk(["id"], "1999-01-01-a")),
        ("id space", setk(["id"], "2026-11-02-a b")), ("id int", setk(["id"], 20261102)),
        ("maker empty", setk(["maker"], "")), ("maker upper", setk(["maker"], "A")), ("maker dash", setk(["maker"], "-x")),
        ("maker long", setk(["maker"], "m" * 33)), ("maker int", setk(["maker"], 7)), ("maker underscore", setk(["maker"], "maker_a")),
        ("kit short", setk(["kit"], "1.0")), ("kit v", setk(["kit"], "v1.0.0")), ("kit int", setk(["kit"], 1)),
        ("kit four", setk(["kit"], "1.0.0.0")), ("ref r0", setk(["reference"], "r0")), ("ref upper", setk(["reference"], "R1")),
        ("ref bare", setk(["reference"], "r")), ("ref int", setk(["reference"], 1)),
        ("palette list", setk(["palette"], [])), ("palette empty", setk(["palette"], {})),
        ("palette 17", setk(["palette"], {chr(97 + i): [1, 2, 3] for i in range(17)})),
        ("palette key upper", setk(["palette", "A"], [1, 2, 3])), ("palette key two", setk(["palette", "aa"], [1, 2, 3])),
        ("palette key digit", setk(["palette", "1"], [1, 2, 3])), ("palette 2 ch", setk(["palette", "a"], [1, 2])),
        ("palette 4 ch", setk(["palette", "a"], [1, 2, 3, 4])), ("palette 256", setk(["palette", "a"], [256, 0, 0])),
        ("palette -1", setk(["palette", "a"], [-1, 0, 0])), ("palette str", setk(["palette", "a"], ["1", 2, 3])),
        ("palette bool", setk(["palette", "a"], [True, 0, 0])), ("palette unused", setk(["palette", "z"], [1, 2, 3])),
        ("rows str", setk(["rows"], "abc")), ("rows empty", setk(["rows"], [])), ("rows 65", setk(["rows"], ["a"] * 65)),
        ("row 65 wide", setk(["rows"], ["a" * 65])), ("rows ragged", lambda o: o["rows"].append("a")),
        ("row unknown char", lambda o: o["rows"].__setitem__(0, "x" * 18)), ("row int", lambda o: o["rows"].__setitem__(0, 5)),
        ("row empty str", lambda o: o["rows"].__setitem__(0, "")),
        ("first row empty", lambda o: o["rows"].insert(0, "." * 18)),
        ("last col empty", lambda o: o.__setitem__("rows", [r + "." for r in o["rows"]])),
        ("first col empty", lambda o: o.__setitem__("rows", ["." + r for r in o["rows"]])),
        ("scale 0", setk(["scale"], 0)), ("scale 5", setk(["scale"], 5)), ("scale str", setk(["scale"], "1")),
        ("scale bool", setk(["scale"], True)),
        ("anchor empty", setk(["anchor"], [])), ("anchor one", setk(["anchor"], [1])), ("anchor three", setk(["anchor"], [1, 2, 3])),
        ("anchor neg", setk(["anchor"], [-1, 0])), ("anchor x out", setk(["anchor"], [18, 0])),
        ("anchor y out", setk(["anchor"], [0, 18])), ("anchor str", setk(["anchor"], ["0", 0])), ("anchor obj", setk(["anchor"], {})),
        ("place list", setk(["place"], [])), ("place no on", lambda o: o["place"].pop("on")),
        ("place grass", setk(["place", "on"], "grass")), ("place self", setk(["place", "on"], "2026-11-02-cairn")),
        ("place on int", setk(["place", "on"], 123)), ("place on bad date", setk(["place", "on"], "2026-02-30-x")),
        ("place x -1", setk(["place", "x"], -1)), ("place x big", setk(["place", "x"], 10000)),
        ("place y str", setk(["place", "y"], "1")), ("place x bool", setk(["place", "x"], True)),
        ("label str", setk(["label"], "TEXT")), ("label empty obj", setk(["label"], {})),
        ("label no side", setk(["label"], {"text": "A"})), ("label side up", setk(["label"], {"text": "A", "side": "up"})),
        ("label text int", setk(["label"], {"text": 5, "side": "left"})),
        ("label text 65", setk(["label"], {"text": "A" * 65, "side": "left"})),
        ("label lower", setk(["label"], {"text": "tide", "side": "left"})),
        ("label 13", setk(["label"], {"text": "THIRTEEN CHAR", "side": "left"})),
        ("label 9", setk(["label"], {"text": "NINE CHAR", "side": "left"})),
        ("glow not a key", setk(["glow"], "z")), ("glow two keys", setk(["glow"], "ab")), ("glow int", setk(["glow"], 1)),
        ("glow grey", setk(["glow"], "a")),
        ("label url", setk(["label"], {"text": "A.COM", "side": "left"})),
        ("label lead", setk(["label"], {"text": " LEAD", "side": "left"})),
        ("label slash", setk(["label"], {"text": "A/B", "side": "left"})),
        ("15 cells", lambda o: o.update(rows=["aaaaa"] * 3, palette={"a": [122, 118, 110]}, anchor=[2, 2])),
        ("channel 241", setk(["palette", "a"], [241, 118, 110])), ("far colour", setk(["palette", "a"], [10, 200, 30])),
        ("floating", setk(["place", "y"], 1600)), ("off the shore", setk(["place", "x"], 3000)),
        ("on keep-out", lambda o: o["place"].update(x=2714, y=1670)), ("on the deck from shingle", setk(["place"], {"on": "pier", "x": 2600, "y": 1655})),
        ("build onto nothing", setk(["place", "on"], "2026-11-01-ghost")),
    ]
    cases += [("manifest " + n, judge_manifest, mut(f)) for n, f in schema]
    return cases


def import_cases():
    rows = [bytes([122, 118, 110, 255]) * 6] * 6
    good = P.png(6, 6, rows)
    ih = P.ihdr

    def build(*chunks):
        return P.SIG + b"".join(chunks)

    idat = P.chunk(b"IDAT", zlib.compress(P.filter_rows(rows, 4, (0,))))
    iend = P.chunk(b"IEND", b"")
    bomb = zlib.compress(b"\x00" * 30000000, 9)
    datas = [
        b"", b"\x89PNG", b"GIF89a" + good[6:], good[:-1], good + b"\x00", good + P.chunk(b"tEXt", b"a\x00b"),
        build(idat, ih(6, 6), iend), build(P.chunk(b"IHDR", b"\x00" * 12), idat, iend),
        build(ih(65, 6), idat, iend), build(ih(6, 65), idat, iend), build(ih(0, 6), idat, iend),
        build(ih(2 ** 31, 6), idat, iend), build(ih(100000, 100000), P.chunk(b"IDAT", bomb[:60000]), iend),
        build(ih(64, 64), P.chunk(b"IDAT", bomb[:60000]), iend),
        build(ih(6, 6, depth=16), idat, iend), build(ih(6, 6, depth=1), idat, iend), build(ih(6, 6, depth=4), idat, iend),
        build(ih(6, 6, ctype=1), idat, iend), build(ih(6, 6, ctype=5), idat, iend), build(ih(6, 6, ctype=7), idat, iend),
        build(ih(6, 6, comp=1), idat, iend), build(ih(6, 6, filt=1), idat, iend), build(ih(6, 6, inter=1), idat, iend),
        build(P.chunk(b"IHDR", struct.pack(">IIBBBBB", 6, 6, 8, 6, 0, 0, 0), crc=1), idat, iend),
        build(ih(6, 6), P.chunk(b"IDAT", zlib.compress(P.filter_rows(rows, 4, (0,))), crc=7), iend),
        build(ih(6, 6), struct.pack(">I", 1 << 30) + b"IDAT" + b"xxxx", iend),
        build(ih(6, 6), P.chunk(b"ABCD", b""), idat, iend), build(ih(6, 6), P.chunk(b"ab1d", b""), idat, iend),
        build(ih(6, 6), idat), build(ih(6, 6), idat, P.chunk(b"IEND", b"x")), build(ih(6, 6), iend),
        build(ih(6, 6), idat, P.chunk(b"tEXt", b"a\x00b"), idat, iend), build(ih(6, 6), ih(6, 6), idat, iend),
        build(ih(6, 6), P.chunk(b"IDAT", b"garbage!"), iend),
        build(ih(6, 6), P.chunk(b"IDAT", zlib.compress(P.filter_rows(rows, 4, (0,)))[:-6]), iend),
        build(ih(6, 6), P.chunk(b"IDAT", zlib.compress(P.filter_rows(rows, 4, (0,))) + b"junk"), iend),
        build(ih(6, 6), P.chunk(b"IDAT", zlib.compress(P.filter_rows(rows + rows, 4, (0,)))), iend),
        build(ih(6, 6), P.chunk(b"IDAT", zlib.compress(P.filter_rows(rows[:5], 4, (0,)))), iend),
        build(ih(6, 6), P.chunk(b"IDAT", zlib.compress(b"\x05" + rows[0][:] + (b"\x00" + rows[0]) * 5)), iend),
        build(ih(2, 1, ctype=3), P.chunk(b"IDAT", zlib.compress(b"\x00\x00\x00")), iend),
        build(ih(2, 1, ctype=3), P.chunk(b"PLTE", b"\x01\x02"), P.chunk(b"IDAT", zlib.compress(b"\x00\x00\x00")), iend),
        build(ih(2, 1, ctype=3), P.chunk(b"PLTE", b"\x01" * 771), P.chunk(b"IDAT", zlib.compress(b"\x00\x00\x00")), iend),
        build(ih(2, 1, ctype=0), P.chunk(b"PLTE", b"\x01\x02\x03"), P.chunk(b"IDAT", zlib.compress(b"\x00\x00\x00")), iend),
        build(ih(2, 1, ctype=3), P.chunk(b"PLTE", b"\x01\x02\x03"), P.chunk(b"IDAT", zlib.compress(b"\x00\x00\x05")), iend),
        build(ih(2, 1, ctype=3), P.chunk(b"PLTE", b"\x01\x02\x03"), P.chunk(b"tRNS", b"\x00\x00"),
              P.chunk(b"IDAT", zlib.compress(b"\x00\x00\x00")), iend),
        build(ih(2, 1, ctype=6), P.chunk(b"tRNS", b"\x00\x00"), P.chunk(b"IDAT", zlib.compress(b"\x00" * 9)), iend),
        build(ih(2, 1, ctype=3), P.chunk(b"tRNS", b"\x00"), P.chunk(b"PLTE", b"\x01\x02\x03"),
              P.chunk(b"IDAT", zlib.compress(b"\x00\x00\x00")), iend),
        build(ih(2, 1, ctype=3), P.chunk(b"PLTE", b"\x01\x02\x03"), P.chunk(b"PLTE", b"\x01\x02\x03"),
              P.chunk(b"IDAT", zlib.compress(b"\x00\x00\x00")), iend),
        build(ih(2, 1, ctype=3), P.chunk(b"IDAT", zlib.compress(b"\x00\x00\x00")), P.chunk(b"PLTE", b"\x01\x02\x03"), iend),
        build(ih(2, 1, ctype=0), P.chunk(b"tRNS", b"\x01\x00"), P.chunk(b"IDAT", zlib.compress(b"\x00\x00\x00")), iend),
        good + b"\x00" * 65536,
        P.png(6, 6, [bytes([122, 118, 110, 128]) * 6] * 6), P.png(17, 1, [bytes(c for i in range(17) for c in (i * 7, 3, 3, 255))]),
        P.png(6, 6, [bytes(24)] * 6),
        build(ih(6, 6), *([P.chunk(b"tEXt", b"a\x00b")] * 70), idat, iend),
    ]

    def imp(d):
        png_to_manifest(d, "2026-11-05-x", "maker-a", "shingle", 2640, 1665, "r1")
    return [("import png %d" % i, imp, d) for i, d in enumerate(datas)]


def refpng_cases():
    grey = bytes(1280 * 640)
    good = write_png(1280, 640, grey, 0)
    ih = P.ihdr
    idat = P.chunk(b"IDAT", zlib.compress(b"".join(b"\x00" + bytes(1280) for _ in range(640))))
    iend = P.chunk(b"IEND", b"")
    datas = [
        (good[:-1], 0), (good + b"\x00", 0), (write_png(1280, 640, bytes([7]) * (1280 * 640), 0), 0),
        (write_png(1281, 640, bytes(1281 * 640), 0), 0), (write_png(1280, 639, bytes(1280 * 639), 0), 0),
        (good, 2), (P.SIG + ih(1280, 640, ctype=0, depth=16) + idat + iend, 0),
        (P.SIG + ih(1280, 640, ctype=0, inter=1) + idat + iend, 0),
        (P.SIG + ih(1280, 640, ctype=0) + P.chunk(b"tEXt", b"a\x00b") + idat + iend, 0),
        (P.SIG + ih(1280, 640, ctype=0) + P.chunk(b"IDAT", zlib.compress(b"".join(b"\x01" + bytes(1280) for _ in range(640)))) + iend, 0),
        (P.SIG + ih(1280, 640, ctype=0) + P.chunk(b"IDAT", zlib.compress(b"\x00" * 40000000, 9)) + iend, 0),
        (P.SIG + ih(1280, 640, ctype=0) + P.chunk(b"IDAT", b"nonsense") + iend, 0),
        (P.SIG + ih(1280, 640, ctype=0) + iend, 0), (b"\x00" * (3 * 1024 * 1024), 0),
        (P.SIG + idat + ih(1280, 640, ctype=0) + iend, 0),
    ]
    return [("reference png %d" % i, lambda d, ct=ct: read_reference_png(d, ct, "keepout.png"), d) for i, (d, ct) in enumerate(datas)]


_LEDGER = {}


def ledger_base():
    if not _LEDGER:
        tmp = tempfile.mkdtemp(prefix="shorekit-mal-")
        objects = os.path.join(tmp, "objects")
        os.makedirs(objects)
        shore = Shore(S.reference(), objects)
        for name, at in (("2026-11-02-cairn", "2026-11-02T04:30:00Z"), ("2026-11-02-flag", "2026-11-02T04:30:00Z"),
                         ("2026-11-03-shell", "2026-11-03T04:30:00Z")):
            m = manifest_from_obj(S.fixture_obj(name))
            with open(os.path.join(objects, m.id + ".json"), "wb") as f:
                f.write(m.canonical)
            shore.accept(m, at, at, "world-1", "0" * 40)
        _LEDGER.update(tmp=tmp, objects=objects, events=shore.events)
    return _LEDGER


def ledger_cases():
    b = ledger_base()

    def replay(d):
        s = Shore(S.reference(), b["objects"])
        for ev in parse_ledger(d):
            s.apply(ev)
        s.finish()

    def mutated(f):
        evs = [dict(e) for e in b["events"]]
        f(evs)
        return ledger_bytes(evs)
    good = ledger_bytes(b["events"])
    raw = [b"", b"[]", b'{"events":[]}', b'{"events":[],"shore_ledger":2}', b'{"events":{},"shore_ledger":1}',
           b'{"events":[1],"shore_ledger":1}', b'{"events":[],"shore_ledger":1,"x":1}', good.replace(b"\n", b"\n\x00", 1),
           good[:-3], b" " * (16 * 1024 * 1024 + 1), b'{"events":[' + b"[" * 50 + b"]" * 50 + b'],"shore_ledger":1}']
    muts = [
        lambda e: e[0].update(x=1), lambda e: e[0].pop("lands"), lambda e: e[0].update(seq="1"),
        lambda e: e[0].update(seq=True), lambda e: e[0].update(seq=0), lambda e: e[1].update(seq=1),
        lambda e: e[0].update(at="2026-11-02 04:30:00Z"), lambda e: e[0].update(at="2026-11-02T04:30:00"),
        lambda e: e[0].update(at="2026-11-31T04:30:00Z"), lambda e: e[0].update(at="2026-11-02T04:60:00Z"),
        lambda e: e[0].update(lands="2026-11-01T00:00:00Z"), lambda e: e[0].update(id="2026-11-02-Cairn"),
        lambda e: e[0].update(maker="Maker"), lambda e: e[0].update(world=""), lambda e: e[0].update(commit="abc"),
        lambda e: e[0].update(commit="A" * 40), lambda e: e[0].update(sha256="0" * 63), lambda e: e[0].update(reference="r0"),
        lambda e: e[0].update(kit="1"), lambda e: e[0].update(sha256="f" * 64), lambda e: e[1].update(at="2026-11-01T00:00:00Z"),
        lambda e: e.append({"seq": 4, "event": "storm", "at": "2026-11-04T00:00:00Z", "for": "2026-11-04-x", "takes": []}),
        lambda e: e.append({"seq": 4, "event": "storm", "at": "2026-11-04T00:00:00Z", "for": "2026-11-04-x",
                            "takes": ["2026-11-02-cairn", "2026-11-02-cairn"]}),
        lambda e: e.append({"seq": 4, "event": "storm", "at": "2026-11-04T00:00:00Z", "for": "2026-11-04-x",
                            "takes": ["2026-11-02-cairn"]}),
        lambda e: e.append({"seq": 4, "event": "veto", "at": "2026-11-04T00:00:00Z", "id": "2026-11-09-x",
                            "takes": ["2026-11-09-x"]}),
        lambda e: e.append({"seq": 4, "event": "veto", "at": "2026-11-04T00:00:00Z", "id": "2026-11-02-cairn",
                            "takes": ["2026-11-02-cairn"]}),
        lambda e: e.append({"seq": 4, "event": "veto", "at": "2026-11-04T00:00:00Z", "id": "2026-11-02-cairn",
                            "takes": "2026-11-02-cairn"}),
        lambda e: e.append(dict(e[0], seq=4, at="2026-11-04T04:30:00Z", lands="2026-11-04T04:30:00Z")), lambda e: e[2].update(maker="maker-b"),
        lambda e: e[1].update(id="2026-11-02-gone"), lambda e: e.insert(0, e.pop(2)),
    ]
    cases = [("ledger bytes %d" % i, replay, d) for i, d in enumerate(raw)]
    cases += [("ledger event %d" % i, replay, mutated(f)) for i, f in enumerate(muts)]
    return cases


def queue_cases():
    good = {"shore_queue": 1, "at": "2026-11-02T04:30:00Z", "lands": "2026-11-02T04:30:00Z",
            "candidates": [{"world": "world-1", "id": "2026-11-02-cairn", "commit": "0" * 40}]}

    def q(**kw):
        o = dict(good, **kw)
        return canonical({k: v for k, v in o.items() if v is not None})
    cand = good["candidates"][0]
    datas = [b"[]", q(shore_queue=2), q(at=None), q(at="tomorrow"), q(lands="2026-11-01T00:00:00Z"),
             q(candidates={}), q(candidates=[cand] * 2), q(candidates=[dict(cand, world="World")]),
             q(candidates=[dict(cand, id="../../etc")]), q(candidates=[dict(cand, commit="x")]),
             q(candidates=[{"world": "w", "id": "2026-11-02-a"}]),
             q(candidates=[dict(cand, id="2026-11-02-a%d" % i) for i in range(65)])]
    return [("queue %d" % i, parse_queue, d) for i, d in enumerate(datas)]


def refjson_cases():
    src = S.reference_dir()
    import json

    def load(name):
        with open(os.path.join(src, name), "rb") as f:
            return json.loads(f.read())

    def edit(name, f):
        o = load(name)
        f(o)
        return (name, canonical(o))
    datas = [
        edit("surfaces.json", lambda o: o["dry"]["top"].pop()),
        edit("surfaces.json", lambda o: o["deck"].append([1000, 1000])),
        edit("surfaces.json", lambda o: o["max_h"]["h"].pop()),
        edit("surfaces.json", lambda o: o.pop("min_h")),
        edit("surfaces.json", lambda o: o["min_h"]["h"].__setitem__(400, o["max_h"]["h"][400] + 1)),
        edit("surfaces.json", lambda o: o["region"].update(x0=1500)),
        edit("surfaces.json", lambda o: o["crop"].update(w=1279)),
        edit("surfaces.json", lambda o: o["dry"]["top"].__setitem__(500, o["dry"]["bottom"][500] + 1)),
        edit("surfaces.json", lambda o: o.update(reference="r2")),
        edit("palette.json", lambda o: o.update(d=0)),
        edit("palette.json", lambda o: o.update(entries=[])),
        edit("palette.json", lambda o: o["entries"].append(dict(o["entries"][0]))),
        edit("palette.json", lambda o: o["plaque"].pop("ink")),
        edit("palette.json", lambda o: o.pop("glow")),
        edit("palette.json", lambda o: o["glow"].append(dict(o["entries"][0]))),
        edit("conditions.json", lambda o: o["conditions"].pop()),
        edit("conditions.json", lambda o: o["conditions"][0]["lut"][0].pop()),
        edit("conditions.json", lambda o: o["vignette"].pop()),
        edit("conditions.json", lambda o: o["conditions"][1]["veil"]["alpha"].__setitem__(3, 257)),
        edit("conditions.json", lambda o: o["conditions"][3]["veil"].update(rgb=[300, 512, 300])),
        edit("conditions.json", lambda o: o["conditions"][2].update(name="noon")),
        edit("conditions.json", lambda o: o.update(cell=8)),
        edit("conditions.json", lambda o: o["conditions"][0].pop("top")),
        edit("conditions.json", lambda o: o["conditions"][2].update(lamps=257)),
    ]

    def run(item):
        name, data = item
        d = tempfile.mkdtemp(prefix="shorekit-ref-bad-")
        try:
            dst = os.path.join(d, "r1")
            shutil.copytree(src, dst)
            with open(os.path.join(dst, name), "wb") as f:
                f.write(data)
            load_reference(dst)
        finally:
            shutil.rmtree(d)
    return [("reference json %d" % i, run, item) for i, item in enumerate(datas)]


class TestVeil(unittest.TestCase):
    def test_a_veil_brighter_than_255_is_linear_and_allowed(self):
        """Daylight fog is brighter than 255 in the renderer's linear light; the tone curve takes 0-511."""
        src = S.reference_dir()
        d = tempfile.mkdtemp(prefix="shorekit-ref-veil-")
        try:
            dst = os.path.join(d, "r1")
            shutil.copytree(src, dst)
            p = os.path.join(dst, "conditions.json")
            import json
            with open(p, "rb") as f:
                o = json.loads(f.read())
            o["conditions"][3]["veil"]["rgb"] = [300, 511, 0]
            with open(p, "wb") as f:
                f.write(canonical(o))
            ref = load_reference(dst)
            self.assertEqual(ref.conditions[3].veil_rgb, (300, 511, 0))
        finally:
            shutil.rmtree(d)


class TestMalformed(unittest.TestCase):
    def test_every_malformed_input_is_refused_fast(self):
        S.reference()
        ledger_base()
        cases = manifest_cases() + import_cases() + refpng_cases() + ledger_cases() + queue_cases() + refjson_cases()
        self.assertGreaterEqual(len(cases), 200)
        slow = []
        for name, fn, data in cases:
            tracemalloc.start()
            t0 = time.perf_counter()
            try:
                fn(data)
                code = None
            except ShoreError as e:
                code = e.code
            elapsed = time.perf_counter() - t0
            peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            with self.subTest(name):
                self.assertIsNotNone(code, "accepted")
                self.assertLess(peak, LIMIT_BYTES)
                if elapsed >= LIMIT_S:
                    slow.append((name, elapsed))
        self.assertEqual(slow, [])

    @classmethod
    def tearDownClass(cls):
        if _LEDGER:
            shutil.rmtree(_LEDGER["tmp"], ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
