#!/bin/bash
# Screenshot what the desktop wallpaper is actually showing, even behind full-screen apps.
# Needs Screen Recording permission for the terminal.   usage: tools/capture_wallpaper.sh [out.png]
set -euo pipefail
out=${1:-wallpaper.png}
id=$(swift "$(dirname "$0")/wallpaper_windows.swift" | awk '$2 == "onscreen" && $3 == "WindowManager" {print $1; exit}')
if [ -z "$id" ]; then
  id=$(swift "$(dirname "$0")/wallpaper_windows.swift" | awk '$2 == "onscreen" {print $1; exit}')
fi
[ -n "$id" ] || { echo "no on-screen wallpaper window found" >&2; exit 1; }
screencapture -x -o -l "$id" "$out"
echo "$out"
