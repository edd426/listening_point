# The Listening Point v3: more defined, more interesting

From Evan's interview on 2026-11-01, held after the shore went live. These are his answers; the
phases are their order. Every step gets a look test before it is installed.

## HANDOFF — pickup after Evan's macOS restart (written 2026-11-01 ~15:20 CET)

**The plan, in Evan's words:** "don't start the animals and instead I restart my computer to update
the MacOs version, then come back and you make sure everything works, then we continue."
The session that ran phases 1–3 ended with the restart. Its agents are gone; their work is on the
branches below, and each branch's doc has a "Status at pause" section. Read this section, then
`## Status` at the bottom, then the part docs.

### Step 1 — make sure everything works after the update

APP=`~/Library/Application Support/The Listening Point`, ROOT=`~/Pictures/Wallpapers/The Listening Point`.

1. **Python is the likeliest break.** Both venvs point at Xcode's Python. Before the update:
   - Xcode's Python was 3.9.6, with numpy 2.0.2, scipy 1.13.1 and Pillow 11.3.0, on macOS 27.0.1 (26A434).
   - The two venvs are `$APP/venv` (installed) and `~/Documents/Projects/listening_point/venv` (dev).

   Check:
   - `"$APP/venv/bin/python" -c "import numpy, scipy, PIL; print('ok')"`, and the same for the dev venv.
   - If either fails, move that venv to the Trash and run `tools/install.sh` from `listening_point`
     `main`. It rebuilds `$APP/venv` only when `venv/bin/python` is missing. Rebuild the dev venv
     with `python3 -m venv venv && venv/bin/pip install -r requirements.txt`.
2. **Jobs:** `launchctl list | grep listening-point` shows both `.live` and `.render`. If not, re-run
   `tools/install.sh` from `main`.
3. **Frames:**
   - `ls "$ROOT/days/$(date +%F)" | wc -l` grows, and the current minute's `HHMM.jpg` exists.
   - `tail ~/Library/Logs/listening-point.log` shows renders and no tracebacks.
   - Before the restart, 2026-11-01 had 777 frames and 2026-11-02 had 901, rendering.
4. **What Evan sees:**
   - The desktop shows the live frame, through the helper `$APP/live_wallpaper`.
   - The lock screen and Mission Control show `$ROOT/The Listening Point.heic`.
   - An OS update can reset the wallpaper store; `tools/install.sh` sets it again and backs up
     `Index.plist`. Ask Evan to glance at the desktop and the lock screen.
5. **Shore on the Mac:** `$APP/shore/sync.json` should have:
   - `reference` = `r2` / `7cbee1f442afce967826b8e6f6aaffddd8921391b138a487f359b4d9024d35fa`;
   - `error` null;
   - `last_ok` recent.

   Only `r2` is in `$APP/shore/reference/` (r1 is in `$APP/shore/retired/`). The Keychain key
   (service `listening-point-github`, account `listener`) must still be readable: check with
   `"$APP/venv/bin/python" -I "$APP/src/tools/shore_sync.py" --force`.
6. **The dev environment still reproduces r2.** Check from `listening_point` `main`:
   `venv/bin/python tools/shore_reference.py /tmp/r2check --reference r2` → digest `7cbee1f4…`.
   - If a new numpy changes it, the phase probes' "r2 unchanged" baseline must be re-taken from
     `main` on the new setup.
   - The Mac's published r2 stays what counts; do not republish.
7. **Nothing else depends on the Mac.** The carrier (waypost, GitHub Actions) runs at 22:17, 23:17
   and 05:11 UTC. Wren's first shore reading is about 00:09 UTC and Gnomon's about 02:02 UTC.
   Check with `gh run list -R edd426/waypost --workflow carrier.yml`.

### Step 2 — then continue (Evan's standing go-ahead: build, merge, install, report; no need to ask)

Install recipe, the same every time:
1. `git merge --no-ff` the part into `main`, run the tests, push.
2. Move today's remaining frames and tomorrow's out of `$ROOT/days/` to the Trash, so they re-render.
3. Run `tools/install.sh`.
4. Check that a new frame appears.

