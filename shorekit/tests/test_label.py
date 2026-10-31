"""Labels: 1-12 characters of [A-Z0-9 .'-], drawn in the kit's own 5x7 font. No homoglyphs,
no bidi controls, no URLs."""
import unittest

import support
from shorekit.errors import ShoreError
from shorekit.font import GLYPHS, PLAQUE_H, check_label, plaque_cells, plaque_width
from shorekit.manifest import parse_manifest
from shorekit.rules import check_local
from shorekit.strictjson import canonical


def with_label(text):
    o = support.fixture_obj("2026-11-03-log")
    o["label"]["text"] = text
    return o


class TestLabelText(unittest.TestCase):
    def test_good(self):
        for t in ("A", "FIRST STONE", "SEEN AT DAWN", "NO. 5", "IT'S HERE", "X-1", "WAIT...", "0O0O", "123456789012"):
            self.assertEqual(check_label(t), t)

    def test_bad_text(self):
        for t in ("", "lowercase", "Hello", "THIRTEEN CHAR", " LEAD", "TRAIL ", "TWO  SPACES", "WWW.EXAMPLE",
                  "A.B", "HTTP://X", "A/B", "A:B", "A_B", "A,B", "A!", "A?", "A\"B", "A@B", "#1", "A+B", "(A)"):
            with self.assertRaises(ShoreError, msg=t) as cm:
                check_label(t)
            self.assertEqual(cm.exception.code, "E_LABEL")

    def test_label_through_the_rules(self):
        ref = support.reference()
        m = parse_manifest(canonical(with_label("tide")))
        self.assertEqual([e.code for e in check_local(m, ref)], ["E_LABEL"])

    def test_non_ascii_never_parses(self):
        # Cyrillic A, Greek Omicron, fullwidth A, zero-width space, right-to-left override, BOM,
        # non-breaking space, combining acute: all refused as bytes before any JSON is read
        for ch in ("А", "Ο", "Ａ", "​", "‮", "﻿", " ", "É"):
            data = canonical(with_label("SEEN")).replace(b'"SEEN"', ('"SE%sN"' % ch).encode("utf-8"))
            with self.assertRaises(ShoreError) as cm:
                parse_manifest(data)
            self.assertEqual(cm.exception.code, "E_PARSE", repr(ch))

    def test_escapes_never_parse(self):
        for esc in (b"\\u0410", b"\\u202e", b"\\t", b"\\n", b"\\u0041", b'\\"'):
            data = canonical(with_label("SEEN")).replace(b'"SEEN"', b'"SE' + esc + b'N"')
            with self.assertRaises(ShoreError) as cm:
                parse_manifest(data)
            self.assertEqual(cm.exception.code, "E_PARSE", esc)


class TestFont(unittest.TestCase):
    def test_glyphs(self):
        self.assertEqual(sorted(GLYPHS), sorted("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .'-"))
        for ch, g in GLYPHS.items():
            self.assertEqual(len(g), 7, ch)
            self.assertTrue(all(len(r) == 5 and set(r) <= {"#", "."} for r in g), ch)
        bitmaps = [g for ch, g in GLYPHS.items()]
        self.assertEqual(len(set(bitmaps)), len(bitmaps), "two glyphs look the same")
        self.assertNotEqual(GLYPHS["0"], GLYPHS["O"])
        self.assertNotEqual(GLYPHS["1"], GLYPHS["I"])

    def test_plaque(self):
        rows = plaque_cells("SEEN AT DAWN")
        self.assertEqual(len(rows), PLAQUE_H)
        self.assertEqual(len(rows[0]), plaque_width(12))
        self.assertEqual(plaque_width(12), 150)
        self.assertEqual(rows[0][:3], "..w")
        self.assertEqual(rows[-1][:3], "..w")
        ink = sum(r.count("i") for r in rows)
        dots = sum(GLYPHS[c][y].count("#") for c in "SEEN AT DAWN" for y in range(7))
        self.assertEqual(ink, 4 * dots)


if __name__ == "__main__":
    unittest.main()
