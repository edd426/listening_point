#!/usr/bin/env python3
"""Delete stale bitmaps from the macOS wallpaper agent's cache.

The agent caches every wallpaper frame it shows as an uncompressed bitmap named
sha256(path)-W-H-frame-<mtime>.bmp and never deletes any, so each new version of a wallpaper file
leaves the old version's bitmaps behind (about 20 MB per frame per screen size). Background jobs
aren't allowed into that folder, but Terminal is, so run this from Terminal (or give the live
wallpaper helper Full Disk Access and it does the same for our files every hour).

usage: clean_wallpaper_cache.py          stale bitmaps of The Listening Point's own files
       clean_wallpaper_cache.py --all    everything except the wallpapers set right now
       add --dry-run to only list what would go
"""
import argparse
import hashlib
import os
import plistlib
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from set_wallpaper import STORE, desktop_slots, picture  # noqa: E402

CACHE = os.path.expanduser("~/Library/Containers/com.apple.wallpaper.agent/Data/Library/Caches/"
                           "com.apple.wallpaper.caches/extension-com.apple.wallpaper.extension.image")
ROOT = os.path.expanduser("~/Pictures/Wallpapers/The Listening Point")
OURS = [os.path.join(ROOT, n) for n in ("The Listening Point.heic", "The Listening Point.jpg")]


def key(path):
    """(name prefix, suffix of the current version) for a wallpaper file."""
    h = hashlib.sha256(path.encode()).hexdigest()
    if not os.path.exists(path):
        return h, None
    return h, struct.pack(">d", os.stat(path).st_mtime - 978307200).hex()


def current_wallpapers():
    with open(STORE, "rb") as f:
        store = plistlib.load(f)
    out = set()
    for slot in desktop_slots(store):
        p = picture(slot["Content"])
        if p.startswith("file://"):
            out.add(p[len("file://"):])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    names = [n for n in os.listdir(CACHE) if n.endswith(".bmp")]
    keep = {key(p) for p in current_wallpapers() | set(OURS)}
    current = {h: suf for h, suf in keep}
    ours = {key(p)[0] for p in OURS}
    gone = 0
    for n in names:
        h, suf = n.split("-")[0], n[:-4].split("-")[-1]
        stale = (h in current and current[h] != suf) or (a.all and h not in current) or (h in ours and current.get(h) != suf)
        if not stale:
            continue
        size = os.path.getsize(os.path.join(CACHE, n))
        gone += size
        if a.dry_run:
            print("would delete", n[:12] + "...", n[-30:])
        else:
            os.remove(os.path.join(CACHE, n))
    print(f"{'would free' if a.dry_run else 'freed'} {gone / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
