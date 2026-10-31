"""The CI guard that keeps real shore data out of this public repository."""
import importlib.util
import os
import unittest

import support as S

spec = importlib.util.spec_from_file_location("no_shore_data", os.path.join(S.ROOT, ".github", "scripts", "no_shore_data.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class TestGuard(unittest.TestCase):
    def test_flags_shore_data_and_spares_fixtures(self):
        files = {
            "shore/ledger.json": b"{}", "data/shore/objects/x.json": b"{}", "ledger.json": b"{}",
            "out/objects/2026-11-02-a.json": b"{}", "returned/2026-11-02-a.json": b"{}",
            "reference/r1/keepout.png": b"", "x/r2/noon.png": b"", "kit.lock": b"{}",
            "notes/thing.json": b'{"shore": 1, "id": "2026-11-02-a"}', "x/y.json": b'{"shore_ledger":1}',
            "shorekit/tests/fixtures/objects/2026-11-02-cairn.json": b'{"shore": 1}',
            "shorekit/manifest.py": b"", "tests/fixtures/open_meteo_sample.json": b'{"hourly": {}}',
            "docs/hero-17h.jpg": b"", "shorekit/SCHEMA.md": b'"shore": 1',
        }
        bad = dict(guard.offending(sorted(files), lambda p: files[p]))
        self.assertEqual(sorted(bad), ["data/shore/objects/x.json", "kit.lock", "ledger.json", "notes/thing.json",
                                       "out/objects/2026-11-02-a.json", "reference/r1/keepout.png",
                                       "returned/2026-11-02-a.json", "shore/ledger.json", "x/r2/noon.png", "x/y.json"])


if __name__ == "__main__":
    unittest.main()
