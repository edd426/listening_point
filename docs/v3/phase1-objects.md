# v3 phase 1: the objects

Branch `v3/objects`. Goal (Evan, 2026-11-01): the tower, the tree, the bench and the lamp post looked
"soft and flat" at normal viewing distance; make them more defined, toward a detailed hand-drawn 2D
game background, without changing layout, colour or mood, and with every bit of light still coming
from the scene.

## What changed

All detail is albedo variation and surface normals that go through the existing `light()` /
`lit()`; nothing paints a highlight in a fixed direction. The few light-independent darkenings are
ambient occlusion (joints, recesses, undersides, the foot of a wall), which is what the sky light
cannot reach whatever the hour. Anything that never changes is built once per frame size and cached
(`functools.lru_cache`), so a minute only lights it.

### Tower (`tower.py`)

- **Masonry** (`wall_maps`): the same course layout as before (21 x 46 at full size, each course
  shifted). Each stone has its own tone (a few much darker or paler, a little warmer or cooler), a
  slight tilt, a pillowed face, slightly irregular edges and rounded corners, and a bevel down into a
  recessed mortar joint. The bevels are a height field turned into normals (`bump_normal`), so the
  top edge of each stone takes the sky and the underside of the one above does not, and at golden
  hour the west-facing bevels catch the low sun. About one stone in seven has lost a corner. Rain
  streaks run down from under the cornice, the window sills and the clock; the foot is damp, darker
  and greener, with moss in the joints and on the lowest stones, and pale lichen here and there;
  occlusion darkens the joints, the wall under the cornice and the last few courses at the ground.
- **Dome** (`dome_maps`): sixteen copper gores between raised standing seams, each gore in sheets
  lapped over the one below and staggered from gore to gore; every sheet its own shade of patina,
  with paler verdigris washed out from under the laps and along the seams; the skirt below the
  cornice turns into its shadow. The specular highlight now breaks on the seams. The cornice ring
  has a moulding profile (a lip that faces the sky, a fillet and a soffit that face down, dentils
  with side faces).
- **Door** (`door_maps`, drawn into the details layer with the new `Layer.blit`): six planks, each
  its own tone, grained along their length, bevelled into dark gaps, greyer and darker near the step,
  occluded under the arch. When the sun reaches the door's face (summer mornings and evenings), the
  jambs and arch, a stone deep, shade the side and top toward it. The strap hinges and nail heads
  have a sky-facing top and a darker underside.
- **Doorway and windows**: dressed jamb blocks (long and short) and nine voussoirs with a keystone,
  each stone its own tone in visible mortar; window heads with joints, a dark reveal round the
  glass, sills with a sky-facing top and a shadowed underside.
- Unchanged on purpose: the clock (still plain and legible), the LOOK CLOSER lintel, ivy, lantern,
  pot, plaque, downpipe, weathervane and telescope.

### Tree (`tree.py`)

- **Crown** (`leaf_set`): the leaves (same skeleton, same per-leaf days to unfold, turn and fall)
  are grouped into clumps by k-means over their positions and drawn a little closer to their clump's
  centre. Each leaf's normal blends its clump's sphere and the crown's ellipsoid (with a slight
  upward turn, as leaves face the sky), so a clump is lit on the side that faces the sun and the
  crown on the side that faces it. The crown shades its own far side and a clump its own
  (`shade` in `light()`), occlusion darkens the inside and the undersides, clumps share a tone and
  mostly a colour and a twig's leaves turn together, so autumn shows in patches. Small gaps let the
  sky through, more toward the edge, which they break up a little; the outline does not move or
  grow. With the sun behind the tree, light comes through the leaves at the crown's rim (as before)
  and faintly at the rims of the outer clumps. Lighting is one vectorised `light()` call per keyframe
  instead of one per leaf.
- **Trunk, roots and limbs** (`bark_maps`): drawn per pixel instead of as flat polygon strips. The
  trunk is swept row by row from the fork to the ground and flares into four root ridges at the
  foot; limbs thicker than 3 px (at full size) are capsules along the skeleton. All have furrowed
  bark (narrow furrows between plates, wandering, now and then bridged, running on from segment to
  segment) as relief and albedo, a little lichen, and a round normal, so the sunward side is the lit
  one. The crown shades the limbs inside it (by leaf cover) and the trunk below it once the sun is
  high enough to look over the crown (from the sun's altitude and the crown's reach), with dappling.
- Thin branches, twigs, snow on the branches and the nest are drawn as before (twigs are shaded
  inside a leafy crown).

### Bench and lamp (`props.py`, `bench()` and `lamp()` only)

- Bench: each back rail its own tone with faint grain, a sky-lit top edge and a darker underside;
  screw heads; the cast-iron ends with worn paler edges lit as each faces, feet and finials.
- Lamp: the post and plinth shaded in three faces (east, camera, west) so the sunward side is the
  light one; fluted plinth with a moulded top, collars, a ball-ended ladder bar; the lantern as three
  framed panes (the side ones turned away), a two-faced roof and finial; lit, the panes glow and the
  flame shows through the frame. Same extents as before (it stays clear of the shore crop).

### `core.py` (additive only)

- `bump_normal(nrm, h, k)`: tilt normals by a screen-space height field, projecting the screen axes
  onto the surface so slopes on a face seen edge-on are foreshortened.
- `Layer.blit(x, y, rgb, a)`: composite a supersampled per-pixel image into a vector layer, so a
  per-pixel surface can sit between vector details (the door, under its ironwork).

## Measurements

The reference command, `nice -n 10 $PY renderers/procedural/listening_point.py OUT --date 2026-11-01
--minutes 720-779 --scale 0.75 --jobs 1 --weather fair --quality 90` (60 frames, 7 keyframes), on the
M1 while another agent was rendering in parallel (load average 5 to 28), so the wall-clock figures
are noisy:

