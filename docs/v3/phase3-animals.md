# v3 phase 3, part 2: the animals

Branch `v3/animals`, from `main` `5b1b55e`. Evan asked for "more animals: sheep big enough to read, a fox,
hares, crows on the fence (and no dog: with no people, a dog alone reads wrong)". This part adds them to
the hillside that part 1 built. It also fixes depth order: an animal standing behind a wall, a gatepost or
the open gate is now hidden behind it. No people, no dog.

## What was added

New module `renderers/procedural/fauna.py` (`FaunaMixin`): the sheep (moved here from `life.py` and redrawn),
the fox, the hares, the crows, and the occlusion. The schedules are in `renderers/procedural/events.py`
(`Schedule._fauna`, `fox_at`, `hares_at`, `crows_at`, and the reworked `sheep`). They are drawn in `front()`
(`listening_point.py`) after the shore's objects: sheep, hares, fox, crows, then the small life and the cat.

All coordinates below are pixels of the production frame (`--scale 0.75`, 2880 x 1800): x from the left,
y from the top.

**Style.** Each animal is a small sprite (`Sprite` in fauna.py), built from a few shapes in metres. It has
one dark edge round its whole silhouette, a lit top, a darker underside, and a rim on the side the sun (or
the moon) is on. Everything is lit by the frame's own `lit()`: sun, moon, sky, the bounce from the grass,
and the lamps' pools at night. A soft contact shadow sits under each animal, and when the sun is out a cast
shadow falls across the grass away from it. The scale is `LIFE_M = 76` px per metre at a perspective of 1
on a 3840-wide frame, a little under the tower's 72 x 1.0 once perspective is applied. It is stylised:
the field walls and the gate are drawn at about half the tower's scale (part 1), so a sheep stands about
twice a field wall's height.

### The sheep (bigger, and kept to their field)

- **Where:** as before. Each ewe's daily base point is x 144-720, y 1278-1494, and she drifts about 100 px
  sideways and 32 px up or down. She now keeps to whichever side of the field walls her base point is on:
  in front of a wall at least 18 px below its foot, or behind it no more than 10 px above it. So a wall hides
  her legs, and she is never drawn through a wall. In the upper field she stays out of the walled garden.
  At night the ewes fold against the wall on their own side: the old fold at x 144-288, y 1390-1435 in the
  lower field, and its mirror tucked behind the upper wall for ewes in the upper field. Lambs (mid March to
  May) follow their mothers.
- **Size:** at y 1400 the fleece is about 72 px long and 49 px from the feet to the top of the back,
  against about 42 x 32 before (about 1.6x). Lambs are 0.6 of that.
- **Look:** blackface ewes. The fleece is a woolly barrel, scalloped along the back. It is lit from above in
  four steps, from the sunlit back down to a shaded belly, with curls drawn into it. The ewes have black faces
  with a light line down the nose, ears out sideways, and four thin dark legs. A ewe can be side on, walking
  toward you (her face and ears toward you), or walking away. The view follows which way she is drifting.
  Grazing ewes have their heads down at the grass. At night the ewes lie down (lambs stand), heads up or
  resting. From June to mid July the ewes are shorn: smaller and greyer.
- **Code:** `fauna.sheep`, `fauna.draw_sheep`, `events.Schedule.sheep`, `events.keep_to_field`.

### The fox

- **When:** at most one visit at a time, decided by the date:

  | window | chance per day |
  |---|---|
  | dawn, sunrise -1.3 h to +0.3 h | 32% |
  | dusk, sunset -0.4 h to +1.3 h | 42% |
  | late evening, sunset +1.6 h to 22:54 | 18% |
  | small hours, 00:24 to sunrise -1.9 h | 12% |
  | full daylight, sunrise +2 h to sunset -2.5 h | 5% |

  There is no visit in heavy rain, thunder or wind of 15 m/s and over. Visits are at least 30 minutes apart.
  Over 2027 (every third day, `fair` weather), that averages 1.06 visits a day of 29-53 minutes each, and
  4.3% of the fox's minutes fall in full daylight (the test allows 15%). On a few days the
  fox stays away (see `fauna.fox`; the reason is in `docs/SPOILERS.md`).
