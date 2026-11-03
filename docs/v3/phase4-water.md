# v3 phase 4, part 1: the water

Branch `v3/water`, from `main` `450163e`. Evan named the open sea as one of the empty areas and asked, for
the sea, for light on water (cloud shadows, wind patterns, glitter) and markers (buoys, lobster-pot floats,
a channel marker). This part also adds a skerry for part 2's seals. No boats, no creatures, no people:
part 2 adds the fishing boat, sailboats, the ferry and the sea life, using what is placed here.

## What was added

New module `renderers/procedural/water.py` (`WaterMixin`, added to `Frame`). Hooks:
- `sea.py`'s `sea()`: the wind's roughness, the cloud shadows, the new glitter and the whitecaps, each
  behind `v3 = not self.reference`;
- `plan_emitters()`: the beacon's light as an emitter;
- `listening_point.py`'s `background()`: `beacon()` after the sea, then `bay()` in place of
  `boats(); moored_boat()`;
- `render()`: `beacon_glow()` after the far fog;
- `sky.py`: `cloud_layer(..., shift=None)` and `_layer_field(..., shift=None)` take an optional ground
  offset, so the sea's shadows sample the very layers the sky draws. With no shift both are unchanged.

Reference mode draws none of it and computes none of it (tested). Nothing new draws from the frame's
shared generator `self.rng`: whitecaps use `default_rng([date, 4400, i, cycle])`, the skerry's breaking
water `default_rng([date, 4420, minute])`, and the skerry's shape fixed seeds 4410-4412.

Coordinates are pixels of the production frame (`--scale 0.75`, 2880 x 1800), x from the left, y from the
top. The horizon is y 1044. World units are `core.FrameBase.proj`'s: the camera stands 1 unit (about 15 m)
above mean sea level, x to the right (west), z ahead (south), y up. `water.sea_point(xn, yn)` gives the world
(X, Z) and distance D of any frame point on the sea; near a mark, one world unit is
`0.58 * H / radians(70) / D` px (`k` below).

### Light on the water

- **Cloud shadows** (`sea_shadow`). For each pixel of the sea (worked on a 6 px grid, blurred one cell,
  then upsampled), the direct light that reaches it through each cloud layer. Each layer is sampled with
  `sky.cloud_layer` at the sun's (or the moon's) direction from a point shifted along the ground. The layers
  are the same three noise layers, with the same threshold, cover and wind drift as the sky this minute. The
  layers stop the light as `sun_visibility` has them (0.25, 0.85, 0.97). At the foot of the frame the shift is
  near zero, so the water there gets the light the land gets. The sea's distances are stretched 24 times
  (`SHADOW_G`, distances capped at 60 units). Seen from 15 m, a cumulus shadow a kilometre wide would
  otherwise cover the whole near bay at once, or lie only as slivers on the horizon. How it shows:
  - the water's own sunlit colour (the `0.35 * sun` part of the body) is scaled by the local light, as
    physics has it;
  - and, as a painter would, the sea is brightened or darkened by `0.25 * (T - median T)` of the bay in
    view. This fades toward the horizon (none within 0.6 degrees, full from 5) and eases for a sun below
    10 degrees. An even sky (clear or overcast) leaves the sea as it was.

  The glitter paths are cut by the same field (`T ** 1.5`). The moon's path uses its own field (`sea_Tm`).
  The marks and the whitecaps take their light from the local field too (`local_shade`).
