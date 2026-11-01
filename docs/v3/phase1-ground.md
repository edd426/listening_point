# v3 phase 1: the ground

Branch `v3/ground`. Goal (Evan, 2026-11-01): the grass hillside, the path and the dry-stone walls
looked "soft and flat"; make them "more defined", toward a detailed hand-drawn 2D game background,
without changing the layout, the palette or the mood, and with every bit of detail lit by the
scene's own sun, moon and sky.

## What changed

All of it is in `renderers/procedural/land.py` (the hill) and a new `renderers/procedural/ground.py`
(the ground's per-pixel fields). `core.py` is untouched.

**ground.py** builds, once per process and per frame size, a set of float16 fields over the whole
hill (MEMORY at the 2880x1800 frame). They don't depend on the date or the
minute, so the same ground is under every frame and every day, like the rest of the layout.

- *Tufts.* A jittered lattice laid on the ground in the hill's perspective (`persp`, the same scale
  the hill already used), so tufts are bigger and further apart toward the bottom of the frame.
  Each tuft is a fan of 3-6 pointed blades, narrow at the foot, the middle blades tallest. The
  fields record coverage, height-in-tuft (0 at the foot, 1 at the tips), which way the blade
  leans, a per-tuft tone, and the blade stripes. Nearer tufts hide the ones behind.
- *Clumps.* Tufts gather into patches (band-limited noise in ground coordinates) with shorter,
  open grass between, and stand taller in the middle of a clump, so the texture reads as shapes,
  not as even grain. A blurred coverage field (`dense`) says how crowded they are.
- *Swathes and hummocks.* A big, soft noise stretched along the contours gives lighter and darker
  bands that follow the slope; a hummock height field (sampled in ground coordinates, its slope
  used as a normal) gives gentle mounds and hollows that the sun lights from wherever it is.
- *The path.* Per pixel: across (-1..1) and along (0..1) coordinates of the existing ribbon
  (`LandMixin.ribbon`, same route, same width), from a distance transform of its centre line. From
  them: a ragged edge (noise along each side), a worn lighter middle, darker verges with green
  creeping in, and a pair of shallow ruts that come and go along the path (albedo and a normal
  tilt). The trail to the bench is worn grass: fewer tufts, a little lighter and yellower.

**land.py** turns the fields into albedo, normals and occlusion in the hill's existing strip pass:

