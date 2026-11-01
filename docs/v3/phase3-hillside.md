# v3 phase 3, part 1: the hillside's built things and land detail

Branch `v3/hillside`, from `main` `4192c35`. Evan named the left hillside as one of the places that
feel empty and picked, for this part: a small garden with beds, a shed, beehives, a gate, more dry-stone
wall; rock outcrops, gorse and heather, wildflower patches, and puddles after rain. No creatures (part 2
adds a fox, hares, crows and bigger sheep, using what is placed here), no people.

## What was added, and where

New module `renderers/procedural/hillside.py` (`HillsideMixin`, added to `Frame`); hooks in
`renderers/procedural/land.py`'s `hill()`. Everything is static near scenery, drawn in `foreground()`
into the hill's own albedo (`A`) and normal (`N`) layers, so it is lit per pixel by the scene's sun, moon,
sky and lamp pools exactly as the grass, stones and walls are; the tower's and tree's shadows fall
across it; snow settles on whatever faces up (roofs, wall tops, beds, rock tops, bush tops).

Coordinates are pixels of the production frame (`--scale 0.75`, 2880 x 1800), x from the left, y from
the top. "foot" is where a thing meets the ground; "^n" is how many pixels its top stands above that.

**The walled kitchen garden** (upper left, below the crest, above the sheep's grazing area, which starts
at y 1245):
- Ground quadrilateral, front-left / front-right / back-left / back-right: (86, 1238), (490, 1249),
  (184, 1154), (564, 1163). `hs_g(a, b, h)` maps garden coordinates (a across 0..1, b back 0..1,
  h metres up) to the frame.