- **Where:** one of four routes (`events.FOX_ROUTES`), walked either way. It comes in past the frame's edge
  and leaves the same way. "Stop" marks where it stays a while:

  | route | waypoints |
  |---|---|
  | garden | in from the left at (-130, 1303); mouses at (101, 1291); sits by the wicket gate at (432, 1267), its back to you; stands at (541, 1327); through the gateway (495, 1440) -> (484, 1516); mouses at (340, 1620); out at the bottom (29, 1926) |
  | upper | along the upper field: (115, 1316), (288, 1341), (490, 1372), (720, 1400), (616, 1307), mousing, standing and sitting by turns |
  | lower | up from (691, 1926); mouses at (628, 1706); stands at (432, 1629); sits in the corner behind the open gate at (340, 1479), seen between its bars; mouses by the gorse at (219, 1552); out to the left at (-130, 1523) |
  | crest | along the skyline behind the garden at y 1150-1168, behind the shed, the hives and the back wall (standing at (432, 1153)); down past the gorse to (576, 1323); through the gateway and out at the bottom |

- **Poses:** trotting (legs in diagonal pairs, alternating by the minute), standing (half the time with its
  head turned to look at you), mousing (crouched, nose down), the pounce (one minute, arched in the air,
  after 40% of mousing stops), sitting with its tail round its feet, and sitting with its back to you at the
  garden wall.
- **Size:** about 69 px from nose to tail tip and 34 px to the ear tips at y 1400. It trots about 70 px
  a minute (0.024 frame widths).
- **Look:** rufous, with a white chest, cheeks and tail tip, black ear backs and black stockings.
- **Code:** `fauna.fox`, `fauna.draw_fox`, `events.fox_track`, `events.Schedule.fox_at`.

### The hares (in place of the rabbits)

The rabbits in `life.critters()` were moved out and redrawn as hares, rather than adding a second animal of
the same shape. `critters()` keeps the bats, swallows and butterflies.

- **When:** a dawn window (sunrise -0.7 h to +1.6 h; 70% of days) and a dusk window (sunset -1.5 h to
  +0.7 h; 75%), less often in December and January, and not in heavy rain, thunder or a gale. Each window has
  1-3 hares. Each arrives in the first 40% of the window and stays for 40-75% of it, loping to a new spot
  1-3 times (two minutes in the lope). Its pose changes every 3 minutes: grazing hunched (55%), sitting (30%)
  or upright and alert (15%). It changes the way it faces every 11 minutes.
- **Boxing:** from day 60 to day 121 (March and April), in half the windows with two hares or more. Two hares
  stand up facing each other about 0.36 m apart and box for 3-6 minutes. One lopes over the minute before, and
  one chases the other off the minute after. Their forelegs and ears change by the minute. In 2027 (every third
  day) there is boxing on 6 of 21 days in that span.
- **With the fox:** while the fox is out, hares within 0.22 frame widths of it sit up and face it. One the
  fox comes within 0.09 of lopes away for a minute and is gone.
