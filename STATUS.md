# Status

_Last updated 2026-11-10 (the shore's cast shadows, merged and installed: see "Cast shadows" under The shore).
v3 progress and handoff: `docs/V3-PLAN.md`._

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
- **Owner controls (branch `shore/controls`, 2026-10-31; not installed yet).** A menu-bar item on
  the helper (Light the lamp, Leave a note…) backed by `tools/listener.py`, with an outbox that
  `nightly.py` drains first on every run. Spec and setup: `docs/LISTENER.md`. Before it does
  anything the owner must make the fine-grained key, store it in the Keychain and write the
  untracked `listener.json` (steps in that doc), then run `tools/install.sh`. The renderer reads
  `listener/lamp.json` (`--lamp`, below).
- Verified 2026-10-06 05:24 after a night on battery: the render job kept three hours ahead, the
  helper showed the right minute (16 MB, no CPU, no log errors), and the system wallpaper showed
  today's 05:00 frame. Disk: about 1 GB a day of frames (3 days kept), 135 MB in Application Support.
- Cost on this M1 (8 GB): a minute frame takes about 2 s of CPU and a 10-minute keyframe about 4 s;
  a full day is about 40 minutes with 2 workers. Each worker peaks around 1.2 GB, so
  `nightly.py` drops to 1 worker when `kern.memorystatus_level` is under 45%. Three workers pushed
  this Mac into heavy swap; don't go back to 3.

## The shore (branch work, not installed)

**The look is variant C (Evan, 2026-11-01), kit 1.2.0.**
- Variant A's objects were specks at desktop size, and its label plaque read as a UI chip.
- Variant B was "slightly better" but still hard to see, so C made objects more noticeable.

What C does:
- **Size:** `scale` 1-4 with a size floor beside the height cap, both scaled by perspective. `max_h`
  is 96 x persp (about 130 px, or 65 points, on the near shingle). `min_h` is 36 x persp: an
  object's width and height must average at least about 49 px there.
- **Paint:** six boat paints in the palette.
- **Rule 7 (`E_FAINT`):** an object's mean colour must stand 48 apart from the ground around it at
  noon and at golden hour.
- **Labels:** at most 8 characters, cut into a small driftwood board.
- **Glow:** one optional `glow` key (at most 64 px) that emits from dusk.
- **Lighting:** every pixel is lit by the face it shows.

See `shorekit/SCHEMA.md` section 10.

Small objects that makers far away leave on the beach and the pier, judged by `shorekit/` (see
`shorekit/README.md` and `SCHEMA.md`), plus a lamp the owner can light. Built on branches, wired
together on `shore/sync` (2026-11-01), not installed:

- **Reference frames.** `tools/shore_reference.py OUT_DIR` renders four fixed minutes of 2027-03-21
  (noon 11:50, golden 17:20, night 22:30 under a full moon, fog 10:00) with `--reference` (no
  creatures, rare events or grain; tide at high water; fixed `clear`/`fog` weather) and writes the
  kit's reference set: the crops, `keepout.png`, `surfaces.json`, `palette.json` (the renderer's own
  albedos, D = 40), `conditions.json`. Two runs give the same bytes. Never write one inside the repo.
