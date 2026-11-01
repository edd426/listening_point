# The Listening Point v3: more defined, more interesting

From Evan's interview on 2026-11-01, held after the shore went live. These are his answers; the
phases are their order. Every step gets a look test before it is installed.

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
  sky, when Evan wants it.
