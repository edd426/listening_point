# Working on this repo

- Read STATUS.md first: it holds the current state, decisions, macOS gotchas, and the idea list.
  Update it when any of those change.
- Iterate at low resolution: `SCALE=0.25 ./build.sh`, or render a few hours with
  `./venv/bin/python renderers/procedural/listening_point.py out/prev --scale 0.3 --hours 0,6,12,18 --jobs 4 --sheet`.
  Check full-res crops before a final render.
- Never commit rendered frames or HEICs; attach them to a GitHub release.
- After installing, confirm what is on screen with `tools/capture_wallpaper.sh`, not by reading the wallpaper store.
- Every renderer writes `HH.jpg` (00–23) for local-clock hours, so `tools/` stays shared.
