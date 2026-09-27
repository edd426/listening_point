#!/usr/bin/env python3
"""Set a desktop picture on every Space and display (macOS 14+ wallpaper store).

Finder's `set desktop picture` only changes the current Space. This sets the current
Space through Finder (so macOS writes a well-formed entry), copies that entry into
every Desktop slot of the wallpaper store, and restarts WallpaperAgent. The store is
backed up first.

usage: set_wallpaper.py IMAGE [--backup-dir DIR]
"""
import argparse
import copy
import datetime
import os
import plistlib
import shutil
import subprocess
import sys
import time
import urllib.parse
from collections import Counter

STORE = os.path.expanduser("~/Library/Application Support/com.apple.wallpaper/Store/Index.plist")


def desktop_slots(node):
    """Yield every dict that holds a Desktop 'Content' entry."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "Desktop" and isinstance(v, dict) and "Content" in v:
                yield v
            else:
                yield from desktop_slots(v)
    elif isinstance(node, list):
        for v in node:
            yield from desktop_slots(v)


def picture(content):
    try:
        cfg = plistlib.loads(content["Choices"][0]["Configuration"])
        url = cfg.get("url", {}).get("relative")
        return urllib.parse.unquote(url) if url else cfg.get("type", "?")
    except Exception:
        return "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--backup-dir", default=os.path.expanduser("~/Pictures/Wallpapers/.store-backups"))
    a = ap.parse_args()
    img = os.path.abspath(a.image)
    if not os.path.exists(img):
        sys.exit(f"no such file: {img}")

    os.makedirs(a.backup_dir, exist_ok=True)
    backup = os.path.join(a.backup_dir, "Index.plist." + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(STORE, backup)
    print("backed up wallpaper store to", backup)

    subprocess.run(["osascript", "-e", f'tell application "Finder" to set desktop picture to POSIX file "{img}"'], check=True)
    want = "file://" + img
    good = None
    for _ in range(20):
        time.sleep(0.5)
        with open(STORE, "rb") as f:
            store = plistlib.load(f)
        good = next((s["Content"] for s in desktop_slots(store) if picture(s["Content"]) == want), None)
        if good:
            break
    if good is None:
        sys.exit("Finder did not record the picture in the wallpaper store; nothing else changed")

    slots = list(desktop_slots(store))
    for s in slots:
        s["Content"] = copy.deepcopy(good)
    with open(STORE, "wb") as f:
        plistlib.dump(store, f, fmt=plistlib.FMT_BINARY)
    subprocess.run(["killall", "WallpaperAgent"], check=False)
    time.sleep(2)
    with open(STORE, "rb") as f:
        after = Counter(picture(s["Content"]) for s in desktop_slots(plistlib.load(f)))
    print(f"set {len(slots)} desktop slots; store now holds:")
    for pic, n in after.items():
        print(f"  {n:3d}  {pic}")


if __name__ == "__main__":
    main()
