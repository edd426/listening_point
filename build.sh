#!/bin/bash
# Render one day of The Listening Point, one frame per minute, and pack the on-the-hour frames into
# an hourly dynamic HEIC (for Macs without the live helper). Or install the live wallpaper.
#   ./build.sh                        today's 1,440 frames (2880x1800) into out/days/YYYY-MM-DD, about 25 min
#   DATE=2026-12-21 ./build.sh        another day (forecast weather reaches ~2 weeks ahead; past that it is made up)
#   SCALE=0.25 EVERY=60 ./build.sh    quick low-res preview, one frame an hour: see out/days/<date>/sheet.jpg
#   WEATHER=fair ./build.sh           fair weather instead of the forecast (also: synthetic, offline)
#   ./build.sh --install              live wallpaper + nightly renders + monthly still (tools/install.sh)
set -euo pipefail
cd "$(dirname "$0")"
SCALE=${SCALE:-0.75}
JOBS=${JOBS:-2}
EVERY=${EVERY:-1}
DATE=${DATE:-$(date +%F)}
WEATHER=${WEATHER:-auto}

if [ ! -x venv/bin/python ]; then
  python3 -m venv venv
  ./venv/bin/pip install -q -r requirements.txt
fi
if [ "${1:-}" = "--install" ]; then
  exec tools/install.sh
fi
out="out/days/$DATE"
mkdir -p "$out"
./venv/bin/python renderers/procedural/listening_point.py "$out" --date "$DATE" --scale "$SCALE" --jobs "$JOBS" \
  --every "$EVERY" --weather "$WEATHER" --sheet
hours=$(ls "$out"/[0-2][0-9]00.jpg 2>/dev/null | wc -l | tr -d ' ')
if [ "$hours" = "24" ]; then
  swiftc -O tools/make_h24.swift -o out/make_h24
  out/make_h24 "out/The Listening Point $DATE.heic" "$out"/[0-2][0-9]00.jpg
fi
