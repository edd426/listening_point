import json
import unittest

import pngmake as P
import support
from shorekit.errors import ShoreError
from shorekit.importer import png_to_manifest, pretty
from shorekit.manifest import parse_manifest
from shorekit.png import read_import_png, read_reference_png, write_png


def picture():
    """A 7x5 RGBA picture: a transparent border round a 5x3 two-colour stone."""
    T, A, B = (0, 0, 0, 0), (122, 118, 110, 255), (196, 132, 46, 255)
    rows = [[T] * 7,
            [T, A, A, A, A, A, T],
            [T, A, B, B, B, A, T],
            [T, A, A, A, A, A, T],
            [T] * 7]
    return 7, 5, [p for r in rows for p in r]


def norm(px):
    return [p if p[3] else (0, 0, 0, 0) for p in px]


class TestImportReader(unittest.TestCase):
    def test_every_filter(self):
        w, h, px = picture()
        rows = P.rgba_rows(px, w)
        for f in range(5):
            got = read_import_png(P.png(w, h, rows, 6, filters=(f,)))
            self.assertEqual(got, (w, h, px), "filter %d" % f)
        got = read_import_png(P.png(w, h, rows, 6, filters=(4, 3, 2, 1, 0), idat_split=3))
        self.assertEqual(got[2], px)

    def test_colour_types(self):
        w, h, px = picture()
        rgb_rows = [bytes(c for p in px[y * w:(y + 1) * w] for c in (p[:3] if p[3] else (1, 2, 3))) for y in range(h)]
        got = read_import_png(P.png(w, h, rgb_rows, 2, filters=(1, 4), trns=bytes([0, 1, 0, 2, 0, 3])))
        self.assertEqual(norm(got[2]), px)
        pal = [(1, 2, 3), (122, 118, 110), (196, 132, 46)]
        idx = {(1, 2, 3): 0, (122, 118, 110): 1, (196, 132, 46): 2}
        prow = [bytes(idx[p[:3] if p[3] else (1, 2, 3)] for p in px[y * w:(y + 1) * w]) for y in range(h)]
        got = read_import_png(P.png(w, h, prow, 3, plte=bytes(c for p in pal for c in p), trns=b"\x00"))
        self.assertEqual(norm(got[2]), px)
        grey = read_import_png(P.png(2, 1, [bytes([7, 9])], 0, trns=b"\x00\x07"))
        self.assertEqual(grey[2], [(7, 7, 7, 0), (9, 9, 9, 255)])
        ga = read_import_png(P.png(2, 1, [bytes([7, 255, 9, 0])], 4))
        self.assertEqual(ga[2], [(7, 7, 7, 255), (9, 9, 9, 0)])

    def test_ancillary_chunks_are_skipped(self):
        w, h, px = picture()
        data = P.png(w, h, P.rgba_rows(px, w), 6, extra=[P.chunk(b"sRGB", b"\x00"), P.chunk(b"tEXt", b"k\x00v")])
        self.assertEqual(read_import_png(data)[2], px)


class TestImport(unittest.TestCase):
    def test_png_to_manifest(self):
        w, h, px = picture()
        obj, notes = png_to_manifest(P.png(w, h, P.rgba_rows(px, w)), "2026-11-05-pebble", "maker-a", "shingle",
                                     2650, 1670, "r1")
        self.assertEqual(obj["rows"], ["aaaaa", "abbba", "aaaaa"])
        self.assertEqual(obj["palette"], {"a": [122, 118, 110], "b": [196, 132, 46]})
        self.assertEqual(obj["anchor"], [2, 2])
        self.assertEqual(notes, ["trimmed to 5x3 cells from 7x5 (offset 1,1)"])
        m = parse_manifest(pretty(obj))
        self.assertEqual(json.loads(pretty(obj)), obj)
        self.assertEqual(m.opaque_cells(), 15)

    def test_refusals(self):
        w, h, px = picture()
        semi = list(px)
        semi[8] = (122, 118, 110, 128)
        many = [(i * 9, i * 3, 7, 255) for i in range(17)]
        for data, text in ((P.png(w, h, P.rgba_rows(semi, w)), "partly transparent"),
                           (P.png(17, 1, P.rgba_rows(many, 17)), "more than 16 colours"),
                           (P.png(2, 1, [bytes(8)]), "fully transparent")):
            with self.assertRaises(ShoreError) as cm:
                png_to_manifest(data, "2026-11-05-x", "maker-a", "shingle", 2650, 1670, "r1")
            self.assertIn(text, cm.exception.text)


class TestReferenceReader(unittest.TestCase):
    def test_round_trip(self):
        grey = bytes((0 if (i // 7) % 3 else 255) for i in range(1280 * 640))
        self.assertEqual(read_reference_png(write_png(1280, 640, grey, 0), 0, "k"), grey)
        rgb = bytes(i % 251 for i in range(1280 * 640 * 3))
        self.assertEqual(read_reference_png(write_png(1280, 640, rgb, 2), 2, "c"), rgb)

    def test_keepout_values(self):
        with self.assertRaises(ShoreError):
            read_reference_png(write_png(1280, 640, bytes([7]) * (1280 * 640), 0), 0, "k")

    def test_needs_filter_zero(self):
        rows = [bytes(1280)] * 640
        data = P.png(1280, 640, rows, 0, filters=(1,))
        with self.assertRaises(ShoreError) as cm:
            read_reference_png(data, 0, "k")
        self.assertIn("filter 0", cm.exception.text)


if __name__ == "__main__":
    unittest.main()