| Part | Branch / worktree | State at pause | Next |
|---|---|---|---|
| 2 sky: clouds | `v3/clouds`, `~/Documents/Projects/lp-v3-clouds` | v2 at `202b860` reviewed. Heaped cumulus parked behind `cumulus.HEAPS = False` (code `096a314`, head `98f4885`). All four probes PASS on `096a314`: 45 tests; 60/60 frames identical; r2 `7cbee1f4…`; ratio ≈1.01 because the heaps read as CG bells. Ships: cover that follows the forecast, sunrise and sunset colour on every layer, mid-layer cloudlets, beams through cloud, paler sea reflections | Glance at `scratchpad/v3/clouds/{1,3,6b,7,8,9}-*-d-v3.jpg` (re-render if the scratchpad is gone), then **merge first** and install |
| 2 sky: air | `v3/air`, `~/Documents/Projects/lp-v3-air` | `0a18623`: all six done (geese, murmuration, gulls, contrails and aircraft, balloon, kite). Tests PASS, r2 PASS on `e6e8869`, timing 0.76–0.85 | Run determinism and the r2 digest on the head, do a look-test review at full and half size, then merge. Conflict: air's line beside `self.clouds(full)` in `sky()` must stay *before* the clouds are drawn. Watch the old contrails that curve into faint dusk arcs. Then install |
| 3 hillside: land | `v3/hillside`, `~/Documents/Projects/lp-v3-hillside` | `a3b7cd7`: walled garden (4 staged beds, shed, 3 hives, wicket gate, a new wall in 5 staged stretches), open field gate, outcrops, gorse, heather, wildflowers, puddles; `GardenStage`/`WallStage` for phase 5. Tests (52), determinism and r2 PASS; timing ~1.03–1.09 | Fix the shed-shadow anchoring, re-run probes 2–3, render the before/after look test (script ready), review it, then merge and install. For Evan to judge: the garden's size and place (upper left); the gorse in spring; puddles that might read as blue dots on the path |
| 3 hillside: animals | not started (Evan: not before the restart) | — | Once the land part is in: a fox, hares, crows on the new gates and walls, bigger sheep, using the coordinates in `docs/v3/phase3-hillside.md`. Same probes, ratio ≤1.15. **Depth order:** animals are drawn over all the near scenery today, so a sheep behind the new gate or garden wall would show in front of it. Part 2 must fix that |

The scratchpad look tests are in `/private/tmp/claude-501/.../scratchpad/v3/`. They may not survive
the restart; re-render from the scripts and recipes in the part docs if they are gone.

**Review bar:**
- Restraint: Evan found the first grass "a bit distracting".
- Readable at a glance, rewarding up close.
- Keep the layout, colour, mood and real-world ties.
- No people.
- Reject anything that reads as pasted-on CG; the parked heaps are the example.

**Suggested pause** (my recommendation, not yet decided by Evan): once phases 2 and 3 are installed,
let him live with them for a few days before phase 4 (sea) and phase 5 (story).

**Unfinished ideas:** a second try at heaped cumulus with a painted 2D approach (see "v3: heaps off"
in `docs/v3/phase2-clouds.md`). The aircraft should fly behind heaps above their height, if the heaps
come back.

## What Evan asked for

- **More defined:** the ground and the objects. He picked these over the distance or the picture as a
  whole. They look soft and flat at normal viewing distance.
- **Style:** toward a *detailed hand-drawn 2D game background*, with rich texture, readable shapes and a
  little stylisation. It should not become a photo, and not a realist oil painting either.
- **More interesting** in three ways:
  - visible at a glance;
  - rewarding when you look close;
  - telling a story that builds over weeks.

  Of the four on offer, he left out "different each day".
- **Empty areas:** the upper sky, the left hillside and the open sea.
- **Busyness:** "a bit livelier". Noticeably more going on, but nothing fast or flashing; it sits
  behind his work all day.
- **Must not change:**
  - the layout: tower left of centre, tree, bench, lamp, pier bottom right, island on the horizon;
  - the colour and mood;
  - the real-world ties: sky, weather, tide and seasons drive everything.
- **No people.** The place is seen, never peopled. The observer and the listener stay offstage,
  implied by lights, doors and things that change overnight.
- **Render budget:** up to 2x today's, so about 6 h of background rendering per day instead of
  about 3 h.
- **Review:** a look test at every step, with before and after pictures at his real screen size
  (1440x900 pt). He says go before anything is installed.

## Phases (Evan: definition first)

1. **Definition: the ground and the objects.**
   - Grass that reads as tufts and blades in the foreground, finer with distance.
   - A path with edges, stones and wear.
   - Crisp shingle stones.
   - Stonework and mortar on the tower, wood grain on the bench and the pier, bark and shaped leaf
     masses on the tree.
   - Contact shadows and edge contrast, so things sit on the ground.
   - No new things, and no layout change.
2. **Sky** (he picked all four):
   - bigger shaped clouds with lit tops, driven by the forecast;
   - flocks: geese in a V in the migration months, starlings at autumn and winter dusk, wheeling gulls;
   - things in the air: far aircraft and contrails when the air allows them, a kite on windy days, a
     balloon on calm mornings;
   - light and colour: sunbeams through cloud, stronger sunrise and sunset.
3. **Hillside:**
   - more animals: sheep big enough to read, a fox, hares, crows on the fence (and no dog: with no
     people, a dog alone reads wrong);
   - built things: a stone wall, a shed, beehives, a small garden, a gate;
   - land detail: rock outcrops, gorse and heather, wildflower patches, puddles after rain.