- Grass: open grass keeps the old albedo (lifted 18% for what the tufts' feet take back); between
  crowded tufts it is darker; tufts run from a darker foot to a light tip mixed with the season's
  own tuft colour, a few straw-coloured (more in winter and in a dry summer). Normals: each blade
  leans out to its side; hummocks and ruts tilt the ground.
- Light: the feet of tufts and the hollows between them get less sky (an ambient multiplier) and
  less sun (folded into the frame's shade mask); tips get full light. So sunlit grass is crisp and
  overcast or foggy grass soft, by itself. Nothing has a painted highlight direction.
- Path: gravel and pebbles are little domes, greyer than the soil, a lit top and a face toward
  the viewer, in a soft contact shadow; about 70 flat stones are set in the path (`rock()`,
  flattened); tufts stop at the path's edge and overhang it a little; none in the trodden middle.
- Walls: three courses (big footings to small stones) with per-stone shade, some lichen and moss,
  a lit top edge per stone and dark joints, under a row of coping stones set on edge, each with a
  lit top. Faces are battered back a little so they take sky light when backlit (the sun is behind
  them most of the winter). The walls now cast real shadows on the grass from the sun (or a bright
  moon), using the same projection as the tower's and the tree's, without shadowing themselves,
  and the grass at their foot is darker (contact occlusion). Tufts grow up against their foot.
- The shore's grass: the strip of grass below the shingle on the right gets the same tufts,
  clumps and swathes, stopping a few rows short of the shingle (see below); tufts near that line
  are shorter, and the old tuft strokes that reach up into the shingle are still drawn there.
- Stones: the seven stones by the path get tufts round their feet; five more small, half-sunk
  stones are scattered in the grass (positions fixed, away from everything).
- Foreground: in the bottom 12% of the frame some of the old tuft draws become larger blades,
  tapering, dark at the foot and light at the tip.
- Weather: lying snow fills the tufts in (their occlusion and normals fade under it, so snow is
  smooth again, with tussocks only where it is patchy); frost rimes the tips; on wet days water
  stands here and there in the ruts and takes a little of the sky (not under snow).

### How the shore stays identical

The shore kit judges objects against reference crops of the shore, so the shingle, the pier's
deck and the sea must stay pixel-identical. The grass is allowed to change (Evan's Dock is hidden,
so the bottom-right grass is the nearest and most prominent ground he sees).

- Every new term is blended in by a per-pixel weight `keep` that is exactly 0 on the shore's side
  from four rows under the top of the grass upward (the shingle, the three grass rows under it
  where `tools/shore_reference.py` fits its contact-shadow alpha, the wet beach, the sea) and rises
  to 1 over the next 6-12 rows; left of the shore it is 1. Adding `0 * delta` is exact in float32,
  so those pixels are computed bit for bit as before (the renormalisation under snow is skipped
  there too).
- The hill's shared generator `r` makes exactly the same draws in the same order as before, even
  where their use changed (`wall_draws()` repeats the old wall's draws; the pebble and tuft loops
  keep theirs), because the shore's stones, strandline and tufts are drawn from the same stream.
  Everything new draws from its own generator (`default_rng(32)` in the hill, 120-140 in
  ground.py).
- Old tuft strokes whose tips reach within four rows of the shingle are drawn exactly as before;
  the rest are replaced by the new grass. New strokes (foreground blades) are only drawn where
  they stay clear of it. `rock()` is unchanged (the shore's stones and the reference builder's
  keep-out spy use it).

## Render time

Command (probe 4): `nice -n 10 $PY renderers/procedural/listening_point.py OUT --date 2026-11-01
--minutes 720-779 --scale 0.75 --jobs 1 --weather fair --quality 90`.

Four runs, alternating, on a busy machine (other renders and a browser running), 60 frames each:
base 141 s / after 182 s, then base 170 s / after 154 s. The noise is larger than the difference;
the cost is about the same as before, well inside the 2x budget. The merged phase-1 tree is re-timed
in `docs/v3/phase1.md`.

One-off near-scenery cost: the ground fields are built once per process on the first keyframe,
about 0.8 s at this size. Per keyframe (`needs_shade` is true here, so two foreground renders per
keyframe): not separated from the noise above.

## Probes

1. `$PY -m unittest discover -s tests`: `Ran 45 tests ... OK`.
2. Determinism: 2026-11-01 12:00 rendered twice into two directories, `cmp` silent; both
   `3d7fea84d9f075d6bd95c5c8b97a7680`.
3. Shore strip: `tools/shore_reference.py OUT --reference r1` from this tree, compared with the
   published `shore/reference/r1`:
   ```
   surfaces.json: identical
   keepout.png: identical
   palette.json: identical
   noon.png: protected px 293516, changed there 0; changed elsewhere in crop 0
   golden.png: protected px 293516, changed there 0; changed elsewhere in crop 0
   night.png: protected px 293516, changed there 0; changed elsewhere in crop 0
   fog.png: protected px 293516, changed there 0; changed elsewhere in crop 0
   PROBE 3: PASS
   ```
   That was before the whole-hill grass (`86b544a`). From `86b544a` the shingle, deck, sea, and the
   rows within 4 of the shingle are still identical, but the grass below it changes, so the four crop
   PNGs and the digest change (`f8f163b3...`, against r1's `37e07b33...`); see Known issues. The
   text below is the pre-`86b544a` result:
   The whole reference set's digest was unchanged
   (`37e07b33a34004069bc784f2ee7b8fb4b3293dd96ccc6185c34d3625354f821c`, the same as `main`'s).
4. Render-time ratio: about 1.0 (0.91 and 1.29 in two noisy pairs); see Render time.

Colour and mood check: mean colour of five grass boxes left of the shore, after/before, is
0.90-1.15 at noon, golden hour, night, fog and summer alike (the spread is the swathes, and it is
the same in every light, so the lighting response is unchanged); the channel ratios (hue) are
unchanged; the path is within 3%.

## Known issues

- **The published r1 crops no longer match the live grass below the shingle.** Probe 3 as first
  written (`y >= dry(x)[0]`) takes in everything below the top of the dry band, which on the right
  is the strip of grass between the shingle and the bottom of the frame (89-488 rows a column), not
  only the shingle. That grass now changes by design (the lead's correction). The shingle, deck,
  sea and shadow-fit rows are identical, and so are `surfaces.json`, `keepout.png`,
  `palette.json` and `conditions.json`; only the four crop PNGs differ, in the grass. If the shore
  kit ever measures an object against the grass below the shingle (for instance `E_FAINT`'s
  "ground around it"), publish a new reference set from this tree.
- At the shingle's lower edge the new grass fades in over 6-12 rows under the old ragged edge,
  where the old tuft strokes that reach the shingle are kept; it reads as a natural margin at both
  sizes, but it is the one place the old strokes survive.
- Ruts are a stylisation and are fairly visible where the path narrows near the door, especially
  in low sun; their strength is two numbers (`0.1 * rut` in the soil albedo, `0.02` in ground.py).
- The tufts are drawn per pixel without antialiasing beyond a half-pixel soft edge; at native size
  the far field near the skyline is busy. At point size it averages out.
- Snow was checked with synthetic weather (2027-01-28 11:00), frost (2026-12-15 09:00) and wet
  ground with a little snow (2026-12-03 10:00); not with every combination.
- The fields cache costs about 40 MB per render process (float16); the nightly job runs two.

## Look-test images

Not committed (rendered frames are never committed). At
`/private/tmp/claude-501/-Users-eddelord-Documents-Projects-cozy-cabin-claude/b85a93cd-3703-4aff-b84b-d9b69db72a54/scratchpad/v3/ground/`:
`{noon,golden,night,fog,summer}-{before,after}-{full.jpg,crop.png,half.png}` and the contact sheet
`before-after.jpg` (native-resolution crops, x 0-900, y 1150-1800, before | after).
