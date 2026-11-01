# v3 phase 2: clouds and light

Branch `v3/clouds` (from `main` `4192c35`). Goal (Evan, 2026-11-01, `docs/V3-PLAN.md` on `v3/plan`):
bigger, shaped clouds with lit tops driven by the forecast; sunbeams through cloud; stronger sunrise
and sunset on the clouds. Style target: a detailed hand-drawn 2D game background. The clear-sky
gradient, the layout, the real sun and moon and the real forecast are unchanged; every light on a
cloud comes from the scene's own sun, moon and sky. Flocks, gulls, geese, aircraft, balloons and
kites are the `v3/air` part and are not touched here.

## What changed

### Heaped low cloud (`renderers/procedural/cumulus.py`, new)

The low deck's cover (`wx.cloud_low`, unchanged) is now shared between two drawings:

- **Heaps:** separate clouds, each one or two *domes*. A dome is an ellipsoid body standing on the
  deck, a ring of bumps round its foot, and rounded heads bulging out of it, larger toward the crown
  and more of them on one side. Everything below the deck (1.2 km, the old low layer's height) is cut
  off flat, so every heap has a flat base in the one plane: distant heaps show a thin dark line,
  heaps overhead show their underside. The spheres are ray-cast on the sky's half-resolution grid
  (the grid the noise layers already use), puff by puff from the nearest, each laid over or under
  what is there with an anti-aliased edge (a soft depth test smooths the creases; the flat base's
  edges are anti-aliased by their own slope across the grid, as a shader's `fwidth` would).
- **The noise layer** (the old `cloud_layer`, unchanged): stratocumulus and, as the deck closes,
  the lid.

Heaps live in cells of a grid on the deck (1.7 deck heights) that drifts with the wind at the deck,
the same drift (`day.drift_e/n`) and wind factor as the old low layer. A cell's heap has its own
threshold, so as the cover rises heaps appear and grow, and as it falls they shrink away; each also
swells and shrinks a little on its own 45-100 minute clock. Positions, sizes and shapes come from a
hash of the cell and the date, so a minute always renders the same. Only heaps within 16 deck
heights (about 3.6 degrees above the horizon) are drawn; distance haze pulls them into the horizon
colour. Puffs smaller than 2.5 grid pixels are left out, and far heaps get fewer puffs.

**Shading.** Each puff's normal is blended into its dome's (0.2 puff, 0.8 dome), so a heap is lit as
one form with lumps on it: a soft two-tone wrap (`_tone`) toward the scene's sun, plus the moon at
night. Sunlit faces take `CLOUD_SUN` (new in `core.py`), the sunlight's colour keyed by the sun's
altitude *as the deck sees it* (1.1 degrees lower than we do); shaded faces take `CLOUD_SHADE`, a
little darker, and the base darker again, darkest under the middle and mottled. A high sun shades
the lower body under the puffs above it. Toward the sun the thin edges and puff rims glow (a
forward-scattering lobe round the sun's direction). Haze grows with distance. Behind higher cloud
(what `sun_visibility` lets through the noise layers) the heaps lose some of their direct light.

### How cloud type is chosen (`cumulus.regime`, once per frame; signals once per day)

Only fields `weather.py` already has: the low/mid/high cover, temperature, the weather code (showers
80-82 and 85-86, thunder 95-99, a front's rain or snow 51-67 and 71-77), rain/snow/drizzle, the sun's
altitude, and the wind.

- **Convection** `heat`: the sun's altitude, or what it was 90 minutes ago if higher (heaps outlast
  the afternoon's heating), times a mild temperature factor. Showers within the next 150 minutes or
  thunder within the next 180 (looked for ahead: heaps tower up before the rain) count as convection
  too.
- **Lid** `lid`: the low cover from 0.6 to 0.95, or a front's steady rain with a mostly closed deck.
- **Share** of the low cover drawn as heaps: `(1 - lid)^2 * (0.25 + 0.75 * convection)`; the rest
  is the noise layer. So a summer afternoon is all heaps, a night or a winter day mostly
  stratocumulus with a few flattened heaps, an overcast day a flat grey lid. Heaps cover 0.75 of
  their share on the deck (their sides fill more of the view than their footprint).
- **Tower:** a heap's height is 0.65-1.2 times its radius on a warm fair afternoon (at least 0.4 at
  night or in winter); showers and thunder build towers 2-3 times as tall, with heavier, darker
  bases (`dark`).
- **Rain shafts:** when showers are about (signal over 0.25), the biggest, tallest heaps hang a grey
  curtain from the base to the horizon, leaning downwind, streaked.

### Stronger sunrise and sunset on the clouds

- Heaps: a low sun lights their sunward faces gold to deep orange (`CLOUD_SUN`); while the sun is
  below the deck's level but not yet set on it, it lights the bases from below, orange toward it and
  rose away from it; then the earth's shadow climbs past the deck and the heaps turn violet-grey
  against the glowing sky. Thin edges toward the sun glow.
- Noise layers (`sky.clouds`): each layer keeps the sun for as long as its height sees it (`DIP`:
  high 3.0, mid 1.9, low 1.1 degrees below our horizon); in that window its lit colour is pulled
  toward gold on the sun's side of the sky and rose away from it (`ROSE`), and the thin edges near
  the sun glow. The clear-sky gradient, sun glow, Belt of Venus and earth's shadow are untouched.
- The mid layer is drawn as cloudlets: crisper edges (`soft` 1.0 -> 0.75 in `CLOUD_LAYERS`), lit
  and shaded tones drawn a little apart, each cloudlet a little darker at its heart.

### Sunbeams through cloud (`weatherfx.cloud_beams`)

`light_shafts()` is unchanged for a frame with no cloud (so the clear reference frames are
bit-identical); with any cloud in the sky it calls `cloud_beams()`, which works along rays out of the
sun in polar coordinates (1024 angles, quarter resolution): what blocks the light (cloud coverage
from `clouds()`, plus the tower and tree) is accumulated outward from the sun, with a memory of about
18 degrees, so each cloud casts a shadow through the hazy air behind it. Shadowed air is darkened,
lit air between shadows brightened (warm, `CLOUD_SUN`), and both continue below the horizon onto the
far sea, fading over 3.5% of the frame height. The strength needs a low or middling sun (to 50
degrees), haze (relative humidity), and cloud broken round the sun, or the sun hidden behind a cloud
with sky around it. The old bright-sky smear is kept, integrated in the same polar pass (the same 28
taps, as running sums), drawn from the gaps only, and allowed to keep going when the sun is behind a
cloud. One polar pass costs less than the old 28 resamplings.

### Other

- `sky.layer_cover(2)` is the noise layer's share of the low cover; `sun_visibility` also ray-casts
  the heaps across the sun's disk (seven directions), so a heap passing over the sun dims the scene
  as before.
- Nothing else in the scene changed: sea, land, objects, fog, rain and the shore are untouched.

## Probes

All on `cefb576` (the code this doc describes; the doc commit after it changes no code).
`$PY` = `~/Documents/Projects/listening_point/venv/bin/python`.

1. **Tests: PASS.** `$PY -m unittest discover -s tests`: `Ran 45 tests in 7.166s` / `OK`.
2. **Determinism: PASS.**
   - The two branch runs of the timing command (2027-06-08, `--weather synthetic`, 12:00-12:59, heaps,
     mid and high cloud, keyframes): all 60 frames `cmp`-identical (`60 frames compared, 0 differ`).
   - Rendered again into a second folder and `cmp`'d against the look-test renders, `--scale 0.75`:
     2026-11-01 `--weather fair` 15:40 identical (`0c398f22b948ebbf22f8513dad7f814e`);
     2027-10-15 `--weather synthetic` 17:00 identical (`06d4182485c5542d5e0363b7e8e2a73c`) and
     17:45 identical (`4fe308d8ea469aead3ef87d2500d16e9`).
3. **Shore reference unchanged: PASS.** `$PY tools/shore_reference.py OUT --reference r2` from this
   tree: `digest 7cbee1f442afce967826b8e6f6aaffddd8921391b138a487f359b4d9024d35fa` (the same as
   `main`; also checked on the untouched tree before starting and on `7d33c78`). Why it holds: the
   reference weathers (`clear`, `fog`) have no cloud at all, so every new path is skipped (no layer
   reaches `cover >= 0.01`, `population()` returns None, `cloud_occ` stays None and
   `light_shafts()` runs its old code); `CLOUD_LAYERS`' mid softness only matters where there is mid
   cloud. The look test's fog frame (2026-11-01 `--weather fog` 10:00) is byte-identical to `main`'s.
4. **Render time: ratio about 1.1 (<= 1.25)**; see Render time.

## Render time

Probe-4 command, `nice -n 10 $PY renderers/procedural/listening_point.py OUT --date D --minutes 720-779
--scale 0.75 --jobs 1 --weather synthetic --quality 90`, main (`~/Documents/Projects/listening_point`,
`4192c35`) against this branch. The machine was shared with other agents' renders and tests, and its
load swung from 5 to 27 during the runs, so the sequential pairs are mostly noise; two pairs run *at
the same moment* (both processes see the same load) are the better measure.

| pair | date | order | load (1 min) | main real / cpu s | branch real / cpu s | ratio real / cpu |
|---|---|---|---|---|---|---|
| 1 | 2027-06-08 | main, branch | 15 -> 8 | 307.9 / 267.6 | 266.9 / 246.1 | 0.87 / 0.92 |
| 2 | 2027-06-08 | main, branch | 8 -> 8 | 238.9 / 219.4 | 181.0 / 179.1 | 0.76 / 0.82 |
| 3 | 2027-06-08 | branch, main | 19 -> 11 | 411.4 / 322.1 | 488.2 / 393.3 | 1.19 / 1.22 |
| 4 | 2027-07-07 | branch, main | 5 -> 6 | 142.1 / 142.7 | 157.0 / 155.9 | 1.10 / 1.09 |
| 5 | 2027-07-07 | main, branch | 6 -> 19 | 182.8 / 176.0 | 401.3 / 292.9 | 2.20 / 1.66 |
| C1 | 2027-07-07 | together | 10 -> 27 | 530.2 / 321.6 | 568.4 / 353.4 | **1.07 / 1.10** |
| C2 | 2027-06-08 | together | 27 -> 9 | 468.9 / 279.4 | 509.2 / 310.7 | **1.09 / 1.11** |

(cpu = user + sys.) 2027-06-08 noon: low 0.36, mid 0.23, high 0.29, heaps. 2027-07-07 noon: low
0.49-0.59, mid 0.27: a heavier heap sky. Pair 5's branch run met a load spike (6 to 19) in its
middle. The concurrent pairs give about **1.08 wall, 1.10 CPU**. Where it goes, per minute frame
(sky only, profiled): the heaps' ray cast and shading cost 0.3-0.6 s on a busy machine, partly paid
back where the heaps replace the low noise layer (its full-grid resamplings skipped) and where
`cloud_beams()`' single polar pass replaces the old 28 resamplings. The heaviest case seen is a
showery afternoon (2027-06-02 16:20: about 1,400 puffs, sky about +0.3 s); not timed over a full hour.

## Look test

Folder: `/private/tmp/claude-501/-Users-eddelord-Documents-Projects-cozy-cabin-claude/b85a93cd-3703-4aff-b84b-d9b69db72a54/scratchpad/v3/clouds/`,
`<n>-<scene>-a-before.jpg` (main, `4192c35`) and `-b-after.jpg` (this branch), full frames at
`--scale 0.75` (2880x1800), quality 90, rendered with `--times` (so each minute has its own near
scenery, as the reference frames do).

| n | scene | date | time | weather |
|---|---|---|---|---|
| 1 | cumulus-afternoon | 2027-06-08 | 14:00 | synthetic (low 0.48, mid 0.23, high 0.29) |
| 2 | cumulus-sun-behind-altocumulus | 2027-06-08 | 16:00 | synthetic (thunder due at 18:00) |
| 3 | showery-towers | 2027-06-02 | 15:30 | synthetic (rain from 16:00, thunder by 17:00) |
| 4 | shower-thunder | 2027-06-02 | 16:20 | synthetic (raining, thunder) |
| 5 | overcast | 2026-11-11 | 12:00 | synthetic (low 0.86, mid 0.72) |
| 6 | beams-sun-behind-cloud | 2027-10-15 | 17:00 | synthetic (sun 8 degrees, behind a heap) |
| 7 | sunset-broken-cloud | 2027-10-15 | 17:45 | synthetic (sun 1.4 degrees, low 0.34) |
| 8 | fair-noon | 2026-11-01 | 12:00 | fair |
| 9 | fair-golden | 2026-11-01 | 15:40 | fair |
| 10 | fair-night | 2026-11-01 | 22:00 | fair |
| 11 | fog | 2026-11-01 | 10:00 | fog |

What to look at:

- **1, 3:** heaps with lit tops and flat bases, rows of them shrinking into the haze toward the
  horizon; near ones overhead show their grey undersides. 3's are towers with heavier bases.
- **4:** dark, heavy heaps under the mid deck in the rain (the rain shafts are faint at this size).
- **5:** the flat grey lid, as before (heaps fade out as the deck closes).
- **6:** the sun behind a heap on the horizon; shafts fan up and left out of the gaps and the
  heaps near the sun have glowing rims.
- **7:** peach-gold heaps lit from below, darker violet tops, rose cloudlets above, shafts from the
  setting sun.
- **8-11:** nothing else broke. Night (10) differs from `main` by a mean of 0.01 levels, fog (11) is
  byte-identical, the land and sea are unchanged except through the sky's light (the sea reflects
  the new clouds; `sun_vis` now includes the heaps).
- **Fair days have much less low cloud than before (8, 9).** On `main` the fair day's 5% low cover
  was drawn by the noise layer as a milky veil over about half the sky (mean density 0.34 on the
  sky grid, 46% of it above 0.3); now that 5% is a handful of heaps, so the sky is bluer and
  clearer. This follows the forecast more closely but changes the fair days' look the most; it is
  the first thing to check with Evan.

## Known issues

- **Motion:** the heaps drift with the same wind as the old low layer (1.5 times the surface wind
  at the deck), so a near heap moves several degrees a minute on a windy day; between two frames it
  is a step, not a glide. This matches the old layer's speed but heaps, being distinct shapes, make
  it more noticeable.
- **Midnight:** the heaps' cells are salted with the date and the drift restarts at midnight, so
  the heaps change at 00:00 (the noise layers already jump there).
- **Level of detail:** a heap gains or sheds puffs one at a time as its size on screen changes
  (always from one fixed list, so it keeps its shape); puffs under 2.5 grid pixels are left out.
  A small puff can still pop in or out between minutes; not seen at viewing size.
- **Edges** are drawn on the half-resolution sky grid and upsampled, so silhouettes are about 2 px
  soft at 2880 wide (1 pt); a few creases between a dome's side and its flat base still show
  1-2 px steps at 1:1.
- **Style:** the heaps are stylised (rounded puffs, smooth gradients, a flat underside), nearer a
  game background than a photograph, as asked; up close they can read as smooth "clay". There are
  no ragged fractus edges or wisps. Heaps overhead show large flat grey bases.
- **Beams** are strongest with a low sun behind broken cloud (6, 7). With the sun hidden behind a
  small isolated heap high in the sky the shafts are faint (the shadow wedge is narrow).
- **Summer sunsets** are off the right edge of the frame (azimuth over 290 degrees), so in June the
  sunset colours show on the clouds but the sun and its shafts are out of view (unchanged geometry).
- **Rain shafts** only hang from big, tall heaps within 16 deck heights when the shower signal is
  over 0.25; at viewing size they are faint grey veils.
- **Timing** was measured on a heavily shared machine; the concurrent pairs (1.07-1.11) are the
  number to trust, and the lead's re-time of the merged tree should confirm it.
- `v3/air` draws gulls, geese and aircraft in `sky_extras()`, after `sky()`; nothing here touches
  that code, so the two should merge cleanly, but the air's things will now fly in front of the
  heaps (they are drawn later), which is right for things below 1.2 km and wrong for aircraft above
  the deck.
