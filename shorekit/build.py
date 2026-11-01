"""Build dist/shorekit.pyz reproducibly: `python3 -m shorekit.build [OUT]`.

The archive is written by hand, not by zipfile or zipapp, so its bytes depend only on the
package's source bytes: entries are sorted, stored (not deflated, so no zlib version can change
them), dated 1980-01-01 00:00, mode 0644, with no extra fields. Two builds of the same commit
are byte-identical on any platform and any Python.
"""
import hashlib
import os
import struct
import sys
import zlib

SHEBANG = b"#!/usr/bin/env python3\n"
MAIN = b"import sys\nfrom shorekit.cli import main\nsys.exit(main())\n"
DOS_DATE = (0 << 9) | (1 << 5) | 1      # 1980-01-01
DOS_TIME = 0
MADE_BY = (3 << 8) | 20                  # unix, zip 2.0
NEEDED = 20
FILE_MODE = 0o100644 << 16


def package_dir():
    return os.path.dirname(os.path.abspath(__file__))


def entries(pkg=None):
    pkg = pkg or package_dir()
    out = [("__main__.py", MAIN)]
    for name in sorted(os.listdir(pkg)):
        if name.endswith(".py") and name != "build.py":
            with open(os.path.join(pkg, name), "rb") as f:
                out.append(("shorekit/" + name, f.read()))
    return out


def zip_stored(items, prefix=b""):
    out = bytearray(prefix)
    central = bytearray()
    for name, data in items:
        nb = name.encode("ascii")
        crc = zlib.crc32(data) & 0xFFFFFFFF
        offset = len(out)
        out += struct.pack("<IHHHHHIIIHH", 0x04034B50, NEEDED, 0, 0, DOS_TIME, DOS_DATE, crc, len(data), len(data),
                           len(nb), 0) + nb + data
        central += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, MADE_BY, NEEDED, 0, 0, DOS_TIME, DOS_DATE, crc,
                               len(data), len(data), len(nb), 0, 0, 0, 0, FILE_MODE, offset) + nb
    start = len(out)
    out += central
    out += struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(items), len(items), len(central), start, 0)
    return bytes(out)


def build(out_path=None, pkg=None):
    """Write the zipapp and return (path, sha256)."""
    pkg = pkg or package_dir()
    if out_path is None:
        out_path = os.path.join(os.path.dirname(pkg), "dist", "shorekit.pyz")
    data = zip_stored(entries(pkg), SHEBANG)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.chmod(tmp, 0o755)
    os.replace(tmp, out_path)
    return out_path, hashlib.sha256(data).hexdigest()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    path, sha = build(argv[0] if argv else None)
    print("BUILT %s sha256=%s" % (path, sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())
