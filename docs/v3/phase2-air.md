# v3 phase 2: things in the air

Branch `v3/air`, from `main` `4192c35`. Goal (Evan, 2026-11-01): "a bit livelier", not busier. Of the
sky items he picked: flocks (geese in a V in the migration months, starlings at autumn and winter
dusk, wheeling gulls) and things in the air (far aircraft and contrails when the air allows them, a
kite on windy days, a balloon on calm mornings). No people anywhere; everything lit by the scene's own
sun, moon and sky; nothing in the air at night but aircraft lights.

The clouds, sunbeams and the sunrise/sunset colour are another branch (`v3/clouds`); this one leaves
`sky.py` `clouds()`/`cloud_layer()`, `weatherfx.py` `light_shafts()` and the colour tables in
`core.py` alone.

## What was added

All drawing is in a new module, `renderers/procedural/air.py` (`AirMixin`, added to `Frame`). The
schedule is in `events.py` (`Schedule._air()`, plus `plane_enu()` and `balloon()`). The hooks:

- `sky.py` `sky()`: one line, `self.high_air(full)`, just before `self.clouds(full)`, so contrails and
  aircraft are under the clouds and any cloud in front of them hides them. **Merge note:** if
  `v3/clouds` changes the lines around `self.clouds(full)`, keep this call before the clouds are laid
  over `full`.
- `sky.py` `sky_extras()`: the old gull and geese strokes (24 lines) are replaced by
  `self.flocks()`; the meteors are untouched.
- `listening_point.py` `front()`: `self.air_kite()` with the other creatures (so never in reference
  mode); the kite's line has to cross the hill and the sea in front of the near scenery.
- `day.py` `_hold_still()`: clears every new schedule (`flights`, `contrails`, `starlings`,
  `balloons`, `kite`, `skeins`), so the shore's reference frames show none of it.
- `events.py` `sky_gulls()` now returns each gull's index, angle round its circle and turn, which the
  new drawing needs; the gull schedule itself (the main stream, `[seed, 1]`) is unchanged, so the
  observer's bedtime and everything else drawn from that stream are where they were.

Every new choice comes from its own seeded stream (`[date ordinal, 20..24]`, per-thing seeds and
per-minute `unit_hash`); nothing touches the frame's own random stream (`self.rng`, which feeds the
stars' twinkle and the grain). So a frame with nothing new in it is byte-identical to `main`'s (the
2026-11-01 19:30 look-test frame is), and a given date always renders the same.

### Geese (`air_geese`, `draw_goose`)

The old skeins were eleven thin ticks in a fixed V. Now each skein (the schedule's existing start
time, direction and height) gets, from stream 24: 9-23 geese, a split between the near and the far
arm (so the arms are uneven), a half-angle of 25-40 degrees, a heading 15-45 degrees off straight
across (so the V is seen obliquely and opens on the screen; the skein sinks as it crosses when it is
heading away and climbs when it is coming nearer), a crossing time of 11-17 minutes, a distance
(size), and in seven skeins of ten a straggler 1.6-2.8 places behind the end of the longer arm. The V
is laid out in plan and seen from below at the skein's own elevation; each goose wanders slowly off
its place (value noise over the crossing). Each goose is a body, a paler belly, a neck stretched out
ahead and a head, and two swept wings whose angle comes from its own wingbeat phase (a hash of the
skein, the goose and the minute), so the beats are out of phase. Half-span 11.5 px at full size
(8.6 px at 0.75). Lit as a dark grey-brown underside (`lit()` with a downward normal): dark against
a bright sky, near black at dusk.

### Gulls (`air_gulls`, `draw_gull`)

Same schedule as before (5-9 gulls a day, each wheeling round its own circle over the bay for half
an hour to two and a half hours). Each is drawn as a gull seen from below: a crooked wing (inner wing
up to the wrist, outer wing angled down and swept back), black wingtips, a mid-grey trailing edge,
a white body. The pose is mostly a glide, sometimes mid-beat up or down (per gull and minute). The
heading follows its circle, and it banks into the turn: the underside's normal tilts outward, and
where that faces the sun the underside lights up white (sun term `1.3 * max(0, n.sun)`); otherwise
it is in its own shade against the sky (ambient and ground bounce), so it reads as a grey gull with
black tips against a bright sky and flashes white as it wheels. At dusk they go dark. Half-span 17 px
at full size (was 14), each on its own small layer (the old code composited a 0.6 x 0.48 frame layer
every minute a gull was up; now about 1 ms).