- **Where:** the upper field (x 58-922, from y 1269 down to 43 px short of the walls' foot) and the lower field
  (x 86-749, from 36 px below the walls' foot to y 1750). They stay clear of the rocks and the gorse
  (`events.NO_SIT`).
- **Size:** 1.3x the life scale: at y 1550 a grazing hare is about 55 px long, and an upright one about
  50 px tall to its ear tips.
- **Look:** tawny, with a pale belly, black-tipped ears that show against the body, and a white scut with a
  black top.
- **Code:** `fauna.hares`, `fauna.draw_hare`, `events.field_point`, `events.Schedule.hares_at`.

### The crows

- **When:** by day, from sunrise +0.4 h to sunset -0.25 h. Visits arrive about 2.4 an hour and last 3-45
  minutes (mean about 14), each with 1-3 birds. There are fewer in rain, strong wind or fog. Visits at the same
  perch don't overlap. In 2027 (every third day, sampled every 10 minutes of daylight) at least one crow is
  out in 41% of daytime minutes. A crow's pose changes every 2 minutes (perched, looking back over its shoulder,
  hunched, calling with its bill open, preening), and its facing every 7 minutes.
- **Where:** perches, weighted (`events.CROW_SITES`, `CROW_P`):

  | perch | weight | where |
  |---|---|---|
  | upper field wall's coping | 27% | (-28, 1341) to (392, 1451) |
  | lower field wall's coping | 17% | (590, 1492) to (950, 1680) |
  | the open gate's top bar | 13% | x 336-398 along the leaf |
  | hinge post top | 7% | (426, 1462)^30 |
  | latch post top | 7% | (564, 1487)^32 |
  | garden front wall's coping | 13% | x 102-385, y 1238-1247, ^18-19 |
  | garden front wall east of the wicket | 4% | x 458-484 |
  | garden right wall's coping | 4% | (494, 1244) to (536, 1195) |
  | the grass beside a grazing sheep | 8% | about 1 m from her, walking or pecking |

  Birds of one visit sit about half a metre apart. Each crow's feet are put on the topmost stone or rail of
  the recorded mask under it (`occl_top`), so it stands exactly on the coping or the bar as drawn, not on a
  smooth line. A crow skips a perch where an animal already drawn covers it (a ewe standing just behind the
  gate) and one near the cat on the wall.
- **Size:** 1.15x the life scale: about 31 x 19 px on the gate, and 19 x 12 px on the garden wall.
- **Look:** black, with a dull blue-grey sheen on the back and the crown.
- **Code:** `fauna.crows`, `fauna.crow_spot`, `fauna.draw_crow`, `events.Schedule.crows_at`.

### The cat

It is unchanged in look. It now sits on the upper wall's topmost coping stone (`occl_top`) rather than
27 px above the wall's foot, and it is hidden like the other animals.

## Depth order

Animals are drawn in `front()`, after the near scenery. Two things decide what hides them.

**Standing scenery.** While `hill()` draws the near scenery, an `Occluders` recorder is listening. A `Tee`
hands the hill's albedo layer exactly the calls it would have had, and also draws each shape into the
recorder's current group. There are 24 groups. Each is a coverage mask (antialiased, cropped to its bounding
box) with the frame row of its foot in every column:
- the two field walls (`wall-upper`, `wall-lower`);
- the five garden wall stretches (named as in `hillside.WALLS`, built as far as their `WallStage`);
- the wicket;
- the shed;
- three hives;
- the latch post, the gate leaf (rails, stiles, brace and hinge straps), the hinge post, and the grass grown
  up round the gate;
- two outcrops and six gorse bushes.

Ground stains (the shadows under rocks and bushes, drawn with alpha < 0.9) are not recorded, and nor is
anything flat (heather, flowers, puddles, the beds). The groups are recorded once per day and frame size in a
process (`fauna.OCC`, key `(W, H, date, wall stages)`). The first keyframe of a run records them, and every
minute's `front()` reuses them.

**Animals already drawn.** Each animal's layer goes in through `life_put(L, depth, xc)`. A thing hides the
animal where its mask covers it if the thing's foot, at the animal's own column `xc`, is lower in the frame
than the animal's feet `depth`, meaning nearer. Once composited, a solid animal's layer (with its
coverage) joins the list for the rest of the frame. So a fox behind a ewe is hidden by her whatever the
drawing order. Shadows are composited the same way but hide nothing.

Each thing is nearer or farther as a whole, judged under the animal's column. A wall that slopes across the
screen therefore never cuts an animal in two. An animal that perches stands in front of its perch: its depth
is the perch's foot plus 1.5 px.

When `front()` runs in a process that never drew the near scenery (a test, a preview built without it),
`occluders()` draws the standing things again on their own: the hillside's exactly (same generators), and
the field walls with the same outline but stones from a fresh generator. In production every minute's frame
follows its keyframe in the same worker, so the recorded masks are always used.

## Probes

1. **Tests** (on `3dcf150`). `$PY -m unittest discover -s tests` -> `Ran 64 tests in 28.092s OK` (52
   before, plus 12 in `tests/test_fauna.py`). **PASS.** `$PY tests/test_shore_reference.py` (its tests are
   module functions, which `unittest discover` does not collect) -> `4/4 passed`, including
   `test_reference_build_is_deterministic_and_leaves_the_tree_clean`. **PASS.** `tests/test_fauna.py`'s 12:
   - the fox is shy;
   - hares come out at dawn and dusk, and box in March and April only;
   - crows come out by day;
   - sheep keep to their field and out of the garden;
   - reference mode has no animals;
   - recording leaves the near scenery unchanged;
   - the redrawn hillside masks equal the recorded ones;
   - behind the gate an animal is hidden and shows between the rails, and in front it is not hidden;
   - the garden wall hides what is inside it;
   - animals hide the ones behind them;
   - crows stand on the coping;
   - drawing is deterministic.

   `tests/test_shore_reference.py` watches `fox`, `hares` and `crows` too, with four new cases:
   - crows at 2027-03-17 10:00;
   - hares at 17:40;
   - the fox at 2027-03-05 18:59;
   - boxing hares at 06:58.

   A bats case for `critters` (2027-07-06 21:30) replaces the rabbits'. One case already failed on `main`:
   2027-01-12 17:15 for `high_air` had no flight in range. It was moved to 18:40, where a night flight's lights
   are in view.