- A new dry-stone wall round it (the field walls' stonework, its own stones, a quarter taller), in five
  stretches (`WALLS`), foot -> coping height:
  - `garden-front`: (86, 1238)^18 ... (409, 1247)^19
  - `garden-front-east`: (449, 1248)^19 ... (490, 1249)^19
  - `garden-left`: (86, 1238)^18 ... (152, 1182)^16
  - `garden-right`: (490, 1249)^19 ... (564, 1163)^15
  - `garden-back`: (291, 1156)^14 ... (564, 1163)^15
- A small wooden wicket gate, shut, in the front wall between (409, 1247) and (449, 1248).
- Four raised beds, front to back: cabbages (kale over the winter), potatoes, salads (lettuce and
  carrots), runner beans on hazel wigwams (2 m poles, about 60 px).
- The shed, in the back-left corner: boarded timber, a slate roof, a door painted the tower dome's
  green, a four-pane window, a water butt at its corner. Front base (151, 1183) to (264, 1185), eaves
  at y 1125, ridge from (167, 1090) to (279, 1092); you see its front and its west gable.
- Three WBC beehives along the back, feet at (405, 1175), (451, 1176), (497, 1177); 18-19 px wide,
  about 37 px tall with four boxes in summer, 25 px with two in winter.

**The field gate** (in the gap the path goes through between the two field walls): squared stone
gateposts at the walls' ends, hinge post foot (426, 1462)^30, latch post foot (564, 1487)^32; a
five-barred wooden gate hung on the hinge post, standing open 108 degrees, swung back toward you into
the lower field: its leaf runs from (426, 1462) to (313, 1491), 24 px tall, so it lies in the grass in
front of the upper wall's end, clear of the path.

**The field walls (phase 1, unchanged), for perching:** foot -> coping height, sampled along each:
- upper wall: (-58, 1336)^19, (46, 1357)^20, (148, 1383)^21, (246, 1409)^22, (339, 1436)^23, (426, 1462)^24
- lower wall: (564, 1487)^25, (656, 1511)^26, (744, 1544)^28, (828, 1587)^29, (907, 1642)^32, (979, 1710)^35

**Land detail:**
- Rock outcrops (a crag of three boulders, a low shelf in front, loose stones, cracks, lichen, turf
  round the foot): foot centre (115, 1642), 153 px wide, top about 61 px up; and (1129, 1516),
  102 px wide, top about 40 px up.
- Gorse (foot centre, width x height): (245, 1600) 92 x 59, (29, 1678) 90 x 60, (1244, 1492) 67 x 42,
  (35, 1265) 51 x 32, (645, 1208) 42 x 26, (585, 1183) 29 x 18.
- Heather mats (centre, half width x half depth): (58, 1584) 60 x 13, (179, 1724) 52 x 12,
  (1037, 1534) 52 x 12, (1204, 1544) 39 x 8, (680, 1228) 18 x 3.
- Wildflower patches (centre, half width x half depth): (749, 1629) 90 x 22, (950, 1440) 52 x 10,
  (173, 1503) 58 x 11, (288, 1274) 47 x 3.
- Puddles, only on wet ground (largest radius when wettest): on the path at (382, 1736) 32,
  (490, 1558) 27, (457, 1496) 21, (628, 1408) 15, (716, 1277) 10, all in the ruts; and in the gateway
  at (490, 1501) 24.

Everything new is drawn left of x 1300 and casts no shadow past x 1440; the shore kit's crop starts at x 1600 (see Probes).

## The year (all from `season.py` and the date, or the stages below)

- **Garden** (`garden_stage(doy)`): its year starts at the end of February. Beds dug bed by bed from
  late February to the end of March (fresh dark tilth); potatoes, salads, beans, then cabbages sown or
  planted April to mid June; growth to the end of July (potato flowers and scarlet bean flowers in high
  summer); ripening to harvest colours August to early October; cleared salads first, then potatoes,
  then the beans with their poles, mid August to early November; the cleared beds dug over rough for
  the winter, October to late November. The cabbage bed stands through the winter as kale and is dug
  last. A garden with nothing done yet is drawn exactly as one whose year is over, so the turn of the
  garden's year (doy 49 -> 50) shows no jump (`tests/test_hillside.py`).
- **Hives**: two boxes in winter, three from mid March, four (the honey super) from mid May to
  August; from mid November to early March wrapped in tarred felt with a stone on the roof and the
  entrance narrowed. No bees (creatures are part 2's).
- **Gorse**: a little yellow all year, a blaze from March to May, a thinner flush in the autumn
  (`gorse_bloom`).
- **Heather**: dark wiry green; paler new tips in early summer; purple late July to September
  (`heather_bloom`); rusty dead flowers from October into the winter.
- **Wildflower patches**: whatever `season.FLOWERS` has in bloom, denser than the scattered drifts.
- **Puddles**: grow with `wx.wet` from 0.3 to 0.9; hidden under lying snow; frozen (pale, lit like the
  ground) in a hard frost below 0.5 C.
- **Snow, frost, wet**: through the hill's own rules (snow on up-facing normals; everything darkens a
  little when wet).

## The stage interface for phase 5

Two dataclasses in `hillside.py`; phase 5 sets them on the `Day`, and the hillside draws whatever they
say. Phase 3 leaves them unset, so the date alone decides.

```python
from hillside import GardenStage, WallStage, WALLS

day.garden_stage = GardenStage(dug=0.6, sown=0.2, growth=0.1, ripe=0.0, cleared=0.0, rough=0.0)
day.wall_stages = {"garden-front": WallStage(courses=2.5), "garden-right": WallStage(0.0)}
```

- `GardenStage` fields are 0..1: `dug` (the four beds in turn, each from left to right), `sown`
  (potatoes, salads, beans, cabbages in turn, each from the left), `growth`, `ripe`, `cleared`
  (salads, potatoes, beans in turn, from the left; the cabbage bed is never cleared, it stands as
  kale), `rough` (the cleared beds dug over for the winter). `garden_stage(doy)` is phase 3's mapping
  from the date.
- `WallStage.courses` is 0..4 per stretch: three courses of stones, then the coping. A fraction lays
  that course along the stretch from its start, so a wall rising stone by stone is `courses` creeping
  up. A stretch at 0 draws nothing and casts nothing. Stretch names are `WALLS`; unset stretches are
  finished.
- Stability: every random draw is made whatever the stage and only what the stage says is shown, so
  clods, plants and stones stay where they are from one day to the next as the stage moves on (tested:
  the undug end of the kale bed is identical at 85% and 90% dug). Each wall stretch has its own
  generator, seeded by its name's place in `WALLS`.
- `land.py`'s `wall_body(..., courses=None, height=1.0, X=None)` is the field walls' stonework split
  out of `wall()`, with the stage and a height; the field walls call it unchanged (same draws, same
  pixels).

## How it is drawn

- `HillsideMixin.hillside(A, N, X, WM, persp)` is called in `hill()` after the crest blades, so none of
  the hill's own generators (`r`, which places the shore's stones, and `r2`) make a single draw more or
  less: everything new draws from its own generators (300-430).
- A new layer `HSL` (`X` inside hillside.py) over the hill's left 46%: blue marks built things, where the
  grass's tuft shading (occlusion, ambient, the blade lean under snow) is switched off, so a shed wall
  or a rock top isn't patterned like turf; red and green are the puddles' water and wet rims.
- Shadows: built things, bushes and the outcrops cast shadows on the grass from wherever the sun (or a
  bright moon) stands, with the walls' projection; the gate's rails and the bean poles cast thin bar
  shadows; things don't fall in their own shadow (they are added to the walls' mask `WM`), and the grass
  darkens at the foot of the new walls and the shed. The walls' shadow and mask layers widened from
  40% to 46% of the frame to take the outcrop and gorse on the right of the lower wall.