4. **Sea:**
   - more boats: fishing boats working, sailboats, a ferry to the island on a timetable;
   - sea life: seals on the rocks, dolphins, gannets diving, a cormorant drying its wings;
   - light on water: cloud shadows, wind patterns, glitter;
   - markers: buoys, lobster-pot floats, a channel marker.
5. **Story over weeks:**
   - work on the land, done offstage: a wall rises stone by stone over weeks, a garden is dug and
     planted;
   - animal lives: lambs grow up, the cat has kittens, a seal returns to the same rock;
   - weather leaves marks: a storm's branch stays until it is cleared, driftwood washes up, snow drifts
     against the wall;
   - echoes of the worlds: the listener's boat and life answer the shore's history.

   All of it is decided by the date, as the mysteries are, so a given day always renders the same.

## Constraints that cut across phases

- **The shore's reference set.** Anything that changes how the shingle, the pier or the water near them
  looks changes the reference pictures that Wren's and Gnomon's objects are judged against. Such a step
  must build a new reference (`r2`), publish it, re-pin it in waypost, and replay the live objects
  against it. Plan any phase-1 change to the shore band with that in mind, or leave the band alone.
- **Determinism and cost.** Keep the per-minute frame cache: the near scenery changes only with the light.
  Measure the render time of one full day before and after every step.
- **The Dock.** It is auto-hidden since 2026-11-01. If Evan goes back to a visible Dock, his fallback is to
  re-frame the view so the shore sits higher. That conflicts with "the layout must not change", so it
  would need his call then.

## Status

- **2026-11-01: phase 1 started** (Evan: "Yes, start"). Two parallel pieces, each in its own worktree
  and branch:
  - `v3/ground` (`~/Documents/Projects/lp-v3-ground`): grass, the path, the walls.
  - `v3/objects` (`~/Documents/Projects/lp-v3-objects`): the tower, the tree, the bench, the lamp.

  Each writes `docs/v3/phase1-<part>.md`, plus look-test images under the session scratchpad's
  `v3/<part>/`. They hold to these probes:
  - the tests pass;
  - renders are deterministic;
  - the shore strip and deck are pixel-identical in the reference crops;
  - the render time is at most 2x.

  Next: merge both into one branch, run the look test at real point size, and get Evan's go before
  installing.
- **2026-11-01: phase 1 merged** on `v3/phase1` (probes pass, see `docs/v3/phase1.md` there). Look
  test shown to Evan. The install moves the shore to reference r2. Waiting on Evan's go.
  Evan's verdict: "It looks fine. A little better. The grass is a bit distracting, but I like what you
  did with everything else." So the next step is to calm the grass (lower tuft contrast and density,
  less yellow in summer) and show that scene again before installing.
- **2026-11-01: phase 1 installed** (Evan, on the calmer grass: "It's great. Let's go with that.").
  `main` `4192c35`; the shore moved to reference r2 (waypost `docs/shore/STATUS.md`). Next: phase 2, the
  sky.
- **2026-11-01: standing go-ahead** (Evan: "Yes, please keep going without asking for my go-ahead.").
  Phases 2-5 are built, reviewed against their look test and probes, and installed without waiting
  for him. Each look test is still rendered and left for him, and he can veto after the fact. A
  reference change (rN) follows the waypost README's "Changing the reference set".
- **2026-11-01: phase 2 (sky) started.** Two parallel parts from `main` `4192c35`:
  - `v3/clouds` (`~/Documents/Projects/lp-v3-clouds`): shaped clouds, sunbeams, sunrise/sunset on clouds.
  - `v3/air` (`~/Documents/Projects/lp-v3-air`): geese, starlings, gulls, aircraft and contrails, a
    balloon, a kite.

  Probes: the tests pass; renders are deterministic; the reference r2 digest stays `7cbee1f4…`
  (bit-identical reference renders, so no r3); time ratio ≤1.25 for clouds and ≤1.15 for air.
  Each part writes `docs/v3/phase2-<part>.md`.

  Evan: "merge them in as they come. You can also start on the next phase." So each phase-2 part is
  merged and installed as soon as it passes its probes and its look test.
- **2026-11-01: phase 3 (hillside) started**, part 1 on `v3/hillside` (`~/Documents/Projects/lp-v3-hillside`):
  built things (garden, shed, hives, gate, more wall) and land detail (outcrops, gorse, heather,
  wildflowers, puddles). The garden and wall are drawn from a stage parameter, for phase 5. Part 2
  (animals: a fox, hares, crows, bigger sheep) follows once part 1 lands, using its gate, walls and
  garden. Same probes, with time ratio ≤1.15.
- **2026-11-01: `v3/clouds` first pass (`acf9b4d`) held back at review.** Its probes passed, and the beams
  and the sunset colour on the mid layer were good. But the heaped cumulus read as smooth grey stickers
  (no bright lit tops or cauliflower edges, clip-art rows on the horizon, flat discs overhead), and
  fair days lost their soft cloud texture, against Evan's "upper sky is empty". Rework requested on
  the same branch.
