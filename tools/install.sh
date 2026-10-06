#!/bin/bash
# Install the per-minute live wallpaper on this Mac (re-run to update it after changing the renderer):
#  - a private copy of the renderer and its Python environment in ~/Library/Application Support/The Listening Point,
#    because launchd jobs may not read ~/Documents, where this repo lives
#  - the live wallpaper helper: a window at desktop level showing the frame for the current minute
#  - two LaunchAgents: one keeps the helper running, one renders frames whenever the Mac is awake
#    (every 15 minutes, and at once on wake: the helper starts it when today's frames are missing)
#  - an hourly HEIC of today as the system wallpaper (lock screen, Mission Control, Space switches, fallback);
#    rebuilt daily once the helper has Full Disk Access to clear the wallpaper cache, else monthly
# usage: tools/install.sh            undo with tools/uninstall.sh
set -euo pipefail
cd "$(dirname "$0")/.."
APP="$HOME/Library/Application Support/The Listening Point"
ROOT="$HOME/Pictures/Wallpapers/The Listening Point"
AGENTS="$HOME/Library/LaunchAgents"
LIVE=com.edd426.listening-point.live
RENDER=com.edd426.listening-point.render
mkdir -p "$APP/src" "$ROOT/days" "$AGENTS" "$HOME/Library/Logs"

rsync -a --delete --exclude __pycache__ renderers tools requirements.txt "$APP/src/"
if [ ! -x "$APP/venv/bin/python" ]; then
  /usr/bin/python3 -m venv "$APP/venv"
  "$APP/venv/bin/pip" install -q --upgrade pip
  "$APP/venv/bin/pip" install -q -r requirements.txt
fi
swiftc -O tools/live_wallpaper.swift -o "$APP/live_wallpaper"
swiftc -O tools/make_h24.swift -o "$APP/make_h24"

cat > "$AGENTS/$LIVE.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LIVE</string>
  <key>ProgramArguments</key><array><string>$APP/live_wallpaper</string><string>$ROOT</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/listening-point-live.log</string>
</dict></plist>
PLIST

cat > "$AGENTS/$RENDER.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$RENDER</string>
  <key>ProgramArguments</key><array>
    <string>$APP/venv/bin/python</string><string>$APP/src/tools/nightly.py</string><string>--root</string><string>$ROOT</string>
  </array>
  <key>StartInterval</key><integer>900</integer>
  <key>RunAtLoad</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>LowPriorityIO</key><true/>
  <key>Nice</key><integer>10</integer>
  <key>StandardOutPath</key><string>/dev/null</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/listening-point.log</string>
</dict></plist>
PLIST

launchctl bootout "gui/$(id -u)/$RENDER" 2>/dev/null || true

cat > "$ROOT/README.md" <<TXT
# The Listening Point

A frame for every minute of the real day: the sky over Budapest, the forecast weather, the season.

- days/YYYY-MM-DD/HHMM.jpg: the frames, rendered in the background whenever the Mac is awake
  (all of tomorrow when on power; the next few hours when on battery). Old days are deleted.
- The Listening Point.heic: today's on-the-hour frames, the system wallpaper (lock screen, Mission
  Control, Space switches). Rebuilt daily if the helper has Full Disk Access, else monthly.
- The live wallpaper helper shows the current minute's frame above the desktop picture.

Log: ~/Library/Logs/listening-point.log. Source: $(pwd) (github.com/edd426/listening_point).
Remove with tools/uninstall.sh in the source folder.
TXT

if [ "${1:-}" != "--keep-wallpaper" ]; then
  "$APP/venv/bin/python" "$APP/src/tools/nightly.py" --root "$ROOT" --hourly-only
  ./venv/bin/python tools/set_wallpaper.py "$ROOT/The Listening Point.heic" --backup-dir "$ROOT/backups"
  rm -f "$ROOT/The Listening Point.jpg"
fi
for job in $LIVE $RENDER; do
  launchctl bootout "gui/$(id -u)/$job" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$job.plist"
done
./venv/bin/python tools/clean_wallpaper_cache.py
echo "installed. Frames render in the background whenever the Mac is awake; log: ~/Library/Logs/listening-point.log"
echo "To let the lock-screen wallpaper follow each day's weather, give the helper Full Disk Access:"
echo "  System Settings > Privacy & Security > Full Disk Access > + > $APP/live_wallpaper"
echo "  (it only clears the wallpaper agent's old bitmaps of our own files; without it the hourly wallpaper is rebuilt monthly)"
