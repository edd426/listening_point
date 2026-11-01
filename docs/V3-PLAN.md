# The Listening Point v3: more defined, more interesting

From Evan's interview on 2026-11-01, held after the shore went live. These are his answers; the
phases are their order. Every step gets a look test before it is installed.

## HANDOFF — state at 2026-11-01 ~17:00 CET (after the macOS 27.2 restart)

**Verified after the update** (macOS 27.2, 26B123): both venvs still import numpy 2.0.2, scipy 1.13.1
and Pillow 11.3.0 on Xcode's Python 3.9.6; both launchd jobs are loaded; frames render; the
desktop shows the live frame (captured); `shore/sync.json` holds r2 `7cbee1f4…`, `error` null; the
Keychain key works (`shore_sync.py --force`); `main` still rebuilds r2 bit-identically; the waypost
carrier is green. The lock screen was not checked (needs Evan's eye).

**Merged on `main` and pushed:**

| Part | Merge | Installed? |
|---|---|---|
| 2 sky: clouds (heaps parked behind `cumulus.HEAPS = False`) | `8b07231` | yes, 16:28 |
| 2 sky: air (geese, murmuration, gulls, contrails, balloon, kite) | `3a971cb` | yes, 16:52 |
| 3 hillside part 1: land (garden, shed, hives, gates, outcrops, gorse, heather, puddles) | `70ea7f3` | yes, 16:52 |

Probes were re-run on each merged head (tests, determinism, r2 digest): all PASS. The details are in
each part's doc under `docs/v3/`.

**Shared with a game.** From 16:43 to 16:51 the render job was SIGSTOPped while Evan's Slay the
Spire 2 co-op run recovered. The game sessions (`sts2-coop-*`) and Evan agreed on low priority from
16:51: the render job as usual (nice 10), other renders one at a time, `--jobs 1`, `nice -n 15`, no
parallel batches. If a game session says "pause", `kill -STOP` the render job again.

**Next, in order:**
1. Air + hillside installed at 16:52 (frames re-rendering).
2. **Phase 3 part 2, animals**, started 16:55 on `v3/animals` (`.claude/worktrees/v3-animals`):
   - a fox, hares, crows on the new gates and walls, bigger sheep;
   - use the coordinates in `docs/v3/phase3-hillside.md`;
   - **depth order:** animals are drawn in `front()` over all the near scenery, so they must be
     hidden behind the gate leaf and the garden walls where they stand behind them;
   - same probes, time ratio ≤1.15.
3. Suggested pause (not yet decided by Evan): let him live with phases 2 and 3 for a few days
   before phase 4 (sea) and phase 5 (story).

**For Evan to judge** (look tests in `out/look/v3/<part>/` of this checkout, top = before, bottom = after):
- clouds: `pair-*`, half size;
- air: `half-*`; a faint contrail arc in the upper right of `half-2026-11-05-1243` could read as a
  pale rainbow;
- hillside: `crop-*`, `wl-*`. Things to look at: the garden's size and place (upper left); the
  puddles on the path, which read as pale ovals (`wl-2027-04-06-1300`); the snow-covered gorse, which
  reads as grey-blue mounds (`wl-2027-01-27-1100`); the faceted outcrops up close.

**Review bar:**
- Restraint: Evan found the first grass "a bit distracting".
- Readable at a glance, rewarding up close.
- Keep the layout, colour, mood and real-world ties.
- No people.
- Reject anything that reads as pasted-on CG; the parked heaps are the example.

**Unfinished ideas:** a second try at heaped cumulus with a painted 2D approach (see "v3: heaps off"
in `docs/v3/phase2-clouds.md`). The aircraft should fly behind heaps above their height, if the heaps
come back.

**Where things live:** new worktrees go in `.claude/worktrees/<name>` inside this checkout (it is
gitignored), never as sibling folders in `~/Documents/Projects`. The old `lp-*` worktrees were all
merged and moved to the Trash on 2026-11-01. Their branches remain in git.

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
  - `v3/ground`: grass, the path, the walls.
  - `v3/objects`: the tower, the tree, the bench, the lamp.

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
  - `v3/clouds`: shaped clouds, sunbeams, sunrise/sunset on clouds.
  - `v3/air`: geese, starlings, gulls, aircraft and contrails, a
    balloon, a kite.

  Probes: the tests pass; renders are deterministic; the reference r2 digest stays `7cbee1f4…`
  (bit-identical reference renders, so no r3); time ratio ≤1.25 for clouds and ≤1.15 for air.
  Each part writes `docs/v3/phase2-<part>.md`.

  Evan: "merge them in as they come. You can also start on the next phase." So each phase-2 part is
  merged and installed as soon as it passes its probes and its look test.
- **2026-11-01: phase 3 (hillside) started**, part 1 on `v3/hillside`:
  built things (garden, shed, hives, gate, more wall) and land detail (outcrops, gorse, heather,
  wildflowers, puddles). The garden and wall are drawn from a stage parameter, for phase 5. Part 2
  (animals: a fox, hares, crows, bigger sheep) follows once part 1 lands, using its gate, walls and
  garden. Same probes, with time ratio ≤1.15.
- **2026-11-01: `v3/clouds` first pass (`acf9b4d`) held back at review.** Its probes passed, and the beams
  and the sunset colour on the mid layer were good. But the heaped cumulus read as smooth grey stickers
  (no bright lit tops or cauliflower edges, clip-art rows on the horizon, flat discs overhead), and
  fair days lost their soft cloud texture, against Evan's "upper sky is empty". Rework requested on
  the same branch.
- **2026-11-01 evening: after the macOS 27.2 restart.** Checks passed. Clouds, air and hillside
  part 1 were merged (`8b07231`, `3a971cb`, `70ea7f3`); only clouds is installed so far. Renders were
  paused for Evan's StS2 run. See the HANDOFF at the top.
