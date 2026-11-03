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

  2026-27 is weak at the upper field wall, 2027-28 and 2028-29 at the garden's front wall, 2029-30 not at all,
  2030-31 at the lower field wall.
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
  height above, never above 0.515 of the beach from low water), in one of two stretches: x 0.605-0.685 of the
  width (the steep beach left of the pier) or 0.885-0.962 (the flat beach right of it).
- **Keeping clear of the shore kit.** The kit's objects stand with their feet on the always-dry band (0.53 to 1
  of the beach, `tools/shore_reference.py`'s `DRY_V`; `shorekit/SCHEMA.md` 5.1 `dry`) and cast their shadows only
  on dry ground; driftwood lies below that band (tested), so every object is nearer than it and it never covers
  one. It is drawn like the bottle, after the kit's objects, and `shore_allow` hides it wherever an object stands
  in front. The reference frames have none (reference mode has no story), so `r2` is unchanged.
- **It goes** when a higher tide reaches it (from the ten minutes the tide, by `day.py`'s own formula sampled every
  ten minutes, comes within 0.015 of the beach's height of the lowest piece; it is also hidden while the sea is
  round it), or the night after the 2nd-6th workable day after it came (taken for the fire), or after 21 days.
- **Look** (`driftwood()`): bleached silver-grey wood, 1.0-1.9 m long at the hillside's scale (60-125 px), lying
  along the tide line, a darker shadow on the stones under it, cracks along the grain, often a gnarled root end;
  darker when wet.

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
CALENDAR
```

## Probes

PROBES

## Look test

LOOK

## Known issues

ISSUES

## For parts 2 and 3

- Hang new strands on `Story` the way these are: a method per strand, reading `self.hist` (the weather of the
  days before, `History`) and `rng(strand, ...)` with a new strand number (9 and up for the calendar, 26 and up
  for drawing); give `NoStory` an empty default for it, so reference mode stays empty.
- The pale seal is seaplan's seal 0 on `SEAL_SPOTS[0]`; her low waters are counted by `SeaPlan.low_water`.
- `History.workable(d)`, `History.count(a, b)` and `tide_samples(date, ...)` are there to reuse.

## Status

STATUS
