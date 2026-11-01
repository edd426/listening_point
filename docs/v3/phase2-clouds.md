# v3 phase 2: clouds and light

Branch `v3/clouds` (from `main` `4192c35`). Goal (Evan, 2026-11-01, `docs/V3-PLAN.md` on `v3/plan`):
bigger, shaped clouds with lit tops driven by the forecast; sunbeams through cloud; stronger sunrise
and sunset on the clouds. Style target: a detailed hand-drawn 2D game background. The clear-sky
gradient, the layout, the real sun and moon and the real forecast are unchanged; every light on a
cloud comes from the scene's own sun, moon and sky. Flocks, gulls, geese, aircraft, balloons and
kites are the `v3/air` part and are not touched here.

## Version 2 (after the lead's review of the first look test)

The lead kept the beams (6) and the sunset colour on the noise layers (7) and sent the heaps back:
smooth grey "stickers"; a clip-art field of near-identical puffs; giant flat discs overhead; a fair
sky that had lost its texture; dark blots in the sea. What v2 does about each:

1. **Form and light** (`cumulus._dome`, `render`, `shade`)
   - **Cauliflower edges at three sizes.** Each dome is a body, a ring of bumps at its foot, up to 14
     heads, then knobs on the first heads and smaller knobs on those knobs, pushed to the upper and
     sunward side. On top of that, a cellular texture of sphere caps (`billow_tex`, two sizes, about
     150 m and 60 m) rides on each dome's face. It tilts the surface normal, so every billow is lit on
     its sun side, and it cuts the outline into knobs (`knobs`).
   - **Light.** Sunlit planes are a warm white (`CLOUD_SUN` times `WARM`, slightly past white, so the
     grade's shoulder rolls them off) with a defined turn into shade (`_ramp`). The shaded side is
     sky-lit blue-grey (`lights()`: the cloud shade colour mixed with the sky's mid and zenith
     colours), lighter on faces that look up and faintly darker in the creases between puffs.
   - **Silver lining.** It follows only the heap's outline, broken by the knobs, with a weaker glow
     through the body. Its strength falls off with the angle from the sun. In v1 every puff's rim
     glowed, which drew the grey discs.
   - **Bases.** The flat base is darker under the middle, mottled, lighter on small (thin) heaps,
     and hazes out with distance.
2. **The field** (`population`, `horizon_band`)
   - **Clusters and streets.** A slow noise sets where heaps cluster and how big they grow. In a
     moderate wind (3-7 m/s) they line up in streets along it.
   - **Rows of domes.** A big heap is a row of two to four domes, the first the tallest; extra domes
     grow in smoothly.
   - **Size.** Sizes range widely: the radius is cubic in a uniform hash, so most heaps are small and
     a few are big.
   - **Toward the horizon.** Far heaps grow broader and flatter, then fade (at 8-11 deck heights)
     into `horizon_band`. The band is low, flattened lumps of a noise on the deck, lit along their
     tops, lost in the horizon haze, and drifting with the heaps.
3. **Overhead**
   - No heap is drawn nearer than about 3-4 deck heights, so none sits above about 15 degrees and
     none can fill the top of the frame.
   - Above `OVERHEAD` (14 degrees) the low noise layer carries the heaps' share of the low cover, so
     the cover overhead is still the forecast's.
   - Each heap is turned partly side-on: about its base, by 0.75 of the angle we look up at it
     (`TILT`). So its flat base is seen nearly edge-on, as a 2D background shows clouds, not as a
     grey disc from below.
4. **Cover follows the forecast, and fair days keep their texture** (`sky.layer_threshold`)
   - **The cause.** Each noise layer used a fixed threshold, the normal quantile of its cover. The
     window of noise in view is small next to the noise's large blobs, so what showed was chance. On
     2026-11-01 12:00 the 5% low deck covered about half the sky on `main` (mean density 0.34) and
     nearly nothing on v1.
   - **The fix.** The threshold is now measured from this frame's sky (a quantile on a coarse grid,
     once per layer and frame), so each layer's visible density matches its forecast cover.
   - **Measured on the sky grid** (mean density above 2 degrees; cover / seen):

     | frame | high | mid | low |
     |---|---|---|---|
     | 2026-11-01 fair 12:00 | 0.20 / 0.20 | 0.14 / 0.13 | |
     | 2026-11-01 fair 15:40 | 0.48 / 0.47 | 0.22 / 0.22 | |
     | 2026-11-11 synthetic 12:00 | 0.40 / 0.40 | 0.71 / 0.69 | noise 0.87 / 0.86 |

   - **Heaps.** On frames where all the low cover is heaps (share 1), heaps and overhead layer
     together showed 0.29 / 0.36, 0.48 / 0.48, 0.59 / 0.46, 0.51 / 0.54, 0.51 / 0.55 and 0.31 / 0.32
     (seen / forecast).
   - **Fair days.** The fair-day high and mid layers now draw their full cover, so the soft veil and
     wisps of `main` are back; the 5% low cover is a few small heaps.