- **Wind on the water** (`sea_wind`). A roughness `lr` (about 1 on average) on a 3 px grid, from the hourly
  forecast wind speed and direction. It scales the wave field, so it sharpens or breaks the reflections. It
  lifts the reflected row by `(lr - 1) * (3 s + 0.4 dy)` px: rough water mirrors the sky from higher up, so
  it reads darker. It also changes how much the water mirrors (`f * (1 - 0.45 (lr - 1))`, fading toward the horizon, none
  within half a degree). By wind:
  - **below about 2 m/s, glassy calm with cat's paws.** Glassy water (`lr` 0.38-0.88) carries rippled patches
    a few tens of metres across (`lr` 1.35). They cover 8% of the water in the faintest airs and about half
    at 2.8 m/s; the level is set from the water in view, as the sky sets its cloud cover. They drift
    downwind at 4% of the wind's run (`SLOW`) and change shape over about 7 minutes.
  - **about 3-8 m/s, lanes and slicks.** Long streaks along the wind direction (they converge toward the
    wind's point on the horizon in perspective). About a third of the water is smooth slick (`lr` 0.7), the
    rest rippled (to 1.35). The regimes cross over between 2.2 and 3.5 m/s.
  - **8-12 m/s and up, a blow.** All of it rough (`lr` 1.15-1.4), still streaked.

  Beyond 7-16 units, where these patterns would be finer than the pixels, the same water shows as soft
  bands along the horizon. Within 1.5 degrees of the horizon it evens out.
- **Glitter** (`glitter`, replacing `sea()`'s `path` outside reference mode). The sun's and moon's paths
  respond to the wind:
  - width `min(1.8, 0.55 + 0.11 v)` times main's (as wide as before at about 4 m/s), wider still on rough
    patches;
  - length `min(1.4, 0.8 + 0.05 v)` times main's;
  - on a calm sea (under about 3 m/s) a steady base (0.25 to 0.70) with fewer glints, so the path is narrow,
    bright and nearly whole;
  - in a blow the base drops to 0.10 and the glints grow and multiply (their threshold drops from 0.9 to
    0.6), so it breaks up.

  Only the columns the path can reach are computed.
- **Whitecaps** (`whitecaps`, replacing the noise-blob foam outside reference mode). From 7.5 m/s, strength
  `c = (v - 7.5) / 6` (0.08 at 8 m/s, 1 from 13.5 m/s). There are up to `340 c^1.1` sites over x 0.24-1.0,
  denser toward the horizon, none right at the shore. Each is a short bent crest (about 1-41 px long at
  native size, by perspective) with two to six broken foam dabs spilling below it. Each lives 4 minutes, fading in and
  out (sites staggered), drifts downwind, and then reappears elsewhere. It is lit by the local cloud
  shadow.
- **Fix: a hard line across the bay** (`weatherfx.cloud_beams`). The cloud beams' sun glow and shafts ran
  onto the sea and stopped dead 180 px (10% of the frame) below the horizon. They now fade out over the
  lower three quarters of that band. This was visible on `main` in cloudy frames whose sun glow reached that far
  (look at `pair-calm-morning`'s top half, about y 590). Reference frames never take this path (digest
  unchanged).

### The marks

All are drawn in `background()`, so the far fog and the mist veil them by distance. The rising and falling
of the water is drawn on fixed things: the water level at the marks is `(tide - 0.5) * TR` world units, `TR`
= 0.10 (about 1.5 m), so low water is -0.05 and high water +0.05. The floats ride the sea's surface, which the
renderer draws as a fixed plane (y = 0, as the boats and the pier do).

- **The beacon** (`beacon`, `beacon_glow`, `beacon_light`). A port-hand lateral mark (IALA A: red post, red
  can topmark) on the approach to the island's harbour. World (3.341, 8.850), D 9.46 units (about 140 m),
  k = 90.3 px/unit. The post stands 0.42 units (about 6 m) above mean water, large enough to read at
  desktop size.
  - Foot at x 1710.7. The waterline is at y 1138.5 at low water, 1134.0 at mean and 1129.5 at high water;
    the weed and barnacle band (with a pale barnacle line at high water) shows below 1129.5.
  - The red post runs to y 1096.3 (top), 4.8 px wide (half-width 2.4).
  - The lantern housing is at y 1092-1096, the light's centre at y 1094.3.
  - The can topmark runs from y 1089.6 to 1081.5, 8.2 px wide.
  - It is mirrored in the water, broken by the ripples by wind. A little wash at its foot shows the tidal
    stream's direction and strength.
  - **The light is steady red**, from dusk to dawn with the other lamps (`lights_on`), the same every
    minute. It is drawn after the far fog, so in fog it dims with distance and spreads into a halo; it is
    also an emitter, so the sea mirrors it.

  Part 2's ferry should pass beyond it (y < about 1125 near x 1711), keeping it to port on the way into
  the island's harbour (the breakwater's green light is at about x 1660, on the horizon).
- **Two mooring buoys** (`BUOYS`, drawn by `sea_marks` with `ball`). Each is a lit sphere sunk 38%, with a
  dark mooring ring on top and a small pick-up buoy trailing down-stream on its line. Each is reflected in
  the water.

  | buoy | anchor (x, y) | D | radius | over a day |
  |---|---|---|---|---|
  | 0, orange, beyond the pier's end | (2329.9, 1305.0) | 3.17 | 7.0 px | x 2326-2333, y 1304-1307 |
  | 1, white, right of the moored boat | (2738.9, 1440.0) | 2.00 | 12.8 px | x 2736-2742, y 1437-1446 |

  The waterline point for each is `Frame.mark_positions()` (kind "buoy", index 0 or 1). It swings round
  its anchor with the stream and the wind, by up to 0.035 x (1.25 - 0.5 tide) units (more slack at low
  water). Either is a mooring for part 2's fishing boat; buoy 1 is the nearer and larger.
- **A string of lobster-pot floats** (`POTS`). Five orange floats in a line along the near shore below the
  lamp; the first (farthest left) is the dahn, a float on a dark pole with an orange flag.

  | float | anchor (x, y) | D | radius |
  |---|---|---|---|
  | 0 (dahn; pole 44 px above it) | (1886.4, 1328.4) | 2.89 | 5.0 px |
  | 1 | (1932.5, 1341.0) | 2.76 | 5.3 px |
  | 2 | (1981.4, 1353.6) | 2.64 | 5.5 px |
  | 3 | (2030.4, 1364.4) | 2.54 | 5.7 px |
  | 4 | (2073.6, 1375.2) | 2.45 | 5.9 px |

  Each swings by up to 0.02 x (1.2 - 0.4 tide) units: within about 5 px over a day (measured on three days).
  - In a strong stream (`|tide_flow| > 0.2`) each is dragged lower (sunk 42-60%) and trails a tapering wake
    down-stream.
  - The dahn's pole leans with the stream and the wind (top down-stream). Its flag hangs in a calm and
    streams downwind, fully from 5 m/s.
  - The tidal stream (`tide_flow`, -1..1) is the tide's rate of change, normalised. It sets west (to the
    right) on the flood and east on the ebb. The wind adds `0.045 v` downwind (`set_on`).
