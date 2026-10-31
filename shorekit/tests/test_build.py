"""The zipapp is reproducible, runs under -I, and checks itself against kit.lock."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

import support as S
from shorekit import KIT_VERSION
from shorekit.build import build, entries


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shorekit-build-")
        self.addCleanup(shutil.rmtree, self.tmp)

    def pyz(self, path):
        return subprocess.run([sys.executable, "-I", path] + self.args, capture_output=True, text=True, cwd=self.tmp)

    def test_two_builds_are_identical(self):
        a, sa = build(os.path.join(self.tmp, "a", "shorekit.pyz"))
        b, sb = build(os.path.join(self.tmp, "b", "shorekit.pyz"))
        self.assertEqual(sa, sb)
        self.assertEqual(open(a, "rb").read(), open(b, "rb").read())
        self.assertEqual(hashlib.sha256(open(a, "rb").read()).hexdigest(), sa)
        with zipfile.ZipFile(a) as z:
            names = z.namelist()
            self.assertIsNone(z.testzip())
            self.assertTrue(all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in z.infolist()))
        self.assertEqual(names, [n for n, _ in entries()])
        self.assertEqual(names[0], "__main__.py")
        self.assertEqual(names[1:], sorted(names[1:]))
        self.assertFalse(any("tests" in n or n.endswith("build.py") for n in names))
        self.assertTrue(open(a, "rb").read().startswith(b"#!/usr/bin/env python3\n"))

    def test_runs_isolated_and_checks_its_lock(self):
        root = S.new_shore(self.tmp)
        path, sha = build(os.path.join(root, "kit", "shorekit.pyz"))
        self.args = ["status"]
        r = self.pyz(path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith("KIT %s sha256=%s (no kit.lock" % (KIT_VERSION, sha)), r.stdout)
        lock = {"shore_kit_lock": 1, "kit": KIT_VERSION, "commit": "0" * 40, "pyz_sha256": sha, "reference": "r1"}
        with open(os.path.join(root, "kit.lock"), "w") as f:
            json.dump(lock, f)
        r = self.pyz(path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        first, second = r.stdout.splitlines()[:2]
        self.assertEqual(first, "KIT OK %s sha256=%s commit=%s" % (KIT_VERSION, sha, "0" * 40))
        self.assertTrue(second.startswith("SHORE reference=r1"))
        lock["pyz_sha256"] = "f" * 64
        with open(os.path.join(root, "kit.lock"), "w") as f:
            json.dump(lock, f)
        r = self.pyz(path)
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stdout.startswith("KIT MISMATCH"))
        self.args = ["check", os.path.join(S.FIXTURES, "objects", "2026-11-02-cairn.json")]
        r = self.pyz(path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith("PASS 2026-11-02-cairn"))


if __name__ == "__main__":
    unittest.main()