5. **Sea** (`sea.py`). Where the reflection samples a heap or the horizon band (`heap_occ`), it is
   pulled 55% toward the horizon colour, so heaps show in the sea as pale, hazy shapes, not dark
   blots.

## What changed (v1 and v2 together)

### Heaped low cloud (`renderers/procedural/cumulus.py`, new)

The low deck's cover (`wx.cloud_low`, unchanged) is shared between heaps and the old noise layer.

**The heaps** are separate clouds built from spheres:
- **Shape.** One heap is a row of one to four *domes*, each built as in Version 2 item 1.
- **The flat base.** Everything below the dome's base plane, the deck at 1.2 km (the old low
  layer's height) turned with the heap, is cut off flat.
- **Drawing.** The spheres are ray-cast on the sky's half-resolution grid, the grid the noise layers
  already use. Puffs are laid one by one from the nearest, each over or under what is there, with
  anti-aliased edges and a soft depth test.

**The noise layer** (the old `cloud_layer`) draws the rest: stratocumulus and, as the deck closes,
the lid. Overhead it also carries the heaps' share.

**Motion and lifetime:**
- Heaps live in cells of a grid on the deck (1.7 deck heights). The grid drifts with the wind at the
  deck: the same drift (`day.drift_e/n`) and wind factor as the old low layer.
- A cell's heap has its own threshold, so as the cover rises, heaps appear and grow; as it falls,
  they shrink away. Each also swells and shrinks a little on its own 45-100 minute clock.
- Positions, sizes and shapes come from a hash of the cell and the date, so a minute always renders
  the same.
- A far dome keeps only the first puffs of its fixed list, so as it drifts nearer it gains puffs
  without changing shape.

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
  stratocumulus with a few flattened heaps, an overcast day a flat grey lid.