| run | load avg (1 min) at start | real | user CPU |
|---|---|---|---|
| baseline (main), first | 4.5 | 132 s | 124.3 s |
| after (`v3/objects`) | 13.2 | 146 s | 128.2 s |
| baseline (main), again right after | 8.8 | 187 s | 153.2 s |

Ratio after/baseline: 1.11 (real) and 1.03 (user CPU) against the first baseline, 0.78 and 0.84
against the second; within the 2.0 budget either way. The per-call costs, best of three in one
process (`Frame` at scale 0.75, 2026-11-01 12:00), are steadier:

| call | baseline | after | how often |
|---|---|---|---|
| `tower()` | 60 ms | 40 ms | every minute |
| `tree()` | 712 ms | 175 ms | every keyframe (10 min, twice when clouds are about) |
| `bench()` | 0.9 ms | 2.2 ms | every keyframe |
| `lamp()` | 0.7 ms | 1.3 ms | every keyframe |
| `foreground()` | 2.48 s | 2.31 s | every keyframe |

One-off cost per process (cached per frame size, at 0.75): `wall_maps` 70 ms, `dome_maps` 9 ms,
`door_maps` 5 ms, `leaf_set` 124 ms, `bark_maps` 178 ms, `twig_set` 3 ms: about 0.39 s. The tree got
cheaper because its lighting is now one vectorised call per keyframe instead of one per leaf.

## Probes

Run on the final code (commit `76d7b54`, re-run after the last tree tweak):

1. `$PY -m unittest discover -s tests`: `Ran 45 tests in 5.554s` / `OK`.
2. Determinism: 2026-11-01 12:00 (`--weather fair --scale 0.75 --quality 90`) rendered twice into
   two directories: `cmp` reports no difference (`BYTE-IDENTICAL`, both md5
   `3aca1b12f2c07d5102bba9b11e4e006d`).
3. Shore strip: `tools/shore_reference.py /tmp/ref-objects-final --reference r1` (digest
   `37e07b33a34004069bc784f2ee7b8fb4b3293dd96ccc6185c34d3625354f821c`) against the published
   `shore/reference/r1`: `surfaces.json`, `keepout.png`, `palette.json`, `conditions.json`
   byte-identical; `noon.png`, `golden.png`, `night.png`, `fog.png`: 0 differing pixels each.
4. Render time: after/baseline 1.11 real, 1.03 user CPU (first baseline); at most 2.0 required.
   (Timed at `d836304`; the last commit changes two constants of the tree and no cost.)

## Look tests

In `/private/tmp/claude-501/-Users-eddelord-Documents-Projects-cozy-cabin-claude/b85a93cd-3703-4aff-b84b-d9b69db72a54/scratchpad/v3/objects/` (outside the repository):

- `before/<name>.jpg`, `after/<name>.jpg`: full frames (2880 x 1800) for noon (2026-11-01 12:00
  fair), golden (16:00 fair), night (19:30 fair), fog (09:00 fog), summer (2027-06-21 12:00 fair)
  and winter (2027-01-15 12:00 fair); plus three fully sunny minutes the six do not cover
  (2027-06-21 11:30 and 18:50, 2027-04-25 12:00: at the summer test minute the sun is behind a
  cloud, `sun_vis` 0.15).
- `crops/<name>-tower-{before,after}.png` (x 700-1000, y 600-1220) and
  `crops/<name>-tree-{before,after}.png` (x 1050-1700, y 580-1350), native resolution.
- `half/<name>-{before,after}.jpg`: the whole frame at 1440 x 900 (point size).
- `before-after.jpg`: contact sheet of the six (tower before/after, tree before/after, native);
  `before-after-sunny.jpg`: the same for the three sunny minutes.

Checks made while tuning: the wall's mean brightness between the windows and the lintel is within
1.5% of before in all eight looks and the dome's within 3%; the crown's extents moved by 1-5 px and
its foliage cover in the crown box fell from 0.51 to 0.49-0.50 (more sky through it); foliage
median brightness is within 7% of before in autumn and at golden hour, about 10% lower in full
summer sun (more of the crown is in its own shade).

## Known issues

- **Timing is noisy**: another agent was rendering on the same machine; see the table. The
  per-call figures are the reliable comparison.
- **Summer canopy a little darker** in full sun (median about 10% below before): the crown now
  shades its own lower and far side. Lifting the occlusion floor further flattens the clumps again.
- **Clumps can look a little regular ("bubbly")** in strong summer sun, as k-means makes clumps of
  similar size. A size spread per clump would help if Evan finds it too even.
- **Twig ends moved slightly**: the twigs now have their own seeded generator (`twig_set`, seed 9)
  instead of continuing the leaves' stream; the leaves themselves keep their seed (8), their days to
  unfold, turn and fall and their angle, but are drawn 8% closer to their clump's centre, and
  their colour index and turning day are now partly shared per clump.
- **The green band under the cornice** (the lower half of the dome showing below the cornice ring)
  is the existing layout; it is kept, now darkened as the occluded underside of the dome.
- **Bench grain is invisible at point size**; what reads there is the rails' lit top edges and the
  iron's worn edges. The lamp's panes read at native size and as a framed lantern at night.
- **The door's reveal shadow** only acts when the sun is north of the wall's normal (summer
  mornings and evenings); checked at 2027-06-21 18:50, where it shades the right side of the door.
- **Untouched**: `land.py`, `shore.py`, `sea.py`, the pier and the boats, and in `props.py`
  everything but `bench()` and `lamp()`. `core.py` only gained `bump_normal()` and `Layer.blit()`.
