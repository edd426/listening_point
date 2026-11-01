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
- **Tower** (height over width): about 0.5-0.9 on a fair day, rising with heat; showers and thunder
  build towers 2-3 times as tall, with heavier, darker bases (`dark`).
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

(filled in below)

## Render time

(filled in below)

## Look test

(filled in below)

## Known issues

(filled in below)