- **Drawing.** `renderers/procedural/shore.py`: `--shore DIR` (a cache in the kit's layout:
  `ledger.json`, `objects/`, `reference/<id>/`) draws the kit's own pixels in `front()` after the
  tower: lit by `lit()` with one camera-facing normal (the bench's), a contact shadow that takes 45% of
  the ground's light, veiled by the fog, shown from `lands` until the sea takes it. Creatures and rare
  events draw after them; the heron and anything washed up are hidden by objects standing nearer.
  Without `--shore`, or with an empty ledger, frames are byte-identical to before.
- **The lamp.** `--lamp FILE` (the lamp-state file, `docs/LISTENER.md` on the controls branch) lights
  two panes in the moored boat's deckhouse from dusk (with the other lamps) on a lit day, from the
  moment it was lit, with a glow and a reflection. The boat is always moored by then (every sailing
  trip ends half an hour before sunset).
- **Tests.** `tests/test_shore_reference.py` and `tests/test_shore_render.py` (a few minutes each;
  `SHORE_REFERENCE=DIR` reuses a built set). At the reference minutes the frame matches the kit's
  preview inside each footprint to mean |d| < 1 and p99 <= 8 (fog), and changes nothing outside it.
- **The sea (kit 1.1.0).** A storm comes only at 48 live objects and takes the oldest, with whatever
  rests on them, until 40 remain; the owner's veto takes an object and its pile. In the ledger both are
  one `sea` event that never says why; the carrier keeps the reasons privately and can hand them to
  `replay --reasons`, which then holds each storm and veto to its exact rule.
- **Sync (`tools/shore_sync.py`, `docs/LISTENER.md` "The shore on this Mac").** `nightly.py` drains the
  outbox, takes the render lock, builds this Mac's own reference set once (`shore/reference/r3`, `REFERENCE`), syncs at
  most hourly (ETag, so mostly a 304), deletes the frames the shore or the lamp has changed (from an
  object's `lands`, or the moment the sea took one; for the lamp, the dark minutes from the moment it was
  lit) and renders with `--shore` and `--lamp`. Sync refuses a ledger that drops or changes a known event,
  an object that does not hash to its sha256, or anything the kit will not replay, and keeps the last good
  one, offline too. The helper kicks the job on wake when the last sync try was over an hour ago. Nothing
  shore-related runs until the controls' key is in the Keychain. `install.sh` copies `shorekit/`.
- **Tests.** `/usr/bin/python3 -m unittest tests.test_shore_sync` (mock API on 127.0.0.1; also the
  re-render records); `tests/test_shore_render.py` also checks what `nightly.py` renders again.

### Cast shadows (kit 1.3.0, reference r3; merged, installed and published 2026-11-10)

Every object standing on the shingle or the pier throws a shadow that follows the sun, and a bright
moon. Until now the kit's only shadow was a footing, the same in all four lights; with this an
upright thing on the shore is a sundial.

- **The rule** is the kit's and is whole numbers (`shorekit/SCHEMA.md` 4.6, `geometry.cast_pixels`): a
  light is `dx`, `dy` (x256 px of shadow per px of height, right and down), each solid pixel shades the
  ground its own height sweeps over, and the shadow is kept where a contact shadow could fall. It is
  **drawn and never judged**: no rule, footprint, plan, `PLAN sha256`, PASS line or ledger entry
  knows of it. `compose.cast_shown` is the one set of pixels both the preview and the Mac darken.
- **The light** is the scene's own projection for the tower, tree and bench (`land.shadow_masks`),
  rounded to the kit's integers (`shore.cast_vector`), so the shadow's pixels on the Mac are the kit's
  by construction. How dark (`shore.shore_cast`): 0.34 of the ground's light under a full sun, as the
  animals' shadows (`CAST`), 0.30 under a full moon (`CAST_MOON`); none in weak direct light (cloud,
  fog, the sun's first degrees, any moon but a bright one: `CAST_FROM`, `CAST_MOON_FROM`); never
  more than the direct light's share of the light on the beach (a low sun); and less where the
  tower's or the tree's own shadow already lies.
- **Reference r3** (`tools/shore_sync.py` `REFERENCE`): the builder writes `conditions.json` as
  `shore_conditions` 2, each condition with its `cast` (`dx`, `dy`, `alpha`) from its own frame. r3's
  four crops, `keepout.png`, `surfaces.json` and `palette.json` are r2's (the crops byte for byte);
  only `conditions.json` differs. The kit still loads a set written as 1 and then draws no cast
  shadow, and so does the renderer: the shadows arrive with the reference set that carries them.
- **The renderer picks the newest reference set** in a cache without `kit.lock`
  (`shore.reference_dir`), so r3 may be built beside r2. Before, two sets in the cache meant no shore
  was drawn.
- **Tests.** `python3 -m unittest discover -s shorekit/tests` (87; `test_cast.py` holds the rule to a
  second implementation written from the schema, to the schema's worked example, and to its
  exclusions); `tests/test_shore_cast.py` (in `unittest discover -s tests`): the Mac's layer covers
  exactly the kit's pixels, the shadow turns with the sun, the strengths; `tests/test_shore_render.py`
  (a script, a few minutes): at the four reference minutes the frame matches the kit's preview on the
  cast shadow too, and nothing outside changes. That file's fixtures dated from before look C and it
  failed 5 of 7 since kit 1.2.0; they are bigger and painted now, its baseline is `main`, and it passes.
- **Done 2026-11-10** (Evan's go): merged as `5654f69` (CI green, same bytes everywhere, pyz sha256
  `bf63d3fd…032c`); `tools/install.sh` run; the Mac built r3 (digest `f237badc…093c`, the same as a
  scratch build); r3 published to the shore repository and pinned in the carrier with kit 1.3.0; an
  owner run carried both to the worlds; `sync.json` names r3 after clearing `etag` and
  `shore_sync.py --force`. Today's and tomorrow's old-look frames were moved to
  `~/Pictures/Wallpapers/The Listening Point/pre-cast/` so they render again; delete that folder
  once the new look has been seen. The install's last step failed once (`Bootstrap failed: 5`, both
  launchd jobs left unloaded); bootstrapping again a few seconds later worked, and `install.sh` now
  retries.