- **Tower:** a heap's height over its radius, 0.8-1.4 times a factor of 0.75-1.2 on a fair day
  (rising with the day's heat), up to 1.45 when showers or thunder are near, with heavier, darker
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

All on `e5b750b`, the v2 code; the doc commit after it changes no code.
`$PY` = `~/Documents/Projects/listening_point/venv/bin/python`.

1. **Tests: PASS.** `$PY -m unittest discover -s tests`: `Ran 45 tests in 6.471s` / `OK`.
2. **Determinism: PASS.**
   - The heavier heap sky, 2027-07-07 `--weather synthetic`, 12:00-12:59 (probe-4 command): two
     branch runs, all 60 frames `cmp`-identical (`60 frames compared, 0 differ`).
   - The 11 look-test frames were rendered twice, once on `e1fe7f4` and once on `e5b750b`. The last
     commit only changes the heaps' haze, so frames without heaps must match, and they do: fair night
     22:00 (`4042d8abedd25de45655b07555b31fe0`), fog 10:00 (`5c81f5d3c5609b881083eb400a1417c7`) and
     overcast 2026-11-11 12:00 (`7a690ad1edbff6bedf66d4c6e5531085`).
3. **Shore reference unchanged: PASS.** `$PY tools/shore_reference.py OUT --reference r2`, run on
   `e1fe7f4` and on `e5b750b`: `digest 7cbee1f442afce967826b8e6f6aaffddd8921391b138a487f359b4d9024d35fa`,
   the same as `main`.

   Why it holds: the reference weathers (`clear`, `fog`) have no cloud at all, so every new path is
   skipped:
   - no layer reaches `cover >= 0.01`, so the new threshold code never runs;
   - `population()` and `horizon_band()` return None;
   - `cloud_occ` and `heap_occ` stay None, so `light_shafts()` takes its old path and the sea its
     old reflection.

   The look test's fog frame is byte-identical to `main`'s.
4. **Render time: ratio about 1.14 (<= 1.25)**; see Render time.

## Render time

**v2.** The probe-4 command, `nice -n 10 $PY renderers/procedural/listening_point.py OUT --date D
--minutes 720-779 --scale 0.75 --jobs 1 --weather synthetic --quality 90`. Main
(`~/Documents/Projects/listening_point`, `4192c35`) and this branch were started *at the same moment*,
so both saw the same load; load 6-8 throughout (quieter than v1's runs).

| pair | date | load (1 min) | main real / cpu s | branch real / cpu s | ratio real / cpu |
|---|---|---|---|---|---|
| 1 | 2027-07-07 | 8.1 -> 8.5 | 181.2 / 174.4 | 209.4 / 201.9 | 1.16 / 1.16 |
| 2 | 2027-06-08 | 8.5 -> 6.7 | 170.9 / 167.7 | 191.0 / 187.2 | 1.12 / 1.12 |
| 3 | 2027-07-07 | 6.7 -> 7.2 | 164.8 / 161.8 | 190.8 / 188.2 | 1.16 / 1.16 |

(cpu = user + sys.) About **1.15**. Where the cost goes, per minute frame (sky only, best of three,
CPU): 2027-07-07 12:30, 0.58 s on main and 0.84 s here; 2027-06-02 15:30 (showery), 0.59 s and
0.89 s; 2026-11-01 fair 12:00, 0.73 s and 0.62 s. The puff ray cast is about 0.3 s, the billow
texture and band 0.1 s. Part of this is paid back: the heaps replace the low noise layer, and
`cloud_beams()`' single polar pass replaces the old 28 resamplings.

v1 measured 1.07-1.11 in concurrent pairs under heavier load (load 9-27); those runs are superseded.

## Look test

Folder: `/private/tmp/claude-501/-Users-eddelord-Documents-Projects-cozy-cabin-claude/b85a93cd-3703-4aff-b84b-d9b69db72a54/scratchpad/v3/clouds/`.

**Files**
- `<n>-<scene>-a-before.jpg`: `main` (`4192c35`).
- `-b-after.jpg`: v1 (`cefb576`).
- `-c-v2.jpg`: this version (`e5b750b`).
- All are full frames at `--scale 0.75` (2880x1800), quality 90, rendered with `--times`.
- `<n>-heaps-crop.png`: native-size crops of the v2 frames: 1, 2, 3, 6 and 7.

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

What to look at in v2:

- **8, 9:** the fair-day veil and wisps are back, with a few small heaps along the horizon.
- **1, 2:** heaps in clusters and rows, smaller and flatter toward the horizon, with knobbly tops
  and a hazy band below them. The tops are brighter than v1.
- **6:** the sun is behind a heap at 17:00. The heap field is different from v1's, so the sun sits
  behind a smaller heap and the beams are weaker than in v1. The sun is hidden from 16:42 to 17:04
  that day.
- **7:** the noise layers' sunset colour is unchanged from v1. The heaps are peach and rose, lit
  from below.
- **10:** the fair night now differs from `main` by a mean 0.66 levels: the night layers' cover now
  follows the forecast. **11:** byte-identical to `main`.

## Known issues

- **Still not the target in the towers (3, 4).**
  - Showery heaps read as rows of bells: tall, smooth-sided columns, each with a flat brim at the
    bottom.
  - The billow texture gives their surfaces a cauliflower grain, but their outlines stay simple.
  - A crisper silhouette needs more large lobes on the flanks than the cost allows with this puff
    count. Tried and dropped: stacking turrets (it read as snowmen).
- **The tilt is a stylisation.** Each heap is turned side-on to us, so seen from below, a heap does
  not show a cut-off base as it physically would. Bases are only visible as a thin darker band.
- **Fair-weather heaps at a high sun (1)** are lit from above. Their sides are in sky-lit shade, so
  the lit/shaded split is mostly top/bottom, and the warm-white is strongest on the crowns.
- **Beams (6)** depend on where the heap field puts a heap in front of the sun at that minute. They
  are faint when the sun is behind a small heap.
- **Motion:** heaps drift with the old low layer's wind (1.5 times the surface wind at the deck).
  Near ones step a few pixels a minute on windy days.
- **Midnight:** the heaps change at 00:00, where the noise layers already jumped.
- **Edges** are drawn on the half-resolution sky grid. Silhouettes are about 2 px soft at 2880 wide,
  and the depth test leaves faint crease lines between some puffs.
- **Rain shafts** are faint grey curtains, only under big, tall heaps when the shower signal is over
  0.25.
- **June sunsets** are off the right edge of the frame (unchanged geometry).
- **Things in the air:** `v3/air` draws after `sky()`, so its things fly in front of the heaps. That
  is right for birds and wrong for aircraft above 1.2 km.