- **The skerry** (`skerry`, `skerry_field`). A low whaleback reef with three knobs, in the middle of the bay
  inside the sailing boat's round trip. Centre (2260.8, 1234.8), D 4.40 units (about 66 m), k = 194
  px/unit. It is 1.32 x 0.64 units (`SKERRY_HALF` 0.66, 0.32), about 20 x 10 m.
  - **Drawing.** It is drawn as a lit height field from far to near (150 x 60 samples): olive wrack low
    down, a grey crust of barnacles on the knobs, darker cracks. Rock just out of the water is wet and dark
    with a sky sheen. A broken wash laps along its foot, and it is reflected in calm water.
  - **Covered.** Just after it covers it shows faintly through the water, fading to nothing at 0.045 units
    deep; at a spring high water it does not show. In a breeze, broken white water is drawn over it while
    it is shallow, changing each minute.
  - **Exposed by tide** (fraction of its field above water):

    | tide | exposed | x extent | top y | waterline y |
    |---|---|---|---|---|
    | 0.0 | 42% | 2173-2353 | 1227 | 1234-1253 |
    | 0.2 | 30% | 2186-2349 | 1227 | 1232-1248 |
    | 0.4 | 7% | 2205-2342 | 1227 | 1230-1242 |
    | 0.6 | 2% | 2212-2242 | 1227 | 1228-1233 |
    | 0.8, 1.0 | covered | | | |

    The shelf dries below tide 0.38-0.42. The knobs:

    | knob (x, y) | height (units) | above water while tide < |
    |---|---|---|
    | (2229, 1228) | +0.0270 | 0.77 |
    | (2287, 1232) | +0.0075 | 0.58 |
    | (2333, 1233) | -0.0082 | 0.42 |

    The highest knob is the cormorant's perch. It stays uncovered at neap high water, which reaches about
    0.72; spring high water covers it. The tide here runs 0-1 at springs and about 0.28-0.72 at neaps
    (`day.py`).
  - **Dry top points for hauled-out seals** (the highest dry point in each 20 px column band):
    - tide 0.1: (2188,1235) (2209,1231) (2224,1226) (2230,1226) (2268,1231) (2278,1230) (2296,1231)
      (2329,1232) (2338,1231);
    - tide 0.3: (2209,1231) (2224,1226) (2230,1226) (2251,1232) (2278,1230) (2294,1232) (2329,1232)
      (2338,1231);
    - tide 0.5: (2224,1226) (2230,1226) (2287,1232) (2292,1232).
  - **For part 2.** `water.skerry_field()` returns the heights (nb 60 x na 150, `a` across -1..1 to the right,
    `b` along -1 near .. 1 far). The world point of a sample is `X0 + a*0.66*lx + b*0.32*fx` (and likewise
    Z), with `lx, lz = cos(az), -sin(az)`, `fx, fz = sin(az), cos(az)` and `az = atan2(X0, Z0)`; see
    `skerry()`. A seal lies dry where `h > (tide - 0.5) * TR` and should be drawn after `skerry()`.

