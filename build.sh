#!/bin/bash
# Render all 24 hours, pack them into a time-of-day dynamic wallpaper, and optionally install it.
#   ./build.sh                  full render (3840x2400, ~10 min) into out/
#   SCALE=0.25 ./build.sh       quick low-res pass; look at out/hours/sheet.jpg
#   ./build.sh --install        also copy to ~/Pictures/Wallpapers/The Listening Point and set it on every Space
set -euo pipefail
cd "$(dirname "$0")"
SCALE=${SCALE:-1.0}
JOBS=${JOBS:-3}
NAME="The Listening Point"

if [ ! -x venv/bin/python ]; then
  python3 -m venv venv
  ./venv/bin/pip install -q -r requirements.txt
fi
mkdir -p out/hours
./venv/bin/python renderers/procedural/listening_point.py out/hours --scale "$SCALE" --jobs "$JOBS" --sheet
swiftc -O tools/make_h24.swift -o out/make_h24
out/make_h24 "out/$NAME.heic" out/hours/[0-2][0-9].jpg

if [ "${1:-}" = "--install" ]; then
  if [ "$SCALE" != "1.0" ]; then
    echo "refusing to install a SCALE=$SCALE build; re-run at full scale" >&2
    exit 1
  fi
  dest="$HOME/Pictures/Wallpapers/$NAME"
  mkdir -p "$dest/hours"
  cp out/hours/[0-2][0-9].jpg "$dest/hours/"
  cp "out/$NAME.heic" "$dest/"
  ./venv/bin/python tools/set_wallpaper.py "$dest/$NAME.heic" --backup-dir "$dest/backups"
fi
