# Status

_Last updated 2026-11-01._

## Current state

- **v2.0 (per-minute, real sky, weather, seasons) is installed and released** (tag `v2.0`; the
  GitHub release carries the hourly HEIC). The renderer lives in `renderers/procedural/` (about
  5,200 lines, split by subject).
- Installed pieces (`tools/install.sh`):
  - `~/Library/Application Support/The Listening Point/`: a copy of the renderer and tools, its own venv, and the
    `live_wallpaper` helper binary.
  - LaunchAgents `com.edd426.listening-point.live` (helper, KeepAlive) and
    `com.edd426.listening-point.render` (`tools/nightly.py`, every 15 minutes, nice 10, background).
  - Frames in `~/Pictures/Wallpapers/The Listening Point/days/YYYY-MM-DD/HHMM.jpg`;
    log in `~/Library/Logs/listening-point.log`; weather cache in `~/Library/Caches/listening-point`.
  - System wallpaper: `~/Pictures/Wallpapers/The Listening Point/The Listening Point.heic`, today's
    24 on-the-hour frames, rebuilt daily if the helper has Full Disk Access (`.cache-clean` says
    `ok`), else monthly. Full Disk Access was granted to the helper on 2026-10-06, so it's daily.
- Verified 2026-10-06 05:24 after a night on battery: the render job kept three hours ahead, the
  helper showed the right minute (16 MB, no CPU, no log errors), and the system wallpaper showed
  today's 05:00 frame. Disk: about 1 GB a day of frames (3 days kept), 135 MB in Application Support.
- Cost on this M1 (8 GB): a minute frame takes about 2 s of CPU and a 10-minute keyframe about 4 s;
  a full day is about 40 minutes with 2 workers. Each worker peaks around 1.2 GB, so
  `nightly.py` drops to 1 worker when `kern.memorystatus_level` is under 45%. Three workers pushed
  this Mac into heavy swap; don't go back to 3.

## The shore (branch work, not installed)

**Branch `shore/look-b` is a look experiment, not for merging as-is.** Variant A's objects were
specks at desktop size (10-24 px tall in the 2880x1800 frame, 5-12 points), its label plaque read as
a UI chip, nothing glowed and objects were lit as one dark face. Look B, for comparing against A:
`scale` 1-4 with a size floor beside the height cap, both scaled by perspective (`max_h` = 44 x persp,
`min_h` = 18 x persp: an object's width and height must average at least 25 px on the near shingle);
labels of at most 8 characters cut 1 px per font pixel into a small board that leans back and is lit
like the beach; one optional `glow` key (at most 64 px) that emits from dusk with a halo, a pool and,
on the pier, a reflection; every pixel lit by the face it shows (top, front, east, west, read off the
bitmap); the strip above the pier deck's far edge opened, so things on the deck can rise in front of
it. See the look B note at the top of `shorekit/SCHEMA.md`. The renderer and kit agree at the
reference minutes except where only the renderer draws: lamp pools and halos, and cast shadows of the
scenery on objects' sunlit faces.

Small objects that makers far away leave on the beach and the pier, judged by `shorekit/` (see
`shorekit/README.md` and `SCHEMA.md`), plus a lamp the owner can light. Phases 2 and 3 are built:

- **Reference frames.** `tools/shore_reference.py OUT_DIR` renders four fixed minutes of 2027-03-21
  (noon 11:50, golden 17:20, night 22:30 under a full moon, fog 10:00) with `--reference` (no
  creatures, rare events or grain; tide at high water; fixed `clear`/`fog` weather) and writes the
  kit's reference set: the crops, `keepout.png`, `surfaces.json`, `palette.json` (the renderer's own
  albedos, D = 40), `conditions.json`. Two runs give the same bytes. Never write one inside the repo.