**Draw order** (`bay`). The skerry, the floats and the buoys are drawn from the farthest to the nearest,
around the sailing boat or the moored boat at their waterline: `sea_marks(0, y_boat)`, `boats()`,
`moored_boat()`, `sea_marks(y_boat, 2)`. Part 2's boats and animals on the water should join this order by
their waterline. The beacon is drawn before the whale and the mist (`background`), so nearer things cover
it. The skerry, the floats and the buoys keep at least 0.03 of the frame from the sailing boat's route
(nearest: buoy 0 at 0.031; `tests/test_water.py` checks 0.025). The route's far leg passes 0.016 in front
of the beacon, so the boat sails past it on the near side. All of it keeps clear of the waters of the rare
events in `docs/SPOILERS.md`.

Helpers part 2 can reuse: `ball(L, R, x, yw, r, albedo, sub, shade)` (a floating ball and its reflection),
`reflect(R)` (composite a layer of mirrored shapes, broken by the ripples by wind), `local_shade(x, y)`
(the cloud shadow at a point of the sea, as `shade` for `self.lit`), `refl_amp()`, `tide_flow()`,
`set_on()`, `water_level()`, `mark_positions()`.

## Schedule and weather rules

Everything is a function of the date, the minute, the weather and the tide (`day.tide`, 0 low water, 1
high), so a given minute always renders the same (probe 2).

| what | shows when | driven by |
|---|---|---|
| cloud shadows (sun) | sun above -1 degree and any cloud layer with cover >= 1% | the sky's layers, threshold and drift this minute; the boost eases below a sun of 10 degrees |
| cloud shadows (moon) | night, moon above -1 degree, cloud about | the same, along the moon's direction; cut the moon's path |
| glassy water, cat's paws | wind below about 3.5 m/s (full below 2.2) | `wind_ms`, `wind_dir_deg`, the wind's run since midnight |
| lanes and slicks | wind above about 2.2 m/s | the same |
| rough all over | from 8 m/s, full at 12 | the same |
| whitecaps | from 7.5 m/s (a handful at 8, many at 13) | `wind_ms`; each lasts 4 minutes |
| glitter width and break-up | whenever the sun or moon path shows | `wind_ms`, the local roughness and cloud shadow |
| beacon, buoys, floats | always (outside reference mode) | |
| beacon light | dusk to dawn (`lights_on`), steady | the sun's altitude only |
| beacon waterline, skerry | always; the skerry covers above tide 0.77 | `day.tide` |
| floats' swing, lean, wakes, flag | always; wakes when the stream is over 0.2 | `tide_flow`, `wind_ms`, `wind_dir_deg` |
| breaking water over the covered skerry | covered within 0.045 units, wind over 3.5 m/s | `wind_ms`, the minute |

Measured on 2027-01-19 12:00 (synthetic): from one minute to the next the sea's shadow field changes by
0.11-0.17 on average (0-1 scale), about as much as the sky's own cloud cover changes (0.12). That is the sky's
existing pace; the shadows keep up with it.

## Probes

All run on the branch head's code (`1359a6f`); the doc commit changes no code.

