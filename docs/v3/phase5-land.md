# v3 phase 5, part 1: work on the land, and the marks the weather leaves

Branch `v3/story-land`, from `main` `a6887df`. Evan asked, for phase 5, for "a story that builds over weeks. All
of it is decided by the date, as the mysteries are, so a given day always renders the same." Part 1 covers two
of its four strands:
- **work on the land, done offstage**: a wall rises stone by stone over weeks, a garden is dug and planted;
- **weather leaves marks**: a storm's branch stays until it is cleared, driftwood washes up, snow drifts against
  the wall.

Part 2 (animal lives) and part 3 (echoes of the shore) come later and hang their own state on the same story
(see "For parts 2 and 3"). No people, ever: the work is implied by things that change between days.

## What was added

Two new modules:
- `renderers/procedural/story.py`: the story calendar. `Story(day, weather, cache_dir)` is built in `day.py`
  after the bay's plan (`day.story`), and hangs phase 3's stages on the `Day` (`day.garden_stage`,
  `day.wall_stages`), where the hillside already draws them from. In reference mode it is `NoStory`, which has
  nothing in it and sets nothing.
- `renderers/procedural/marks.py` (`MarksMixin`, added to `Frame`): the drawing.

Hooks, each a no-op when the story is empty:
- `land.py`:
  - `wall_body(..., gap=None)` and `wall(..., gap=None)`: a length of wall fallen or part rebuilt
    (`wall_gap`); the field walls take their gap from `day.wall_stages` (`field_gap`);
  - `hill()`: the field walls' shadows are as tall as what stands; snow drifts against the field walls
    (`mk_drift`) right after the walls are drawn.
- `hillside.py`:
  - `WallStage` has a new field, `gap` (default `None`, so phase 3's stages are unchanged);
  - `hs_wall`: passes the gap on, casts a shorter shadow where the wall is down, and draws its drift;
  - `hs_garden`: the spade after its bed (`mk_spade`), the logs after the shed (`mk_logs`);
  - `hillside()`: the fallen stones or the pile and the builder's line (`mk_wall`), and the branch
    (`mk_branch`), last.
- `tree.py`: the torn stub in the crown (`mk_scar`).
- `listening_point.py`'s `front()`: `driftwood()` right after the shore kit's objects, before the bottle.
- `fauna.py`: the occluders' key includes the gap, and its fallback draws the field walls with it.
- `weather.py`: `_synthetic_hourly(..., back=15)` can make more days before its date (the story makes a month
  before each block, to spin up lying snow); `_share` is cached (the same values; the story makes many days).

Nothing new draws from any existing generator. The story's seeds are `[5500 + strand, ...]`:
- 5501 the winter's weak wall (by the winter's year), 5503 whether a gale brings a branch down (by its date),
  5505 whether an onshore blow throws up driftwood, 5506 the logs, 5507 when the branch is cleared, 5508 the
  driftwood's pieces;
- 5520-5525 for the drawing: the fallen stones and the pile (by the winter), each stone's facets, the logs'
  slots, the branch's shape (by the day it fell), each piece of driftwood, each wall's drift.

Coordinates are pixels of the production frame (`--scale 0.75`, 2880 x 1800), x from the left, y from the top.

### The weather of the days before

`story.History` gives each earlier day as a `DaySum`: the strongest gust and the wind's direction then, the
strongest mean wind, the strongest wind blowing in from the sea (from 210 degrees, SSW), rain, snowfall and where
the wind blew it, the most snow lying, the lowest and highest temperature. A day is **workable** (fit for work
outside) unless it is unknown, a gale (gusts 15 m/s or more, or wind 11), rain-soaked (3 mm that day, or 12 mm
the day before), snowbound (1 cm lying) or frozen (never above 2 C).

Where the days come from, by the Day's own weather mode:

| mode | earlier days | cost |
|---|---|---|
| `synthetic` | `weather._synthetic_hourly`, a block of 32 days at a time (ordinals 32k .. 32k+31) made from a month before the block, so each block is the same whichever date asks; cached per process | see Probes |
| `fair`, `clear`, `fog` | one calm, dry, mild day (`CALM`): every day workable, nothing happens | about 1 ms |
| `auto`, `offline` (real) | the weather cache only, never the network: for each day the newest cached forecast covering it that was fetched **before the date began** (so a date's story does not change as the cache grows during that day); a day no cached forecast covers is unknown: nothing happened, no storm and no work | see Probes |

`tools/nightly.py` never prunes `~/Library/Caches/listening-point` (its `prune` removes only frame folders), so
the cache keeps every day since the job first ran (2026-10-02 on this Mac, 354 files, 5.5 MB on 2026-11-03,
about ten a day).

Synthetic blocks do not match the day's own `synthetic_day(date)` to the bit (that one is made from 15 days
before the date), but they agree on what matters (a gale, a soaking, snow lying) and each day has one value
whichever date asks, so the story never contradicts itself from one day to the next.

