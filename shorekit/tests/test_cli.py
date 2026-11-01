import contextlib
import hashlib
import io
import os
import shutil
import struct
import tempfile
import unittest
import zlib

import pngmake as P
import support as S
from shorekit.cli import main
from shorekit.manifest import parse_manifest


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue().splitlines()


def decode_png(path):
    """Pixels of a PNG written by write_png (filter 0 rows), for checking the printed hash."""
    data = open(path, "rb").read()
    w, h, depth, ctype = struct.unpack(">IIBB", data[16:26])
    pos, idat = 8, b""
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        if data[pos + 4:pos + 8] == b"IDAT":
            idat += data[pos + 8:pos + 8 + n]
        pos += 12 + n
    raw = zlib.decompress(idat)
    stride = 3 * w
    return w, h, b"".join(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)] for y in range(h))


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shorekit-cli-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.shore = S.new_shore(self.tmp)
        self.fix = os.path.join(S.FIXTURES, "objects")

    def test_status(self):
        code, lines = run(["status", "--shore", self.shore])
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith("KIT 1.2.0 unpacked (not a zipapp) (no kit.lock found"))
        self.assertTrue(lines[1].startswith("SHORE reference=r1 digest="))
        self.assertIn("ledger=0 events live=0/48", lines[1])

    def test_check(self):
        code, lines = run(["check", os.path.join(self.fix, "2026-11-02-cairn.json"), "--shore", self.shore])
        self.assertEqual((code, lines), (0, ["PASS 2026-11-02-cairn: seq 1, draws 1 of 1, 208 solid px, 34 shadow px"]))
        code, lines = run(["check", os.path.join(self.fix, "2026-11-03-shell.json"), "--shore", self.shore])
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["E_ON there is no object 2026-11-02-cairn on the shore to build onto",
                                 "FAIL 2026-11-03-shell: 1 problem"])
        bad = os.path.join(self.tmp, "bad.json")
        with open(bad, "wb") as f:
            f.write(b'{"shore": 1.5}')
        code, lines = run(["check", bad, "--shore", self.shore])
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], "FAIL: the manifest does not parse")
        code, lines = run(["check", bad])
        self.assertEqual(code, 2)

    def test_preview(self):
        out = os.path.join(self.tmp, "pv")
        code, lines = run(["preview", os.path.join(self.fix, "2026-11-03-log.json"), "--shore", self.shore, "--out", out])
        self.assertEqual(code, 0, lines)
        self.assertTrue(lines[0].startswith("PASS 2026-11-03-log"))
        sheet = [l for l in lines if l.startswith("SHEET")][0]
        zoom = [l for l in lines if l.startswith("ZOOM")][0]
        for line, name in ((sheet, "sheet.png"), (zoom, "zoom.png")):
            w, h, px = decode_png(os.path.join(out, name))
            self.assertIn("%dx%d" % (w, h), line)
            self.assertTrue(line.endswith("pixels-sha256=" + hashlib.sha256(px).hexdigest()))
        self.assertIn("2560x1280 (noon, golden, night, fog)", sheet)

    def test_preview_draws_a_failing_object_too(self):
        out = os.path.join(self.tmp, "pv")
        obj = S.fixture_obj("2026-11-02-cairn")
        obj["place"]["y"] = 1600
        p = os.path.join(self.tmp, "float.json")
        with open(p, "wb") as f:
            f.write(S.manifest_bytes(obj))
        code, lines = run(["preview", p, "--shore", self.shore, "--out", out])
        self.assertEqual(code, 1)
        self.assertTrue(any(l.startswith("ZOOM") for l in lines))

    def test_import_then_check(self):
        rows = [bytes([122, 118, 110, 255]) * 6] * 5
        png = os.path.join(self.tmp, "p.png")
        with open(png, "wb") as f:
            f.write(P.png(6, 5, rows))
        out = os.path.join(self.tmp, "p.json")
        code, lines = run(["import", png, "-o", out, "--id", "2026-11-05-pebble", "--maker", "maker-a", "--on", "shingle",
                           "--at", "2620,1665", "--ref-id", "r1", "--label", "STONE"])
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines, ["WROTE %s: 6x5 cells, 1 colours, anchor (2,4)" % out])
        self.assertEqual(parse_manifest(open(out, "rb").read()).label, "STONE")
        code, lines = run(["check", out, "--shore", self.shore])
        self.assertEqual(code, 0, lines)
        code, lines = run(["import", png, "-o", out, "--id", "2026-11-05-pebble", "--maker", "maker-a", "--on", "shingle",
                           "--at", "2640,1665"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