2. **Determinism** (on `3dcf150`). `listening_point.py OUT --date 2027-03-24 --minutes 1058-1063 --scale 0.75
   --jobs 1 --weather fair --quality 90`, rendered twice in a row. The six frames have the fox trotting
   and mousing, a hare sitting up and then loping away from it, two crows on the garden wall, and the ewes.
   `cmp` on every frame -> `6 frames compared with cmp, 0 differ` (1740.jpg `438dde204442193e2fb1c79cfe9a8f5b`).
   **PASS.** Earlier, the same with 17:38-17:45 at `--scale 0.375`: 8 frames, 0 differ.
3. **Shore reference** (on `3dcf150`, and before on `8845eab`). `$PY tools/shore_reference.py out/animals-r2
   --reference r2` -> `reference r2 written to .../out/animals-r2: digest
   7cbee1f442afce967826b8e6f6aaffddd8921391b138a487f359b4d9024d35fa`, exactly the published r2. **PASS.** Reference mode draws no animals (front() skips them, and `_hold_still`
   empties their schedules), and the recorder is off in reference frames.
4. **Near scenery unchanged.** `Frame.foreground()` at `--scale 0.375` on `main` and on this branch:
   - 2027-03-24 12:00 fair;
   - 2027-04-06 13:00 synthetic (wet);
   - 2027-01-27 11:00 synthetic (snow).

   Colour and coverage arrays are identical in all three (`np.array_equal`). **PASS.**
5. **Cost** (scratchpad `cost.py`). `frame_image()` CPU over 10 consecutive minutes (2027-03-24 17:35-17:44,
   fair, `--scale 0.75`, keyframe step 10, so 6 `foreground()` calls). One process per run, `main` and this
   branch in turn, on a shared machine:

   | run | main | branch | ratio |
   |---|---|---|---|
   | 1 (main first, load 8) | 39.56 s | 32.57 s | 0.82 |
   | 2 (branch first) | 33.93 s | 34.34 s | 1.01 |
   | 3 (load rose to 13) | 43.61 s | 48.51 s | 1.11 |
   | sum | 117.10 s | 115.42 s | **0.99** |

   Per call, `front()` took 0.22-0.28 s on main and 0.12-0.19 s on the branch.

   Measured directly in one process (`cost2.py`):
   - Recording the occluders costs +0.14 s CPU, once per day and frame size in a process: a warm
     `foreground()` takes 2.56 s while recording and 2.42 s with them recorded already.
   - Over 18 minutes with the animals out (the boxing hares, the fox with hares and crows, crows on the gate),
     per minute: `sheep` 29 ms, `hares` 4 ms, `fox` 2 ms, `crows` 1 ms. The whole `front()` was 134 ms.

   Against about 3.4 s a frame, the new work is about 1%. **PASS** (well under the 1.15 limit).

## Look test

Folder: `out/look/v3/animals/` of the main checkout. `pair-<scene>.jpg` is the whole frame at Evan's
1440 x 900, with `main` on top and this branch below. `crop-<scene>.jpg` is the animals at native size,
`main` above this branch. Each was rendered with
`listening_point.py --scale 0.75 --jobs 1 --quality 90`, one at a time.

Nine scenes. The crops' boxes are given in native pixels (x0, y0, x1, y1).