## What the story shows

### The wall that falls and is rebuilt

- **Which winter, which wall.** Each winter (mid November to the end of February) is weak with a chance of
  0.7, seeded by its year; its weak length is on one of three stretches, with its middle in a seeded range
  along it and a fallen length of 58-81 px (half length 0.010-0.014 of the frame's width):
  - `garden-front`, the garden's front wall (phase 3), middle 0.30-0.66 of the stretch;
  - `wall-upper`, the upper field wall, 0.42-0.80;
  - `wall-lower`, the lower field wall, 0.30-0.66.

  In synthetic weather seven of the ten winters from 2026-27 have a wall down (table under Known issues).
- **It comes down** the night after the first day, from 15 November, with gusts of 18 m/s or more, or a thaw
  (above 3 C within three days of a hard frost, -6 C or below). A winter with neither keeps its wall.
- **Fallen** (`WallStage.gap = (middle, half, "fallen", 0)`): a ragged V-shaped breach, down to about half the
  footing course in the middle; each stone stays or falls by a hash of where it is (`land.wall_gap`), so no
  generator moves. The dark core of the wall is lowered to match, and the wall casts a shorter shadow there.
  Its stones (22) lie in the grass on the near side, most within a metre of the foot (`mk_wall`).
- **Rebuilt** from the first workable day on or after 1 March (and at least five days after it fell), one step
  per workable day:
  1. stripped to the footings, a clean gap, the stones sorted into a heap beside it (24 stones in five rows),
     and two pale stakes at its ends with a line between them at the course being laid;
  2. the second course, then the third, laid from the gap's left end, a fifth of the gap a day (5 days each);
  3. the coping, a quarter a day (4 days);
  4. the heap goes down as the stones go in (to an eighth of it), and the leftovers are taken away the next
     workable day.

  So a wall stands whole again 16 workable days into March, three to four weeks in a typical spring; a wet or
  frozen week holds it up. The stones in the wall are the same stones at every stage (phase 3's rule).

### The garden, stepping with the work

Phase 3's garden year (`hillside.garden_stage`) is kept, but its work (digging, sowing, clearing, digging over)
moves on only after workable days:
- for each of `dug`, `sown`, `cleared`, `rough`: as far as phase 3's calendar had got on the last workable day,
  and no further than the work done allows (the workable days since the field's start, against 55% of its
  calendar days);
- `growth` and `ripe` are the plants' own, by the date;
- a day with no weather on record holds nothing up (the garden already has a year of its own; the wall does
  not), so with an empty cache the garden is exactly phase 3's;
- 45 days after a field's calendar end it is done whatever the weather.

In fair weather (every day workable) the garden is phase 3's to the bit (`tests/test_story.py`). In the
synthetic 2027 it lags the calendar by up to 0.06 on 57 days.

**The spade** stands in the bed being dug, where the digging stopped (`mk_spade`): an iron blade in the soil, an
ash shaft leaning a little, a T handle. It moves on overnight after each day of digging and goes when the last
bed is dug (39 days in the synthetic 2027).

### A storm's branch, and the logs it makes

- **It comes down** the night after a day with gusts of 20 m/s or more, with a chance of 0.5 (seeded by the
  date), or for certain at 24 m/s. One at a time: while a branch lies, a gale brings no other.
- **It lies** under the tree, to the left of the trunk, from (1234, 1283), pointing downwind of the gale (any
  wind with a westerly part; an easterly gale's branch is turned to the left, clear of the bench): a limb as
  thick as an arm at its torn end (0.2 m, about 8 px), 2.7-3.5 m long (100-135 px), forking into side branches
  that stand up off the grass and a fan of twigs. Its butt is pale splintered wood. If it came down in leaf it
  carries the tree's own leaf shapes and greens, wilting to brown over nine days and thinning; a winter branch
  is bare (`mk_branch`).
- **The tree** shows pale torn wood on a lower limb on the left of its crown where it broke, greying over 75 days
  (`mk_scar`; behind the leaves in summer).
- **It is cleared** the night after the 2nd-4th workable day after it fell (seeded), and cut into 4-7 logs that
  join a stack against the shed's gable, cut ends toward you (`mk_logs`): all stay a week, then one goes on the
  fire every three days.

### Driftwood

- **It comes ashore** the night after a day when the wind blowing in from the sea reached 8 m/s, with a chance
  of 0.85: one to three pieces, unless some already lie there.
- **Where.** On the shingle a little above the high water of that day and the two after it (2-5% of the beach's
  height above, never above 0.515 of the beach from low water), in one of two stretches: x 0.605-0.665 of the
  width (1742-1915 px, the steep beach left of the pier's root) or 0.885-0.962 (2549-2771 px, the flat beach right
  of the pier), lying along the tide line.
- **Keeping clear of the shore kit.** The kit's objects stand with their feet on the always-dry band (0.53 to 1
  of the beach, `tools/shore_reference.py`'s `DRY_V`; `shorekit/SCHEMA.md` 5.1 `dry`) and cast their shadows only
  on dry ground; driftwood lies below that band (tested), so every object is nearer than it and it never covers
  one. It is drawn like the bottle, after the kit's objects, and `shore_allow` hides it wherever an object stands
  in front. The reference frames have none (reference mode has no story), so `r2` is unchanged.
- **It goes** when a higher tide reaches it (from the ten minutes the tide, by `day.py`'s own formula sampled every
  ten minutes, comes within 0.015 of the beach's height of the lowest piece; it is also hidden while the sea is
  round it), or the night after the 2nd-6th workable day after it came (taken for the fire), or after 21 days.
- **Look** (`driftwood()`): a bent, tapering trunk of bleached silver-grey wood worn smooth, 1.0-1.9 m long at
  the hillside's scale (about 45-90 px on the far stretch, 90-130 px on the near one), lumpy where branches were,
  its top catching the light, cracks and paler streaks along the grain, often a gnarled root end, a splintered
  broken end, a shadow on the stones under it; darker when wet.

### Snow drifts

When snow lies (`wx.snow_cover` above 0.05 at the keyframe), the snow of the current spell (the days of lying snow
or snowfall before today, up to 21, and today's up to the minute) is added up as snowfall x (wind - 3 m/s) along
the downwind direction. Where that wind blew from beyond a wall toward you (its near side is the lee), a smooth
bank of snow rises against the wall's foot (`mk_drift`):
- up to 0.38 of the wall's height, by how much snow was blown (full at 25 cm m/s, by its square root), by how
  squarely the wall faces away from the wind, and by how much snow still lies (so the drifts go as the snow goes);
- deeper here and shallower there along the wall (a fixed wobble per wall), tapering at its ends and lower in a
  gap;
- its upper half leans toward you against the wall, its lower half runs out into the lying snow at the ground's
  own slope, so it reads as the wall's foot buried.

On all the field walls and the garden's walls. Drifts on a wall's far side would be hidden behind it and are
not drawn; with the westerly and north-westerly snow of most synthetic winters, the lee is often the far side.

## The calendar

`tools/story_calendar.py` prints, for each date, that day's weather as the story reads it, whether it was
workable, and what the story shows that day. With `--changes` only the dates on which something changes. The
synthetic year from 2026-11-01:

```
$ ./venv/bin/python tools/story_calendar.py --changes
weather synthetic; from 2026-11-01 for 365 days. A date's line is what shows that day (from the days before it); 'work' means that day itself was fit for work, so its work shows the next morning.
2026-11-01 Sun  gust  6.0 rain  0.0 snow 0.0 lying   0cm   3.0..12.4C work | -
2026-11-25 Wed  gust 10.1 rain  4.1 snow 0.0 lying   0cm   0.7.. 4.8C | wall wall-upper down
2026-12-08 Tue  gust  6.5 rain  0.0 snow 5.3 lying   7cm  -4.5.. 0.4C | wall wall-upper down, driftwood x1, drifts
2026-12-11 Fri  gust  5.4 rain  0.0 snow 0.0 lying   0cm  -3.8.. 7.5C work | wall wall-upper down, driftwood x1
2026-12-23 Wed  gust  5.4 rain  0.0 snow 0.0 lying   0cm   0.3.. 8.9C work | wall wall-upper down
2026-12-30 Wed  gust  8.7 rain  0.0 snow 4.9 lying   8cm  -4.3..-1.1C | wall wall-upper down, drifts
2027-01-09 Sat  gust  6.1 rain  0.3 snow 0.0 lying   0cm   2.2.. 6.1C work | wall wall-upper down
2027-01-21 Thu  gust 15.2 rain  0.0 snow 8.3 lying   8cm  -6.7..-0.5C | wall wall-upper down, branch (1d)
2027-01-22 Fri  gust  6.1 rain  0.0 snow 2.1 lying  10cm  -8.4.. 0.1C | wall wall-upper down, branch (2d), drifts
2027-02-02 Tue  gust  5.7 rain  0.0 snow 0.0 lying   0cm   3.7.. 8.6C work | wall wall-upper down, branch (13d)
2027-02-04 Thu  gust  6.2 rain  0.5 snow 0.0 lying   0cm   1.8.. 6.5C work | wall wall-upper down, logs 6
2027-02-14 Sun  gust  9.8 rain  0.0 snow 0.0 lying   0cm  -4.2.. 4.9C work | wall wall-upper down, logs 5
2027-02-17 Wed  gust  8.7 rain  0.0 snow 0.0 lying   0cm   4.9..14.1C work | wall wall-upper down, logs 4
2027-02-20 Sat  gust  5.2 rain  0.0 snow 0.0 lying   0cm   2.4..11.7C work | wall wall-upper down, logs 3, spade
2027-02-23 Tue  gust  7.7 rain  3.3 snow 0.0 lying   0cm   2.6..10.5C | wall wall-upper down, logs 2, garden behind 0.01, spade
2027-02-26 Fri  gust  8.5 rain  2.9 snow 0.0 lying   0cm   1.1.. 5.7C work | wall wall-upper down, logs 1, spade
2027-03-01 Mon  gust  5.3 rain  0.0 snow 0.0 lying   0cm  -2.5..10.5C work | wall wall-upper down, spade
2027-03-02 Tue  gust  5.5 rain  0.0 snow 0.0 lying   0cm   0.3..13.3C work | wall wall-upper 1.00 pile, spade
2027-03-03 Wed  gust  4.1 rain  0.0 snow 0.0 lying   0cm   3.9..17.0C work | wall wall-upper 1.20 pile, spade
2027-03-04 Thu  gust  9.8 rain  0.0 snow 0.0 lying   0cm   5.4..16.0C work | wall wall-upper 1.40 pile, spade
2027-03-05 Fri  gust  8.4 rain  0.0 snow 0.0 lying   0cm   2.1..13.3C work | wall wall-upper 1.60 pile, spade
2027-03-06 Sat  gust  3.4 rain  0.0 snow 0.0 lying   0cm   0.1..13.3C work | wall wall-upper 1.80 pile, spade
2027-03-07 Sun  gust  9.8 rain  0.0 snow 0.0 lying   0cm   2.5..15.7C work | wall wall-upper 2.00 pile, spade
2027-03-08 Mon  gust  4.2 rain  0.0 snow 0.0 lying   0cm   5.0..18.3C work | wall wall-upper 2.20 pile, spade
2027-03-09 Tue  gust  4.7 rain  0.0 snow 0.0 lying   0cm   4.0..17.3C work | wall wall-upper 2.40 pile, spade
2027-03-10 Wed  gust  3.5 rain  0.0 snow 0.0 lying   0cm   5.2..15.3C work | wall wall-upper 2.60 pile, spade
2027-03-11 Thu  gust  2.7 rain  5.9 snow 0.0 lying   0cm   5.6..14.2C | wall wall-upper 2.80 pile, spade
2027-03-13 Sat  gust  5.1 rain  0.0 snow 0.0 lying   0cm   5.8..14.9C work | wall wall-upper 3.00 pile, spade
2027-03-14 Sun  gust  9.8 rain  6.6 snow 0.0 lying   0cm   4.2.. 9.4C | wall wall-upper 3.25 pile, spade
2027-03-16 Tue  gust  7.7 rain  0.5 snow 0.0 lying   0cm   6.7..12.9C work | wall wall-upper 3.50 pile, spade
2027-03-17 Wed  gust  9.9 rain  0.0 snow 0.0 lying   0cm   6.4..12.7C work | wall wall-upper 3.75 pile, spade
2027-03-18 Thu  gust  3.9 rain  0.0 snow 0.0 lying   0cm   6.1..12.5C work | wall wall-upper 4.00 pile, spade
2027-03-19 Fri  gust  7.0 rain  0.0 snow 0.0 lying   0cm   4.8..13.0C work | spade
2027-03-26 Fri  gust  3.7 rain  0.0 snow 0.0 lying   3cm  -4.3.. 6.0C | drifts, garden behind 0.04, spade
2027-03-27 Sat  gust  5.5 rain  0.0 snow 0.0 lying   0cm   0.6..11.3C work | garden behind 0.05, spade
2027-03-31 Wed  gust  5.7 rain  3.7 snow 0.0 lying   0cm   5.9..15.8C | -
2027-05-31 Mon  gust 18.9 rain 36.6 snow 0.0 lying   0cm  18.6..28.9C | driftwood x1, garden behind 0.02
2027-06-03 Thu  gust 13.4 rain 19.3 snow 0.0 lying   0cm  18.2..29.5C | branch (1d), driftwood x1 (sea takes it 01:30), garden behind 0.06
2027-06-04 Fri  gust  5.3 rain  1.1 snow 0.0 lying   0cm  18.8..29.2C | branch (2d), garden behind 0.06
2027-06-12 Sat  gust  5.0 rain  0.0 snow 0.0 lying   0cm  17.7..28.7C work | logs 6
2027-06-22 Tue  gust 14.7 rain 12.8 snow 0.0 lying   0cm  11.5..21.8C | logs 5
2027-06-25 Fri  gust  5.4 rain  1.0 snow 0.0 lying   0cm  14.8..24.7C | logs 4
2027-06-28 Mon  gust 22.4 rain 30.5 snow 0.0 lying   0cm  14.4..25.0C | logs 3
2027-06-30 Wed  gust  6.2 rain  0.0 snow 0.0 lying   0cm  11.9..23.4C | branch (1d), logs 3
2027-07-01 Thu  gust  9.5 rain  7.2 snow 0.0 lying   0cm  16.1..25.6C | branch (2d), logs 2
2027-07-04 Sun  gust 10.1 rain  7.9 snow 0.0 lying   0cm  17.5..27.3C | branch (5d), logs 1
2027-07-07 Wed  gust 18.0 rain 20.3 snow 0.0 lying   0cm  14.3..26.6C | branch (8d)
2027-07-13 Tue  gust 17.6 rain 20.6 snow 0.0 lying   0cm  13.8..24.6C | logs 7
2027-07-23 Fri  gust  3.5 rain  0.0 snow 0.0 lying   0cm  17.7..31.2C work | logs 6
2027-07-26 Mon  gust  5.5 rain  0.0 snow 0.0 lying   0cm  19.8..30.8C work | logs 5
2027-07-29 Thu  gust  6.5 rain  0.0 snow 0.0 lying   0cm  17.4..28.4C work | logs 4
2027-08-01 Sun  gust  4.7 rain  0.0 snow 0.0 lying   0cm  17.4..28.4C work | logs 3
2027-08-04 Wed  gust  5.2 rain  0.0 snow 0.0 lying   0cm  20.1..32.0C | logs 2
2027-08-07 Sat  gust  6.5 rain  0.0 snow 0.0 lying   0cm  17.7..28.7C work | logs 1
2027-08-10 Tue  gust  7.7 rain  0.0 snow 0.0 lying   0cm  15.6..26.6C work | -
2027-08-17 Tue  gust  6.9 rain  7.2 snow 0.0 lying   0cm  15.7..27.4C | branch (1d)
2027-08-22 Sun  gust  6.9 rain  0.0 snow 0.0 lying   0cm  15.5..26.4C work | logs 4
2027-09-01 Wed  gust 13.2 rain  5.0 snow 0.0 lying   0cm  15.1..25.6C | logs 3, garden behind 0.02
2027-09-04 Sat  gust  5.5 rain  0.0 snow 0.0 lying   0cm  10.2..23.9C work | logs 2
2027-09-07 Tue  gust  8.0 rain  0.0 snow 0.0 lying   0cm  10.5..21.6C work | logs 1
2027-09-10 Fri  gust  4.2 rain  0.0 snow 0.0 lying   0cm  12.6..23.6C work | -
2027-10-12 Tue  gust  1.7 rain  4.5 snow 0.0 lying   0cm  13.8..22.6C | branch (1d), driftwood x2, garden behind 0.02
2027-10-14 Thu  gust  0.9 rain  0.0 snow 0.0 lying   0cm  14.2..22.3C work | branch (3d), driftwood x2 (sea takes it 02:10)
2027-10-15 Fri  gust  1.9 rain  0.0 snow 0.0 lying   0cm  12.7..20.7C work | branch (4d)
2027-10-17 Sun  gust  8.0 rain  0.0 snow 0.0 lying   0cm  11.2..24.4C work | logs 6
2027-10-27 Wed  gust  1.3 rain  0.0 snow 0.0 lying   0cm   7.2.. 8.8C work | logs 5
2027-10-30 Sat  gust  5.0 rain  0.0 snow 0.0 lying   0cm   5.8..18.5C work | logs 4, garden behind 0.03

365 days: 232 fit for work (64%), 11 with gusts of 20 m/s or more, 3 with an onshore blow of 8 m/s, 35 with snow lying.
days showing: wall 114, branch 46, logs 112, driftwood 22, drifts 25, spade 39, garden 57
```

## Probes

PROBES

## Look test

LOOK

## Known issues

- **Real weather, read twice.** A date's story reads each earlier day from the newest forecast fetched before
  that date began, so the next date may read the same earlier day from a later forecast. Where the two disagree
  across a threshold (gusts just either side of 20 m/s, say), a mark can appear one day and be gone the next
  without the work that would clear it. Rare, and the same kind of seam as "weather can jump where separately
  rendered spans of a day meet" (STATUS.md).
- **Synthetic history is made in blocks.** Earlier days of synthetic weather come from 32-day blocks, not from
  `synthetic_day(date)` itself (which spins up only 15 days), so the story's reading of a day can differ a little
  from that day's own frames (a gust of 19.9 m/s against 20.1). It never contradicts itself from one date to the
  next.
- **Fair weather shows almost nothing.** `--weather fair` has no gales, no rain and no snow, so no wall comes down,
  no branch, no driftwood, no drifts; only the spade while the beds are dug. Use `--weather synthetic` (dates in
  "The calendar") to see the story.
- **The rebuilt stones are the old stones.** The stability rule (every stone drawn from the same draws at every
  stage) means a rebuilt length looks exactly as it did before it fell, lichen and all, the day the leftovers go.
- **Small at desktop size.** The builder's stakes and line are 1-2 px, the spade's shaft 1 px, the logs 7 px
  across; the gap itself, the heap, the branch and the driftwood read at a glance, these only up close.
- **The branch always lies left of the trunk.** An easterly gale's branch is turned to lie there too (clear of the
  bench). The crown keeps all its leaves where it broke; only the torn wood shows (and only through a bare crown).
- **Drifts only on the near side.** With the westerly and north-westerly snow of most synthetic winters a wall's
  lee is often its far side, hidden behind it; those drifts are not drawn.
- **Driftwood is drawn in front.** Like the bottle, it is drawn after the near scenery, so a pebble of the shingle
  nearer than it cannot cover it.
- **Logs.** Each cleared branch's logs stay about a month; the stack shows on about 110 days of the synthetic year.
- **A wall that never finishes.** If a spring had fewer than 16 workable days by the end of June the wall would
  stand whole on 1 July without them. None of the seven weak synthetic winters of 2026-2036 comes near: their
  walls fell between 24 November and 8 January and stood whole again between 18 March and 2 April:

  | winter | stretch | fell | whole again |
  |---|---|---|---|
  | 2026-27 | wall-upper | 2026-11-24 | 2027-03-19 |
  | 2027-28 | garden-front | 2027-12-14 | 2028-03-26 |
  | 2028-29 | garden-front | 2028-12-17 | 2029-03-23 |
  | 2029-30 | (no weak wall) | | |
  | 2030-31 | wall-lower | 2030-12-04 | 2031-03-20 |
  | 2031-32 | (no weak wall) | | |
  | 2032-33 | garden-front | 2033-01-08 | 2033-04-02 |
  | 2033-34 | wall-upper | 2033-12-20 | 2034-03-23 |
  | 2034-35 | (no weak wall) | | |
  | 2035-36 | wall-upper | 2035-12-18 | 2036-03-18 |
- The fauna's occluders are recorded per date with the gap, so sheep and crows behind a fallen length show
  through it; a crow perching on a stretch with a gap stands on what is left there.

## For parts 2 and 3

- Hang new strands on `Story` the way these are: a method per strand, reading `self.hist` (the weather of the
  days before, `History`) and `rng(strand, ...)` with a new strand number (9 and up for the calendar, 26 and up
  for drawing); give `NoStory` an empty default for it, so reference mode stays empty.
- The pale seal is seaplan's seal 0 on `SEAL_SPOTS[0]`; her low waters are counted by `SeaPlan.low_water`.
- `History.workable(d)`, `History.count(a, b)` and `tide_samples(date, ...)` are there to reuse.

## Status

STATUS