- Puddles mirror the sky as `sky.py` paints it, at the angle you look down at the water, greyed under
  cloud and a little by mud, brighter toward the sun, with the far bank's dark reflection along the top.
- Scale: built things use about 72 px per metre at a perspective of 1 on a 3840-wide frame (the tower's
  own scale; the shed is about 3.7 m long and 2.9 m to the ridge). The gate is sized to the field walls
  it hangs between (which are drawn lower than that scale), not to the shed.

## Probes

1. **Tests**: `$PY -m unittest discover -s tests` -> `Ran 52 tests in 15.5s OK` (45 before, plus
   `tests/test_hillside.py`'s 7: the garden's year wraps; nothing-done draws exactly as year-over; the
   seasons differ; the stages keep plants in place; a wall rises by stage and a finished stage is the
   default; nothing drawn or cast reaches the shore crop in three seasons and three hours; drawing is
   deterministic). **PASS**
2. **Determinism**: 2026-11-01 12:00, `--scale 0.75 --weather fair --quality 92`, rendered twice into
   two folders: `cmp` silent, both `5477532088f0b6b3f4f575facfc25e5c`. **PASS**
3. **Shore reference**: `$PY tools/shore_reference.py OUT --reference r2` from this tree ->
   `reference r2 written to ...: digest 7cbee1f442afce967826b8e6f6aaffddd8921391b138a487f359b4d9024d35fa`,
   exactly the published r2. **PASS** (no r3 needed)
4. **Render cost**: see Timing.

## Timing