| scene | when | what to look at |
|---|---|---|
| `sheep-midday` | 2027-03-24 12:00 fair; crop (0, 1150, 1100, 1650) | The ewes and lambs: main's small grey ovals against blackface ewes in white fleece. The ewe by the upper wall stands on it in main, and behind it in the branch, legs hidden. A crow walks the grass beside her. |
| `behind-gate-sheep` | 2027-03-02 12:50 fair; (0, 1200, 1300, 1600) | Depth fix: a ewe in the corner behind the open gate shows her legs behind its rails (main draws her over them). Two crows sit on the upper wall's coping at the far left. Crows that would sit on the gate's bar leave it, because the ewe stands there. |
| `crows-gate-garden` | 2027-03-24 10:30 fair; (200, 1100, 800, 1550) | Two crows on the open gate's top bar, and one on the garden's right-wall coping by the back corner. |
| `hares-boxing` | 2027-03-24 17:12 fair (sunset 18:01); (0, 1400, 800, 1800) | Two hares boxing on the path's edge, low left; one sitting up on the path. |
| `fox-dusk` | 2027-03-24 17:40 fair; (0, 1150, 900, 1700) | The fox trotting across the lower field. One hare sits up watching it and the other lopes off. The ewes are heading for the fold, and a crow is on the garden's front wall. |
| `behind-gate-fox` | 2027-03-30 06:55 fair (sun 4 degrees); (150, 1250, 700, 1650) | Depth fix: the fox sitting in the corner behind the open gate, seen between the rails, and a hare sitting up watching it. The dawn ewes are pale shapes (Known issues). |
| `behind-garden-fox` | 2027-01-25 07:54 fair; (0, 1000, 800, 1350) | Depth fix: the fox on the skyline behind the garden's back wall, left of the hives. The wall hides its legs. |
| `night-moon` | 2027-02-18 18:33 fair, moon 93%; (0, 1050, 1100, 1650) | The flock lying folded behind the upper wall in the moonlight (main lays them on top of it). The fox behind the garden's back wall by the hives. |
| `snow` | 2027-01-27 11:00 synthetic; (0, 1150, 1300, 1650) | Ewes in snow. Those just behind the walls have their legs hidden; main stands them on the coping. One ewe beyond the lower wall still seems to stand on it (Known issues). |

Development renders (`--scale 0.375`, this branch only) and the sprite sheets are in `out/animals-dev/` of the
main checkout. The raw look-test frames are in `out/animals-dev/look/{main,branch}-<scene>/`.

## Known issues

- **Scale against the walls.** The field walls and the gate are drawn at about half the tower's scale
  (part 1), and the animals sit between the two. A ewe stands about twice a wall's height, and a crow on the
  gate's top bar is large against the gate.
- **Just beyond a wall.** We look steeply down on the field, so an animal about one wall-height behind a
  wall has its feet on the coping's line and can seem to stand on it. Ewes in the upper field are kept close
  enough that the wall hides their legs. Hares, and a fox passing, can still be seen that way now and then.
- **Dawn and dusk.** The animals are lit by the scene's own low light, so at dawn the ewes are pale shapes
  with their legs and faces lost in the dark grass, and a hare at dusk is small and dark. At night the fox
  is a dark shape by moonlight.
- **Movement is minute by minute.** The trotting fox moves about 70 px between frames, and a hare's lope
  takes two frames. The helper cross-fades them. Ewes turn (side, toward you, away) as their drift changes
  direction.
- **Masks without the near scenery.** In a process that never drew the hill, the field walls' masks are
  redrawn with other stones, so a perched crow or the cat can sit 1-3 px off the drawn coping. Production
  frames always use the recorded masks.
- **Not occluded:** the cat's eye glints (glows, as before), and the bats, swallows and butterflies in
  `critters()`, which fly.
- Hares sometimes sit on the path.
- **Tests outside this part.** `tests/test_shore_render.py` fails 5 of 7 with `no spot passes for
  2027-03-17-cairn` (and `-18-`), on `main` too (checked with
  `test_resting_things_are_hidden_by_objects_standing_nearer`, the same reference set). Its synthetic cairn
  finds no spot that passes against r2. Not touched here.

## Status

**Done on `v3/animals`** (2026-11-01 evening), from `main` `5b1b55e`:
- `8845eab`: the code and tests;
- `3dcf150`: refinements and this doc's draft;
- the commit after it: this doc completed.

Probes 1-5 pass (above) and the look test is rendered, in `out/look/v3/animals/`. The branch is not merged
and not installed: the lead merges and installs.

Rendering during this part was shared with a game. The first iterations waited on a memory gate
(`kern.memorystatus_level` of at least 40, or 45 at `--scale 0.75`), until Evan said to go ahead. Every render was
one at a time, `--jobs 1`, under `nice -n 15`.

**Left for later:**
- A choice on the "just beyond a wall" look (Known issues), if Evan finds it reads wrong.
- The stale `test_shore_render.py` cairn spots, which belong to the shore work.