### Starlings (`air_starlings`)

A murmuration of 8,000-16,000 birds over the far side of the bay (the lighthouse headland), drawn
as one folded sheet in 3-D: a disc of birds, stretched, bent, tapered and S-curved, with two
travelling folds out of its plane, then turned (yaw, pitch, roll). Where the sheet is seen edge-on,
the birds pile up into the dark bands a murmuration has; where it faces us it is a thin grain of
specks. Every shape parameter is smooth value noise over minutes (periods 3-11 min), so consecutive
minutes are close but a quarter of an hour later it is a different shape; now and then a part
(up to 30% of the birds) breaks away and rejoins. It gathers for the first 7-8 minutes (35% of the
birds, growing to all, the flock growing from 65% of its size), and in the last 9 minutes the birds
pour down in a funnel into the roost, behind the headland, which hides them. Drawn by vectorised
bilinear splatting (`np.bincount`) at 2x and box-reduced, a bird about 0.55 px of cover at 0.75,
`alpha = 1 - exp(-0.8 * birds per pixel)`; dark against the dusk sky with 22% horizon haze. About
1-5 ms a minute. The sea's reflection of the sky carries it too.

### Contrails and aircraft (`high_air`, `contrail_layer`, `plane_speck`, `plane_lights`)

Aircraft fly all day and night: straight tracks at 9.4-11.9 km, 12.6-14.6 km/min, on two airways
(headings 128/308 and 72/252 degrees, +-8) or (one in four) any heading, passing 15-90 km from
us, three in four of them on the south side we look at; 2.6 an hour from 05:30 to 22:30, 0.8 an hour
at night. Each is placed in the sky with the same altitude/azimuth mapping as the sun and stars,
including the earth's curvature. What is seen of them depends on the day:

- **A contrail day** (stream 20): the upper air is moist enough. From the forecast, without new
  fields: `moist = clip(1.4 * mean high cloud (06-21 h) + 0.25 * winter + 0.5 * max(0, mean RH - 0.55))`,
  and the day is a contrail day with probability `0.15 + 0.55 * moist` (not when low cloud averages
  over 0.8). `persist = moist * U(0.55, 1)` says how long trails last.
- Each trail is drawn behind its aircraft as gaussian splats along the track, sampled by age so
  neighbours overlap (geometric spacing, finer where the trail is thin): it forms a moment behind the
  aircraft (a small gap, then a thin bright line), drifts with the upper wind (the day's own drift,
  times 3.5, as `sky.py` moves its high cloud), spreads (`0.006 + 0.05 * persist` km a minute) and
  fades. Whether a piece of trail persists depends on where it was laid: a fixed noise field over the
  upper air, drifting with it, marks the moist patches (`0.12 + 0.5 * persist` of the sky); there a
  trail lasts `0.5 + 30 * persist^1.5` minutes (e-folding), elsewhere 0.4 min. So on the same day one
  aircraft leaves a long trail and the next only a short one, trails break off where the air dries,
  and two aircraft through the same patch both leave lasting trails. Older trails break into lumps
  and gaps along their length.
- The splats are binned by width into seven gaussian sizes (0.7-45 px), the wide ones on a 2x or 4x
  coarser grid, filtered and summed into an optical depth; `alpha = 1 - exp(-depth)`. Colour: the
  clouds' own lit/shade tables at the sun's altitude + 2 degrees (ten kilometres up, a trail keeps
  the sun a little longer: pink and gold after sunset), the sky's forward-scatter glow near the sun
  (`sun_glow`, as the clouds use), horizon haze, and at night nearly nothing unless the moon lights
  it (as the high cloud).
