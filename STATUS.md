# Status

_Last updated 2026-09-27._

## Current state

- v1.0 is rendered and installed locally at
  `~/Pictures/Wallpapers/The Listening Point/The Listening Point.heic`, set on every Space.
  Verified by capturing the wallpaper window at 08:40: the 08:00 frame was showing.
- The renderer is one file, `renderers/procedural/listening_point.py` (about 1,600 lines).
  A full build takes about 10 minutes with 3 processes (about 1 GB RAM each).
- The prebuilt HEIC and the 24 JPEG frames are on the GitHub release `v1.0`.

## Decisions

- **Dynamic HEIC, not Auto-Rotate "every hour".** Auto-Rotate counts from the moment it's set,
  not the top of the hour, and drifts after sleep, so it can't keep the clock honest.
  The h24 HEIC switches on real local time.
- **Fixed date: September equinox at 47.5° N.** Sunrise and sunset fall at exactly 06:00 and
  18:00 and the day is symmetric, which makes the sun easy to read as a clock. The full moon
  (RA 0h) keeps a moon in the sky every night hour.
- **The view faces south** so the sun and moon cross the frame. Consequence: the tower's front
  is always on the shady side; fill light and rim light compensate.
- **Git holds code and small previews only.** Rendered frames and the HEIC (about 45 MB) go on
  releases.

## Lessons (macOS 27)

- h24 dynamic HEICs still work, and `ti[].t` is a fraction of the **local** day. Verified with a
  numbered test file: "07" showed at 07:54 CEST.
- `tell application "Finder" to set desktop picture` changes **only the current Space**. Every
  Space has its own entry in `~/Library/Application Support/com.apple.wallpaper/Store/Index.plist`.
  `tools/set_wallpaper.py` handles this.
- Reading the store, or `get picture of every desktop`, isn't proof of what's on screen. Capture
  the wallpaper window instead (`tools/capture_wallpaper.sh`). The terminal needs Screen Recording
  permission.

## Known weaknesses

- It looks computer-generated: flat shapes, noise textures, analytic lighting, no bounce light.
- The tree canopy reads a little blobby, and the leaves are simple diamonds.
- The night foreground is very dark; the grass shows little texture by moonlight.
- The stone wall is a flat band; the sheep are simple.

## Ideas for next time

- **Painterly pass:** a post-process over the existing frames (Kuwahara or brush strokes, paper texture).
- **Blender renderer:** rebuild the scene in 3D, scripted per hour, reusing the astronomy code.
- **Seasons:** vary the sun declination by month for spring, summer and winter sets, with snow
  or blossom. macOS "solar" dynamic wallpapers (`apple_desktop:solar`) could pick frames by the
  real sun position instead of the clock, but then the tower clock would drift from the frame.
- **Modules:** split the renderer (astro, sky, sea, terrain, props) the first time a second
  renderer needs to share code.
- **More life:** a ship on the horizon, a cat on the bench, rain or fog days, a real moon phase.
