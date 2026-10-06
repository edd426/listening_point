#!/bin/bash
# Remove the live wallpaper helper and the nightly render job. Rendered frames stay in
# ~/Pictures/Wallpapers/The Listening Point/days (delete them by hand if you like).
set -uo pipefail
for job in com.edd426.listening-point.live com.edd426.listening-point.render; do
  launchctl bootout "gui/$(id -u)/$job" 2>/dev/null
  rm -f "$HOME/Library/LaunchAgents/$job.plist"
done
echo "removed the helper and the render job; the system wallpaper is unchanged"