Probe 4's command, `nice -n 10 $PY renderers/procedural/listening_point.py OUT --date 2026-11-01
--minutes 720-779 --scale 0.75 --jobs 1 --weather fair --quality 90`, main's checkout and this branch
(`2440965`) alternating, three pairs, on a shared machine (other render agents running):

| pair | main | hillside | ratio | load (1-min) before -> after the pair |
|---|---|---|---|---|
| 1 | 213 s | 440 s | 2.07 | 6.5 -> 11.2 |
| 2 | 427 s | 373 s | 0.87 | 11.2 -> 10.2 |
| 3 | 529 s | 463 s | 0.88 | 10.2 -> 10.4 (37 between) |
| sum | 1169 s | 1275 s | **1.09** | |

The noise (main alone ran 213 s to 529 s) is far larger than the difference. Pair 1's main run had the
quietest machine of all six; from pair 2 on, the load was steady and the branch was faster both times.
A direct measure with less noise: `Frame.foreground()` CPU time, four keyframes each, same process,
main 3.34 s against 3.67 s mean (+0.33 s, +10%); a 60-minute run makes about 14 foreground calls
(7 keyframes, sun on and off), so about +5 s on a run of about 3 minutes of CPU: an expected ratio of
about 1.03. **Probe 4: passes on the sum (1.09 <= 1.15) and on the CPU estimate; pair 1 alone does not.
Re-time on a quiet machine before installing.**

## Look test

Session scratchpad `v3/hillside/`: full frames `<n>-<scene>-a-before.jpg` (main) and `-b-after.jpg`
(this branch), and `<n>-<scene>-crop.png` (the hillside, x 0-1300, y 1050-1800, at native size: main
on top, this branch below).

**Not rendered yet** (paused before it started). The script is ready:
`scratchpad/hs/tools/look.sh` renders the ten scenes (spring 2027-04-08, summer 2027-07-05, late August
2027-08-25, autumn 2026-10-08, winter snow 2027-01-27 11:00 synthetic, wet 2027-04-06 synthetic,
2026-11-01 noon/golden 16:00/night 21:00 fair and fog 10:00) with main and with this branch, and writes
the pairs and crops into `v3/hillside/`. Development renders of every one of those scenes (this branch
only) are in `scratchpad/hs/it/` (`v*-<scene>-full.jpg`, `-half.png`, `-crop.png`, and `z*` zooms).

## Known issues

- **Depth with creatures.** Sheep, the cat and the like are drawn in `front()`, over all the near
  scenery. A sheep standing just behind the open gate (its feet above y 1462-1491 between x 313 and 426)
  would be drawn over the gate instead of behind it; likewise anything behind the garden's front wall.
  Part 2 should hide animals behind the gate leaf and the garden walls where they stand behind them
  (the leaf and wall lines above give the geometry).
- **Perspective is stylised.** The garden and its contents use a simple oblique view (receding edges at
  about 40 degrees, showing the right-hand sides), not the panorama's own projection, which at this side
  of the frame would show the buildings almost side-on. It reads as a hand-drawn game background.
- **Scale.** The field walls (phase 1) are drawn about half the height the tower's scale would give
  them; the garden's walls follow the field walls (a quarter taller), the shed follows the tower. So the
  garden walls look low against the shed.
- **No bees, no gardener**; the shed has no lit window at night (no one is in it).
- Bean wigwams stand in front of the shed's window in summer.
- Rime (frost) does not whiten the new things' surfaces (the hill's rime skips anything in the overlay,
  as it does the phase-1 stones); snow does.
- The far gorse bushes near the crest are small (28-50 px wide); they register as yellow dots in
  spring.
- Puddles are fixed places (six), not computed from the ground's hollows; they appear and grow
  together.
- Cost: `foreground()` is about 0.3 s CPU (10%) dearer per call; see Timing for the whole run.

## Status at pause (2026-11-01, Mac restart for a macOS update)

Paused at the lead's request. Branch `v3/hillside`; the code is committed in `2440965`, this doc in the
commit after it.

**Built and working** (all in `hillside.py`, hooks in `land.py`): the walled kitchen garden with four
beds whose soil and crops follow the year, the shed, three hives (boxes by season, wrapped in winter),
the new dry-stone wall in five stretches with a stage, the wicket gate, the open field gate with its two
stone posts, two rock outcrops, six gorse bushes, five heather mats, four wildflower patches, six
puddles that mirror the sky after rain. Coordinates: "What was added, and where" above (frame pixels at
scale 0.75). The phase-5 stage interface (`GardenStage`, `WallStage`, set on the `Day`) is built and
tested.

**Probes run:**
1. Tests: `Ran 52 tests ... OK`. PASS.
2. Determinism: 2026-11-01 12:00 twice, `cmp` identical (`5477532088f0b6b3f4f575facfc25e5c`). PASS.
3. Shore reference r2 from this tree: digest `7cbee1f442afce967826b8e6f6aaffddd8921391b138a487f359b4d9024d35fa`
   (twice, the second after the last change to anything right of the garden). PASS.
4. Timing: sum ratio 1.09 over three noisy pairs (one pair 2.07, two 0.87-0.88); CPU estimate about
   1.03. Pass on the sum, but re-time on a quieter machine.

Probes 1-3 were run on the code as committed except the last gorse size change (three far bushes made
larger, all left of x 650); the tests (probe 1) were re-run after it, probes 2 and 3 were not.

**Left to do:**
- Re-run probes 2 and 3 on `2440965` (expected unchanged: the change is far from the shore crop, and the
  tests' layout check passed).
- The look test: run `look.sh` (about 20 renders; 10-15 minutes on a quiet machine) and look at every
  pair at full and half size.
- A small fix not yet made: the shed's cast shadow (`"box"` caster in `land.py`) pairs the ridge's top
  points with the front corners' ground points, so the ridge's part of the shadow is anchored at the
  front and a little too long. Pair each top with its own ground point (`g(a, bm)` for the ridge).
- Re-time (probe 4) on a quiet machine, ideally three pairs.
- Merge, install, and the scratchpad look-test images for Evan (his standing go-ahead applies).

**Open problems:** see Known issues; the main one for part 2 is depth: animals drawn in `front()` go over
the gate and the garden walls even when they stand behind them.

## Pickup after the restart (2026-11-01, evening)

- **Shed shadow fixed** (`7afbae2`): each top corner of the `"box"` caster now carries the ground point
  under it, so the ridge's shadow starts under the ridge, not at the front corners.
- **Merged with `main`** (clouds `8b07231`, air `3a971cb`); the only conflict was the `Frame` mixin list
  (`HillsideMixin` and `AirMixin` both kept). Head `714817b`.
- **Probes on `714817b`:** 1 tests `Ran 52 tests ... OK`; 2 determinism, 13 frames (2026-11-01 12:00-12:04
  fair, 2027-04-06 13:00-13:03 synthetic, 2027-01-27 11:00-11:03 synthetic) rendered twice, 0 differ;
  3 r2 digest `7cbee1f4…`. All PASS. Probe 4 not re-timed: the Mac was shared with a game and swapping,
  so a timing would mean nothing; the earlier 1.03-1.09 stands.
- **Look test**, main (with clouds and air) against this branch at `--scale 0.75`, the ten scenes of
  `look.sh`: hillside crops in `out/look/v3/hillside/` of the main checkout (`crop-*`, `wl-*`; top is
  main, bottom the branch). Reviewed: garden, gate, gorse and heather read as drawn scenery, restrained;
  the shed's shadow sits right. For Evan to judge, as before: the puddles on the path read as pale ovals
  in the wet scene (2027-04-06); snow-covered gorse reads as grey-blue mounds (2027-01-27); the
  outcrops are faceted grey stones that may read slightly CG up close.