- **Drawing.** `renderers/procedural/shore.py`: `--shore DIR` (a cache in the kit's layout:
  `ledger.json`, `objects/`, `reference/<id>/`) draws the kit's own pixels in `front()` after the
  tower: lit by `lit()` with one camera-facing normal (the bench's), a contact shadow that takes 45% of
  the ground's light, veiled by the fog, shown from `lands` until a storm or a veto. Creatures and rare
  events draw after them; the heron and anything washed up are hidden by objects standing nearer.
  Without `--shore`, or with an empty ledger, frames are byte-identical to before.
- **The lamp.** `--lamp FILE` (the lamp-state file, `docs/LISTENER.md` on the controls branch) lights
  two panes in the moored boat's deckhouse from dusk (with the other lamps) on a lit day, from the
  moment it was lit, with a glow and a reflection. The boat is always moored by then (every sailing
  trip ends half an hour before sunset).
- **Tests.** `tests/test_shore_reference.py` and `tests/test_shore_render.py` (a few minutes each;
  `SHORE_REFERENCE=DIR` reuses a built set). At the reference minutes the frame matches the kit's
  preview inside each footprint to mean |d| < 1 and p99 <= 8 (fog), and changes nothing outside it.
- **Still to do (phase 5).** `tools/install.sh` must copy `shorekit/` beside `renderers/` (the renderer
  imports it from there), and `tools/nightly.py` must pass `--shore` and `--lamp`.

## Decisions

- **Per-minute frames are shown by a helper window, not the system wallpaper** (see Lessons:
  the wallpaper agent's cache). The helper draws at desktop level + 1 on every Space, cross-fades on
  the minute, falls back to the same minute of the newest earlier day, and kicks the render job
  (`launchctl kickstart`) when today's frame is missing.
- **The system wallpaper is an hourly HEIC of the same day.** macOS draws it (not the helper) for
  a moment during every Space switch, and on the lock screen; a golden-hour still made Space switches
  flash daytime at night, and Evan prefers the hourly lock screen. Each rebuild leaves ~0.5 GB of
  stale bitmaps in the agent's cache, which only an FDA-granted process can delete; so the helper
  tries hourly and the job rebuilds daily only when that works, else monthly.
- **Laptop that sleeps a lot (Evan's note):** the job renders whenever the Mac is awake, not just at
  night. On power: the rest of today from the current minute, then all of tomorrow; after 18:00
  tomorrow is re-rendered if the evening forecast changed meaningfully. On battery with at least 50%:
  when less than an hour is ready, the next three hours with one worker (small batches cost
  ~9 s a frame in keyframes and start-up, against ~2 s in bulk).
- **The installed copy runs from Application Support** because launchd jobs may be denied
  `~/Documents`. Re-run `tools/install.sh` after changing the renderer.
- **The real sky for Budapest, in local clock time** (DST included), instead of v1's fixed
  equinox. The tower clock now tells the time to the minute, so the sun no longer has to.
- **Near scenery is keyframed every 10 minutes** (grass, tree, pier, bench, lamp), in sunlit and
  shaded versions when clouds are about, and cross-faded; the sky, sea, creatures, tower and weather
  are rendered every minute. The tower is per-minute because its clock, telescope and dome change.
- **The view faces south**, so the sun and moon cross the frame; bounce light keeps shaded faces
  readable.
- **The pier is real 3D** (`PIER3` in `core.py`), projected with a local pinhole camera matched to
  the panorama at its middle, so its edges stay straight. Fitted to its v1 screen position.
- **Spoilers live in `docs/SPOILERS.md`**; don't describe the hidden events in chat or the README.
- **Git holds code and small previews only.** Frames, HEICs and weather caches never go in git.

## Modules

`renderers/procedural/` holds mixins on one `Frame`: `sky`, `sea`, `land`, `tree`, `tower`, `props`,
`life`, `distant`, `weatherfx`, `mystery`, `shore`. `day.py` builds one date's per-minute astronomy, weather,
season (`season.py`), schedule (`events.py`) and mysteries. `astro.py` and `weather.py` are
self-contained. Tests (offline): `./venv/bin/python tests/test_astro.py` and `tests/test_weather.py`.

- `astro.py` matches Skyfield/DE421 to 0.01 deg or better (sun, topocentric moon, VSOP87-truncated
  planets, precessed stars) and sun events to 1 s; it assumes UT1 = UTC and a fixed delta-T. The
  fixture is regenerated by `tests/make_astro_fixture.py` in a separate venv with Skyfield.
- `weather.py` caches raw Open-Meteo responses (default `out/weather/`, or `--cache`). Open-Meteo's
  ISO local times use one fixed offset for the whole response, even across a DST change, so it asks
  for unix times. Its drizzle codes (51-55) just mean light rain. Forecasts only reach 15 days ahead.

## Lessons (macOS 27)

- A 1,440-frame h24 HEIC does switch every minute (frames showed 19:33, 19:34, 19:35 on time,
  within ~6 s of the boundary). But WallpaperAgent writes every frame it shows to an
  uncompressed BMP cache (~20.7 MB at 2880x1800, in three sizes) in
  `~/Library/Containers/com.apple.wallpaper.agent/Data/Library/Caches/com.apple.wallpaper.caches/extension-com.apple.wallpaper.extension.image/`,
  keyed by path hash, size, frame index and file mtime, and doesn't prune it (8-day-old entries
  remain). A per-minute system wallpaper would write ~30 GB a day.
- Replacing a wallpaper file in place isn't picked up: the agent keeps decoding the old file until
  `killall WallpaperAgent`, and meanwhile caches the old pixels under the new mtime key.
- This Mac's display runs scaled ("looks like" 1440x900), so the wallpaper is drawn at
  2880x1800, not the panel's 2560x1600 (that's what the cache files and window captures show).
- A borderless window at `CGWindowLevelForKey(.desktopWindow) + 1` with
  `[.canJoinAllSpaces, .stationary, .ignoresCycle]` sits above the wallpaper and below the icons,
  on every Space; an `.accessory` app can show it. Measured: 42 MB, no visible CPU.
- launchd `StartInterval` jobs skip the intervals missed while asleep; hence the helper's kickstart.
- The wallpaper agent names its cached bitmaps `sha256(absolute path)-W-H-frame-<mtime>.bmp`, the
  mtime as a big-endian double of seconds since 2001 (`struct.pack('>d', st_mtime - 978307200)`).
- A launchd job (Python or Swift) gets "Operation not permitted" listing the agent's container;
  Terminal can. Full Disk Access on the job's own binary is the only way in for background code.
- During a Space switch macOS shows the system wallpaper, not desktop-level windows such as the
  helper's, so the two should show the same hour.
- h24 dynamic HEICs still work, and `ti[].t` is a fraction of the **local** day.
- `tell application "Finder" to set desktop picture` changes **only the current Space**. Every
  Space has its own entry in `~/Library/Application Support/com.apple.wallpaper/Store/Index.plist`.
  `tools/set_wallpaper.py` handles this.
- Reading the store, or `get picture of every desktop`, isn't proof of what's on screen. Capture
  the window instead (`tools/capture_wallpaper.sh`, which prefers the helper's window). The terminal
  needs Screen Recording permission.

## Known weaknesses

- Still recognisably computer-made: flat-shaded polygons, noise textures.
- Creatures are small and simple at this scale (sheep, cat, heron, owl).
- Mid-level clouds near the horizon streak toward the vanishing point (the plane projection).
- Weather can jump where separately rendered spans of a day meet (battery renders, a forecast
  refreshed mid-day).
- The sea render and the front layer still peak at ~250 MB per frame; strip them like the hill if
  memory gets tight.

## Ideas for next time

- **Painterly pass:** a post-process over the frames (Kuwahara or brush strokes, paper texture).
- **Blender renderer:** rebuild the scene in 3D, reusing `astro.py`, `weather.py` and `day.py`.
- **Location from the system:** follow the Mac when it travels (sky and weather) instead of Budapest.