1. **Tests.**

   `$PY -m unittest discover -s tests`:
   ```
   Ran 77 tests in 31.462s

   OK
   ```
   `tests/test_water.py` adds 13 of them:
   - places: every mark on open water and clear of the sailing route; `sea_point` inverts `proj`;
   - tide: the skerry covers and uncovers; the water climbs the beacon; the stream turns with the tide;
   - light: the cloud shadows follow the cloud and drift with it; the wind patterns by wind speed; the
     glitter narrows in a calm; whitecaps only in a blow; the beacon's light is steady;
   - reference: none of the water's methods run in reference mode.

   `$PY tests/test_shore_reference.py` (its watched drawers now include `beacon`, `beacon_glow`,
   `sea_marks`, `skerry`, `whitecaps`; two new cases, 2027-01-20 12:00 synthetic (a blow) and 2026-11-13
   12:00 synthetic (low water), which normal mode draws and reference mode must not):
   ```
   ok    test_reference_mode_draws_no_creature_or_rare_event (18.7s)
   ok    test_reference_mode_has_no_grain_and_holds_the_tide (0.2s)
   ok    test_reference_build_is_deterministic_and_leaves_the_tree_clean (47.1s)
   ok    test_existing_set (0.0s)
   4/4 passed
   ```
   `tests/test_shore_render.py` (fails 5 of 7 on `main`) was left alone. **PASS.**
2. **Determinism.** These were each rendered twice, one after the other, and every frame compared with
   `cmp`:
   - 2027-01-20 `--minutes 720-725 --weather synthetic --scale 0.75` (a blow: whitecaps, cloud shadows,
     rough water, every mark, the covered skerry in a breeze);
   - 2026-11-13 `--minutes 480-485 --weather synthetic --scale 0.375` (a calm morning with cat's paws).

   Result: `12 frames compared, 0 differ`. **PASS.**
3. **Shore reference.** `$PY tools/shore_reference.py out/water-dev/r2 --reference r2`:
   ```
   reference r2 written to .../out/water-dev/r2: digest 7cbee1f442afce967826b8e6f6aaffddd8921391b138a487f359b4d9024d35fa
   ```
   **PASS** (unchanged, so no r3).
4. **Cost.** Each run is one process per checkout, run in turn: `main` (`/Users/eddelord/Documents/Projects/listening_point`,
   at `adf7335`, the same renderer as `450163e`) against this worktree. The command was
   `nice -n 15 listening_point.py OUT --minutes 720-749 --scale 0.75 --jobs 1 --weather synthetic`
   (30 minutes with keyframes every 10, as the nightly job renders), timed with `/usr/bin/time -p`. Load
   5-9.

   | run | date | main real / user+sys s | branch real / user+sys s | ratio real / cpu |
   |---|---|---|---|---|
   | 1 | 2027-06-08 (broken cloud, 5.7 m/s) | 70.22 / 72.39 | 76.04 / 78.29 | 1.083 / 1.081 |
   | 2 | 2027-06-08 | 69.35 / 71.82 | 74.87 / 77.12 | 1.080 / 1.074 |
   | 3 | 2027-01-20 (a blow, whitecaps) | 69.32 / 71.65 | 75.09 / 77.84 | 1.083 / 1.086 |

   About **1.08** (limit 1.15). **PASS.** Per frame, about +0.19 s. A profile of one native frame (2027-06-08
   13:00): the sea 0.44 s against `main`'s 0.32 (glitter 0.067, wind 0.030, shadows 0.021, the rest in the
   mirror and shadow mixing); the skerry 0.031 s and the floats and buoys 0.020 s.

   **Peak memory**, one native frame (2027-06-08 13:00 synthetic, rendered in one process with its own
   keyframe), `/usr/bin/time -l` maximum resident set size, two runs each:
   - main 1,197,080,576 and 1,360,789,504 bytes;
   - branch 1,330,724,864 and 1,297,907,712 bytes.

   The means are 1279 against 1314 MB (+2.8%), but RSS swings by ±160 MB between runs here (6 GB of swap in
   use). The numpy allocation peak, measured with `tracemalloc` in the same script, does not swing: main
   1032.8 MB, branch 1048.1 MB, **+1.5%**. **PASS** (limit 15%). The keyframe's foreground still sets the
   frame's peak, not the sea.

## Look test

Folder `out/look/v3/water/` of the main checkout. `pair-<scene>.jpg` is the whole frame at Evan's
1440 x 900, with `main` on top and this branch below. `crop-<scene>.jpg` is the sea at native size, box
(1500, 1030, 2880, 1650), with `main` above this branch. Everything was rendered with
`listening_point.py --scale 0.75 --jobs 1 --quality 90`, one at a time.

