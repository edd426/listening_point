#!/usr/bin/env python3
"""Fail if real shore data is committed to this public repository.

Shore data lives only on the shore branches and in the private shore repo. Here we keep code and
synthetic test data (shorekit/tests/fixtures/). Usable as a CI step or a pre-commit hook:

    python3 .github/scripts/no_shore_data.py            # checks `git ls-files`
"""
import re
import subprocess
import sys

FIXTURES = "shorekit/tests/fixtures/"
NAMES = {"ledger.json", "kit.lock", "lamp.json", "queue.json", "result.json"}
REF_FILES = {"surfaces.json", "palette.json", "conditions.json", "keepout.png", "context.jpg"}
SHORE_KEY = re.compile(rb'"shore(_[a-z_]+)?"\s*:')
REF_DIR = re.compile(r"r[1-9][0-9]{0,3}")


def offending(paths, read):
    """(path, reason) for every path that looks like shore data. `read(path)` returns its bytes."""
    bad = []
    for p in paths:
        parts = p.split("/")
        name = parts[-1]
        parent = parts[-2] if len(parts) > 1 else ""
        if "shore" in parts[:-1]:
            bad.append((p, "inside a shore/ directory"))
        elif p.startswith(FIXTURES):
            continue
        elif name in NAMES:
            bad.append((p, "a shore record file"))
        elif parent in ("objects", "returned") and name.endswith(".json"):
            bad.append((p, "an object or returned object"))
        elif REF_DIR.fullmatch(parent) and (name in REF_FILES or name.endswith(".png")):
            bad.append((p, "part of a reference set"))
        elif name.endswith(".json") and SHORE_KEY.search(read(p)):
            bad.append((p, "JSON with shore keys"))
    return bad


def main():
    out = subprocess.run(["git", "ls-files", "-z"], check=True, stdout=subprocess.PIPE).stdout
    paths = [p for p in out.decode("utf-8").split("\0") if p]

    def read(p):
        try:
            with open(p, "rb") as f:
                return f.read(1 << 20)
        except OSError:
            return b""
    bad = offending(paths, read)
    for p, why in bad:
        print("shore data committed: %s (%s)" % (p, why))
    print("checked %d files, %d look like shore data" % (len(paths), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