- **Installing it** (the steps, as they were done):
  1. Merge, then `tools/install.sh`. The render job builds `shore/reference/r3/` on its next run
     (about a minute) and sync replays the ledger against it; what is on the shore now replays with
     no misfit (checked against a copy with the kit's `replay`).
  2. Publish that r3 and the 1.3.0 `shorekit.pyz` with its `kit.lock` to the shore repository, and set
     the carrier's reference id and digest, as for r2 (`docs/v3/phase1.md`, Install). From then a
     manifest must name `r3` (`E_REFERENCE`); nothing already on the shore changes.
  3. Frames already rendered keep the look they were rendered with: the day's `shore.json` record
     does not know about renderer changes. Delete a day's frames to have them rendered again.
- **Known issues.**
  - A flat picture has no depth. When the sun or the moon stands due east or west, the shadow of the
    whole silhouette falls into a line one to five pixels thick along the ground (08:50 on 21 June, for
    one; the equinox's golden hour, one of the four reference lights, is nearly this). A thin post
    should look like that; a stack of logs should not. Giving each row a depth on the ground
    would mend it and is a change to the rule.
  - The shadow's edge is hard, to the pixel, where the scenery's own shadows are soft.
  - On the shingle's busy texture a 0.34 shadow is quiet; on the grass it reads well.
  - A thing built onto another casts none, and no cast shadow falls on another object.

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

`renderers/procedural/` holds mixins on one `Frame`: `sky`, `sea`, `land`, `hillside`, `tree`, `tower`, `props`,
`life`, `fauna`, `distant`, `weatherfx`, `mystery`, `shore`, `air`, `water`, `sealife`, `marks`. `water` (v3 phase 4 part 1,
`docs/v3/phase4-water.md`) draws the light on the sea and the marks in the bay. `sealife` (v3 phase 4 part 2,
`docs/v3/phase4-sea-life.md`) draws the bay's boats and animals (the creel boat, extra yachts, the island ferry,
seals, a cormorant, gannets, dolphins) from the day's plan in `seaplan.py` (`day.sea`; empty in reference mode);
`tools/sea_schedule.py` reports how often each shows. `marks` (v3 phase 5 part 1, `docs/v3/phase5-land.md`) draws
what the story leaves on the land (a wall fallen and rebuilt, the spade, a storm's branch and its logs, driftwood,
snow drifts) from `story.py` (`day.story`, from the date and the weather of the days before, real weather from the
cache only; empty in reference mode); `tools/story_calendar.py` prints what shows on each date. `story.py` also tells the
animal lives (v3 phase 5 part 2, `docs/v3/phase5-lives.md`): the lambs from their births to the sale and a kept ewe lamb
(drawn by `fauna`), the cat's kittens in some years (`life`), and the pale seal's autumns away (`seaplan`, `sealife`);
`tools/story_calendar.py --lives` prints them. And it tells the echoes of the shore (v3 phase 5 part 3,
`docs/v3/phase5-echoes.md`), from the shore cache's history (`shore.History`, on `day.shore`; nothing without a shore or
with an empty ledger, and nothing in reference mode): a pennant at the masthead in the colour of the newest object still
on the shore, the boat out on the bay the day after the sea takes things, and washing on some quiet days (drawn by
`props`). Each reads only the ledger events at or before its moment, so `nightly.py`'s shore re-render rule covers it;
`Day` loads the shore and builds the story before the bay's plan. `tools/story_calendar.py --echoes --shore DIR` prints
them. `fauna` (v3 phase 3 part 2,
`docs/v3/phase3-animals.md`) draws the sheep, fox, hares and crows, and hides any animal standing behind the
walls, the gate, the shed, the hives, the rocks or the gorse (masks recorded while the hill is drawn). `day.py` builds one date's per-minute astronomy, weather,
season (`season.py`), schedule (`events.py`) and mysteries. `astro.py` and `weather.py` are
self-contained. Tests (offline): `./venv/bin/python tests/test_astro.py` and `tests/test_weather.py`;
the owner controls and the shore sync: `/usr/bin/python3 -m unittest tests.test_listener tests.test_shore_sync`
(mock API on 127.0.0.1).

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

- 2026-11-01: v3 look tests and probes (several renders at once, up to `--jobs 3`), the render job and
  macOS's post-update indexing drove the load to about 30, with swap at 6.3 of 8 GB. They stalled Evan's
  Slay the Spire 2 co-op run: the host's API timed out and the client dropped. Share the Mac: one
  render at a time, `--jobs 1`, `nice`; SIGSTOP the render job when a game needs the CPU.

## Known weaknesses

- Still recognisably computer-made: flat-shaded polygons, noise textures.
- The cat, the heron and the owl are still small and simple; the sheep, fox, hares and crows were redrawn
  in v3 (`docs/v3/phase3-animals.md`, Known issues).
- `tests/test_shore_render.py` failed 5 of 7 on `main` from 2026-11-01 (its synthetic cairn found no spot that
  passed against reference r2); mended on `shore/cast` (2026-11-10).
- The shore's cast shadows: see "Cast shadows" above, Known issues.
- Mid-level clouds near the horizon streak toward the vanishing point (the plane projection).
- Weather can jump where separately rendered spans of a day meet (battery renders, a forecast
  refreshed mid-day).
- The sea render and the front layer still peak at ~250 MB per frame; strip them like the hill if
  memory gets tight.

## Ideas for next time

- **Painterly pass:** a post-process over the frames (Kuwahara or brush strokes, paper texture).
- **Blender renderer:** rebuild the scene in 3D, reusing `astro.py`, `weather.py` and `day.py`.
- **Location from the system:** follow the Mac when it travels (sky and weather) instead of Budapest.