| scene | when | what to look at |
|---|---|---|
| `cloud-shadows` | 2027-06-08 13:00 synthetic (low 0.42, 5.7 m/s) | Broken cloud at midday: lit patches far off and to the right, the near bay in the shadow the land is in too. The skerry and floats at low water. |
| `calm-morning` | 2026-11-13 08:00 synthetic (1.4 m/s) | Glassy water with soft darker cat's paws, a sharper reflection of the island. The hard line across `main`'s bay (y about 590 in the pair) is gone. |
| `breezy` | 2026-11-22 12:00 synthetic (6.3 m/s, low 0.22) | Lanes and slicks slanting along the wind (right half), cloud shadows drifting across, the dahn's flag streaming. |
| `blow` | 2027-01-20 12:00 synthetic (about 12 m/s, overcast) | Scattered white horses, crisp crests with broken foam, in place of `main`'s white noise blotches. A rough, darker sea. |
| `sunset` | 2026-11-22 15:40 fair (4 m/s, sun 2.4 degrees) | The sun's path, about `main`'s width at this wind. Faint streaks of cloud shadow fan across the bay from the sun's side. |
| `moonlight` | 2026-11-22 01:00 fair (moon 91%) | The moon's broken path by the pier, the beacon's steady red light and its reflection, the floats and buoys faint in the moonlight. |
| `low-water` | 2027-05-20 09:26 fair (tide 0.00) | The skerry dried out: wrack, the crusted knobs, the wash at its foot. The beacon's weedy foot shows. |
| `high-water` | 2027-05-20 15:43 fair (tide 1.00) | The skerry covered: at a spring high water it does not show at all, and the sun's glitter runs over it. The beacon's weedy foot is under water. |
| `flood-stream` | 2027-05-20 12:35 fair (mid-flood, stream about +1) | The floats dragged low with wakes trailing right, the dahn leaning, the pick-up buoys streaming right of the mooring buoys, a wash at the beacon's foot; two knobs of the skerry showing. |
| `fog` | 2027-03-21 10:00 fog | The beacon almost lost at about 140 m, the skerry, floats and buoys veiled by distance, calm water with paws. |
| `night-fog` | 2027-03-21 19:00 fog | The beacon's red light glowing through the fog with its reflection; the white buoy and the skerry dark shapes. |

## Known issues

- **The floats do not rise with the tide.** The sea is drawn as a fixed plane, and the boats and the pier
  stand on it. So the floats ride that plane, and the tide shows on fixed things instead: the beach (as
  before), the beacon's foot and the skerry. At the floats it shows in their swing (more slack at low water)
  and in the stream's lean and wakes. Drawn literally, a 1.5 m tide would lift buoy 1 about 34 px against
  the moored boat beside it, which does not move.
- **The cloud shadows are stretched** (`SHADOW_G` = 24), so they fall on the bay in patches. Seen from 15 m
  they would mostly be either everywhere or only on the horizon. They change from minute to minute as fast
  as the sky's clouds do, which is the sky's existing pace.
- **The heaps** (`cumulus.HEAPS`, off) are not in the sea's shadow field. If they come back, the sea shows
  the noise layers' shadows only.
- **Low sun.** At sunset, cloud shadows lie as long faint streaks fanning across the bay from the sun's
  side. This is real, but a new look; it is eased for a sun below 10 degrees.
- **Breaking water** over the covered skerry is white specks that change each minute, in a breeze only.
- **Small marks.** The pot floats are 10-12 px across at native size. They read as a line of orange dots at
  desktop size, but no closer. The beacon's can topmark is 8 px wide, too small for a cormorant at that
  distance; part 2 should perch it on the skerry's top knob.
- **The `cloud_beams` fix changes `main`'s look** on every cloudy frame with the sun up, below the horizon
  only. Reference frames are not affected.
- `tests/test_shore_render.py` still fails 5 of 7 (stale cairn fixture, on `main` too); not touched.

## Status

- 2026-11-03: built on `v3/water`. Probes 1-4 pass; the look test is in `out/look/v3/water/` (11 pairs and
  11 crops). Not merged, not installed. Reference r2 is unchanged.
- Next: the lead reviews the look test, then merges and installs. Part 2 (boats and sea life) builds on the
  positions and draw order above.
