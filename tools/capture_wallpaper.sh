#!/bin/bash
# Screenshot what the desktop is actually showing behind the windows, even behind full-screen apps:
# the live wallpaper helper's window when it is running, otherwise the system wallpaper.
# Needs Screen Recording permission for the terminal.   usage: tools/capture_wallpaper.sh [out.png]
set -euo pipefail
out=${1:-wallpaper.png}
list=$(swift "$(dirname "$0")/wallpaper_windows.swift")
id=$(echo "$list" | awk '$2 == "onscreen" && $3 == "live_wallpaper" {print $1; exit}')
[ -n "$id" ] || id=$(echo "$list" | awk '$2 == "onscreen" && $3 == "WindowManager" {print $1; exit}')
[ -n "$id" ] || id=$(echo "$list" | awk '$2 == "onscreen" {print $1; exit}')
[ -n "$id" ] || { echo "no on-screen wallpaper window found" >&2; exit 1; }
screencapture -x -o -l "$id" "$out"
echo "$out"
