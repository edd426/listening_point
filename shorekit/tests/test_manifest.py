import hashlib
import json
import unittest

import support
from shorekit.errors import ShoreError
from shorekit.manifest import parse_manifest
from shorekit.strictjson import canonical, loads

NAMES = ["2026-11-02-cairn", "2026-11-02-flag", "2026-11-03-shell", "2026-11-03-log", "2026-11-04-bottle"]


def obj(name="2026-11-02-cairn"):
    return support.fixture_obj(name)


class TestStrictJson(unittest.TestCase):
    def test_accepts_plain_objects(self):
        self.assertEqual(loads(b'{"a": [1, -2, {"b": "c"}]}', 100, 3), {"a": [1, -2, {"b": "c"}]})

    def test_rejects(self):
        for data in (b'{"a": 1.0}', b'{"a": 1e3}', b'{"a": NaN}', b'{"a": 1, "a": 2}', b'{"a": "\\u0041"}',
                     b'[1]', b'"x"', b'{"a": 1} x', b'', b'{"a": "\xc3\xa9"}', b'{"a": [[[[1]]]]}',
                     b'{"a": 1234567890123456}'):
            with self.assertRaises(ShoreError) as cm:
                loads(data, 100, 3)
            self.assertEqual(cm.exception.code, "E_PARSE", data)

    def test_size_limit(self):
        with self.assertRaises(ShoreError):
            loads(b'{"a": 1}' + b" " * 100, 100, 3)

    def test_canonical(self):
        self.assertEqual(canonical({"b": 1, "a": [2, "x"]}), b'{"a":[2,"x"],"b":1}')


class TestManifest(unittest.TestCase):
    def test_fixtures_parse(self):
        for n in NAMES:
            m = parse_manifest(support.fixture(n))
            self.assertEqual(m.id, n)
            self.assertEqual(m.sha256, hashlib.sha256(m.canonical).hexdigest())

    def test_identity_ignores_layout(self):
        a = parse_manifest(support.fixture("2026-11-02-cairn"))
        b = parse_manifest(json.dumps(obj(), indent=3).encode("ascii"))
        self.assertEqual(a.sha256, b.sha256)
        self.assertEqual(a.canonical, canonical(obj()))

    def test_example_shape_from_the_plan(self):
        o = {"shore": 1, "id": "2026-11-02-cairn", "maker": "maker-a", "kit": "1.0.0", "reference": "r1",
             "palette": {"a": [134, 130, 122], "b": [96, 80, 64]}, "rows": ["..aa..", ".abba.", "aabbaa"],
             "scale": 1, "anchor": [3, 2], "place": {"on": "shingle", "x": 2310, "y": 1641},
             "label": {"text": "FIRST STONE", "side": "right"}}
        m = parse_manifest(canonical(o))
        self.assertEqual((m.w, m.h, m.anchor, m.label), (6, 3, (3, 2), "FIRST STONE"))

    def test_schema_errors(self):
        cases = [
            (lambda o: o.pop("rows"), "E_SCHEMA"),
            (lambda o: o.update(extra=1), "E_SCHEMA"),
            (lambda o: o.update(scale=True), "E_SCHEMA"),
            (lambda o: o.update(id="2026-02-30-x"), "E_ID"),
            (lambda o: o.update(id="2026-11-02-Cairn"), "E_ID"),
            (lambda o: o["rows"].append("." * 18), "E_SCHEMA"),
            (lambda o: o["palette"].update(z=[1, 2, 3]), "E_SCHEMA"),
            (lambda o: o.update(anchor=[18, 0]), "E_SCHEMA"),
            (lambda o: o["place"].update(on="grass"), "E_SCHEMA"),
            (lambda o: o["place"].update(on="2026-11-02-cairn"), "E_SCHEMA"),
            (lambda o: o.update(label={"text": "HI", "side": "up"}), "E_SCHEMA"),
        ]
        for mutate, code in cases:
            o = obj()
            mutate(o)
            with self.assertRaises(ShoreError) as cm:
                parse_manifest(canonical(o))
            self.assertEqual(cm.exception.code, code, cm.exception.line())


if __name__ == "__main__":
    unittest.main()