- The aircraft itself: a 1-2 px speck at the head of its trail, sunlit metal or dark against a
  bright sky. Not drawn on days without contrails (too small to notice).
- **At night** (sun below -3 degrees, not in heavy rain or snow), about half the flights show their
  lights: a steady red beacon, a dim white tail light, and a white strobe caught in about a third of
  the minutes. Under cloud they are hidden (they are drawn before the clouds).

Cost: 25-100 ms a minute on a contrail day at 0.75.

### Balloon (`air_balloons`, `draw_balloon`)

A hot-air balloon far off over the far coast (60%) or beyond the headland (40%). It rises from
behind the land after launch, over 14 minutes, to 0.39-0.49 of the frame's height, drifts with the
real surface wind (the day's own drift) and undulates a little, and sinks back out of sight in its
last 16 minutes. The envelope is drawn per pixel (sphere above, tapering to the mouth), with 8-16
gores in one of four colour schemes, turning slowly; lit by `light()` with the envelope's own normals,
so the morning sun lights the eastern side; the burner fires in about a third of the minutes while
climbing and an eighth while cruising, warming the envelope from inside and adding a small glow at
the mouth. Basket on two cables. Envelope radius 8.5 px at full size (about 15 px tall with its basket at 0.75):
small, as Evan asked, and readable as a balloon up close. Behind the far coast and the headland
(drawn before them), with a little haze.

### Kite (`air_kite`)

A diamond (two styles out of three) or a delta kite in one of four colour pairs, with a tail of
seven bows. The kite flies from just beyond the frame on the side the wind comes from: an east wind
blows toward the right of the frame, so the flyer stands off the left edge on the hill and the kite
is over the left hillside; a west wind puts the flyer on the shore off the right edge and the kite
over the headland's sky; a south wind (140-220 degrees) would carry it behind us, so no kite. The line
sags between the hand and the bridle and runs off the edge; the kite climbs in the first 4 minutes
and comes down in the last 4, flies higher in a stronger wind, wanders and wags (value noise); the
tail streams downwind and droops when the wind eases. Cloth lit on its face (normal toward the flyer
and down), plus sky light through it, plus the sun through it when the sun is behind it, so it glows
backlit. At 0.75 the diamond is about 34 px tall and the delta about 23 px tall and 42 px wide, the
tail three to four kite-lengths.

## Schedule rules (how often)

All per date, so a given day always has the same things at the same minutes.

| thing | when | how often |
|---|---|---|
| geese | the existing schedule: 1-3 skeins a day with probability `season.geese` (March and mid-October to mid-November), each between sunrise + 0.5 h and sunset - 0.5 h, 11-17 min to cross | see the year scan below |
| gulls | the existing schedule: 5-9 a day, each up 0.5-2.5 h between sunrise + 0.5 h and sunset - 1.5 h | every day |
| starlings | probability `0.4 * bump(doy, 268, 292, 405, 430)` (late September to early March, full from mid-October to early February); from sunset - 0.55..0.85 h to sunset + 0.1..0.25 h; dry, wind under 9 m/s, visibility over 5 km, no fog over that time | see the year scan below |
| contrails | a contrail day: probability `0.15 + 0.55 * moist` (above); trails by day (sun above -7 degrees), lit until the sun is 2 degrees further down than on the ground | see the year scan below |
| aircraft lights | every night that is not raining or snowing hard; about half of the night's flights; hidden by cloud | every night |
| balloon | probability `0.28 * bump(doy, 95, 120, 262, 290)` (April to mid-October); one balloon, two in 15%; launched sunrise + 0.05..0.6 h, up 0.9-1.6 h; only if over its flight the wind stays under 4 m/s, gusts under 7.5, dry, no fog, visibility over 8 km, low cloud under half | see the year scan below |
| kite | probability 0.45 of a session starting 10:00-15:00 (and at least an hour after sunrise), 1-2.8 h long (ending by sunset - 0.4 h, at least 45 min); flown only if over the session the wind averages 5 m/s or more, stays between 3.5 and 13 m/s, gusts under 18 m/s, from a steady direction that is not southerly, dry and no fog | see the year scan below |

Year scan (2026-11-01 to 2027-10-31, an early version of the rules; the balloon and starling
probabilities were lowered after it, to 0.28 and 0.4): synthetic weather gave contrail days 132,
starling evenings 53, balloon mornings 55, kite days 16, geese days 54; fair weather 180, 69, 73, 0
(fair days are never windy) and 54. Re-scan with the final rules is not done (see Status at pause).
On a contrail day a trail shows somewhere in the sky in about 50-70% of daylight minutes once cloud
has hidden what it hides (`fair` weather, 2026-11-05/14/19 and 2027-01-12).

## Probes

Run on this branch (the timing on `e2b6632` plus a line-wrap edit that keeps every random draw in order):

1. `$PY -m unittest discover -s tests`: `Ran 45 tests ... OK` (on `e6e8869` and again on `e2b6632`).
   Also `tests/test_shore_reference.py test_reference_mode_draws_no_creature_or_rare_event
   test_reference_mode_has_no_grain_and_holds_the_tide`: `2/2 passed`, with `high_air` and `air_kite`
   added to its watched drawers and five new cases (a contrail, a night flight, starlings, a balloon,
   a kite) that normal mode must draw and reference mode must not. `tests/test_astro.py` 42 checks 0
   failed, `tests/test_weather.py` 17/17. `tests/test_shore_render.py` 2/7, the same five failures
   on `main`'s code ("no spot passes for 2027-03-17-cairn", pre-existing, not from this branch).
2. Determinism: **not run yet.** The script is ready:
   `scratchpad/v3/air/tools/determinism.sh` (five minutes with something flying, rendered twice, `cmp`).
3. Shore reference: `$PY tools/shore_reference.py OUT --reference r2` from this tree printed
   `digest 7cbee1f442afce967826b8e6f6aaffddd8921391b138a487f359b4d9024d35fa`: **PASS** (run on the
   `e6e8869` tree; `e2b6632` changes only contrail, kite and gull drawing, which reference mode never
   reaches, but re-run it to be sure).
4. Render cost: `nice -n 10 $PY renderers/procedural/listening_point.py OUT --date 2026-11-05
   --minutes 720-779 --scale 0.75 --jobs 1 --weather fair --quality 90` (contrails, a skein of 23
   geese at 12:37, gulls), alternating `main` and this branch:

   | run | load (5 min) start/end | real | user |
   |---|---|---|---|
   | main 1 | 8.95 / 8.95 | 317.3 s | 228.6 s |
   | air 1 | 8.95 / 8.53 | 239.7 s | 195.2 s |
   | main 2 | 8.53 / 9.49 | 246.2 s | 196.6 s |
   | air 2 | 9.49 / 8.20 | 192.4 s | 166.3 s |

   Ratio air/main: 0.76 and 0.78 real, 0.85 and 0.85 user: **PASS** (at most 1.15). The branch is
   cheaper because the gulls now go on small layers (`main` composited a 0.6 x 0.48 frame layer for
   the gulls every minute one was up). Per call at 0.75, in one process: contrails 25-100 ms a minute,
   a murmuration 1-5 ms, the kite about 40 ms, gulls, geese and balloon 1-3 ms. The murmuration and
   kite hours were not timed as whole runs.

## Look test

Rendered with the CLI at the production size (`--scale 0.75`, 2880x1800, `--quality 90`, one frame per
process, so each has its own near-scenery keyframe), `main` (`~/Documents/Projects/listening_point`,
`4192c35`) against this branch, into the session scratchpad
`/private/tmp/claude-501/-Users-eddelord-Documents-Projects-cozy-cabin-claude/b85a93cd-3703-4aff-b84b-d9b69db72a54/scratchpad/v3/air/`:
`<n>-<scene>-a-before.jpg` / `<n>-<scene>-b-after.jpg`, and native-size crops `<n>-<scene>-crop.png`.

| n | scene | date, time, weather | pixels that changed by more than 12 (of 5.2 M) |
|---|---|---|---|
| 1 | geese | 2026-11-01 10:40 fair | 2,038 (the skein, a gull, leaves' JPEG blocks) |
| 2 | murmuration | 2026-11-12 16:00 fair | 16,342 (the flock and its reflection) |
| 3 | gulls | 2026-11-01 14:45 fair | 471 |
| 4 | contrails | 2026-11-05 12:43 fair (also a skein and gulls) | 33,581 |
| 5 | balloon | 2027-05-03 06:20 fair | 374 |
| 6 | kite | 2027-04-25 15:00 synthetic | 1,637 |
| 7 | noon | 2026-11-01 12:00 fair | 1,287 (a contrail low in the south; 2026-11-01 is a contrail day) |
| 8 | golden | 2026-11-01 16:00 fair | 2 |
| 9 | night | 2026-11-01 19:30 fair | 0: byte-identical file |
| 10 | fog | 2026-11-01 09:00 fog | 0 (the file differs only by a gull's faint JPEG trace in the fog) |

So nothing else moved: where no new thing is in the air the frame is the same as `main`'s.

What to look at (Evan): at a glance, the murmuration (2) and the contrails (4) read from across the
room; the geese (1) and kite (6) read as such at point size; the gulls (3) and the balloon (5) are
small on purpose and reward a close look (the balloon's gores and basket, the gulls' black tips and
the white flash of a banking gull).

## Known issues

- Contrails: a trail laid near overhead becomes a long arch across the 220-degree panorama (the
  projection does this to any straight line; the clouds fan the same way). Old, spread arches could
  read as a faint rainbow at dusk; shortened (`life` 30 min max, `A` 75 min) and broken up by the moist
  patches and gaps, but worth Evan's eye.
- Contrail days are picked partly from cirrus cover, and the cirrus then veils the trails somewhat
  (they are drawn under all clouds, the high ones included).
- The geese skein flies a mostly horizontal path while the V is drawn at a 15-45 degree heading;
  the skein drifts up or down a little to match, not fully.
- The kite is small (about 34 px tall at 0.75) and dark under overcast.
- `sky.py`: the one-line hook in `sky()` sits next to `self.clouds(full)`, which `v3/clouds` may touch:
  a likely merge conflict, trivial to resolve (keep the call before the clouds).

## Where to see each thing

All `--scale 0.75`, the weather mode given:

- Geese: 2026-11-01 10:40 fair; 2026-11-05 12:43 fair; 2027-03-17 08:05-08:50 fair.
- Murmuration: 2026-11-12 15:22-16:24 fair (best 15:50-16:10); 2026-11-04 15:35-16:36 fair;
  2027-01-15 15:41-16:30 fair.
- Gulls: 2026-11-01 14:44-14:48 and 08:25-08:29 fair (three up at once).
- Contrails: 2026-11-05 12:43 fair; 2026-11-19 08:30 fair (a fresh trail with its aircraft);
  2027-01-12 10:20 fair. Night lights: 2026-11-19 03:42 fair; 2027-01-12 17:15 fair.
- Balloon: 2027-05-03 05:59-07:17 fair (06:20); 2027-05-14 from 05:16 fair.
- Kite: 2027-04-25 14:07-16:39 synthetic (left, a delta); 2026-12-06 14:06-15:29 synthetic (right,
  a diamond, overcast).

## Status at pause (2026-11-01, Evan's restart)

- **Done, all six:** geese, murmuration, gulls, contrails (with aircraft and night lights), balloon,
  kite. Each drawn, scheduled, looked at at native size and in the full frame, and tuned once or
  more. Committed on `v3/air`.
- **Probes run:** 1 tests PASS; 3 shore reference digest PASS (on `e6e8869`); 4 timing PASS (0.76-0.85).
  **Not run:** 2 determinism (script ready, see Probes), and probe 3 again on the head.
- **Left:** run determinism and the digest on the head; re-scan a year with the final rules for the
  frequency table; time a murmuration hour and a kite hour as whole runs; a half-size (1440x900)
  look at the look-test pairs; optionally a dusk contrail look-test pair.
- **Open problems:** see Known issues (contrail arches, cirrus veiling trails, skein heading vs path,
  small kite, the `sky()` merge line).
