# v3 phase 4, part 2: boats and sea life

Branch `v3/sea-life`, from `main` `b547f81`, rebased onto `main` `614cd93` (the puddle fixes; no conflict).
Evan asked, for the sea, for more boats (fishing boats working, sailboats, a ferry to the island on a
timetable) and sea life (seals on the rocks, dolphins, gannets diving, a cormorant drying its wings). Part 1
(`docs/v3/phase4-water.md`) placed the marks they use: the pot floats, the skerry, the beacon. No people:
the wheelhouse and the ferry's windows are glass, lit at night.

## What was added

Two new modules:
- `renderers/procedural/seaplan.py` (`SeaPlan`): the day's plan for the bay. It is built in `day.py` after the
  mysteries (`day.sea`). In reference mode it is `NoPlan`, which has nothing in it.
- `renderers/procedural/sealife.py` (`SeaLifeMixin`, added to `Frame`): the drawing.

Hooks:
- `listening_point.py`'s `background()`: `far_sea()` (the ferry, the yachts, the gannets) after `sea()` and
  before `beacon()`. So the beacon stands in front of the ferry, and the mist and the far fog veil them by
  distance.
- `water.py`'s `bay()`: the creel boat, the dolphins and seals' heads in the water join the marks and the
  sailing boat in waterline order. With none of them present, `bay()` makes exactly the calls it made before.
- `water.py`'s `sea_marks()`:
  - `skerry_life()` (the seals hauled out, the cormorant) right after `skerry()`;
  - it leaves out the float the creel boat has aboard.
- `sea.py`'s `plan_emitters()`: the ferry's lights, so the sea mirrors them.
- `render()`: `sea_lights()` after `beacon_glow()`, so the ferry's lights dim and spread in fog.
- `day.py`: `tide_phase`, where the tide is in its half-day cycle (0 at low water). It changes nothing else.

Reference mode builds no plan and draws none of it. Nothing new draws from the frame's shared generator
`self.rng`. Each part of the plan has its own seed:
- 90 the ferry, 91 the creel boat, 92 the yachts, 93 the gannets, 94 the dolphins, 95 the cormorant;
- 98 the seals' swims;
- the seals' haul-outs are seeded by the low water's own count, `[n, 96, seal]` (see below).

**The boats** are small models in their own metres (`Model`, `Placed`):
- a hull from a few stations, boxes for the deckhouses, sticks for masts and davits, flat two-sided sails;
- placed on the sea plane and projected with the frame's own camera (`proj`), so they turn and foreshorten
  as they would;
- each face is lit by its normal (`lit`), with the cloud shadow on the water where they are (`local_shade`)
  and a little haze by distance;
- an ink edge round each box face and the hull's silhouette, and the top edge of each upright face catching
  the sky (the bench's trick);
- in the water: a dark waterline with a lap of foam, a bow wave, two wake arms and broken churned water
  astern when moving, and a reflection broken by the ripples (`reflect`).

**The animals** are sprites (`fauna.Sprite`, as the hillside's), drawn larger than life so they read: the
seals and the cormorant 1.9x, seals' heads 2x, dolphins 2x, gannets 3x.

Coordinates are pixels of the production frame (`--scale 0.75`, 2880 x 1800), x from the left, y from the
top; the horizon is y 1044. World units are those of `proj` (1 unit = 15 m).

### The island ferry

- **Way** (`seaplan.FERRY_WAY`, waterline): in from beyond the right edge (the mainland slip is just out of
  sight), along the far bay, past the beacon's column on its far side, on a little way, then a turn to
  starboard and away into the island's harbour on the horizon. The harbour's mouth opens to the east.

  | minutes in | x, y | distance | length on screen |
  |---|---|---|---|
  | 0 | 3096, 1064 (off the edge) | 42 units | 42 px |
  | 3.5 (enters) | 2890, 1069 | 34 | 53 |
  | 12 | 2326, 1081 | 23 | 78 |
  | 21 (the beacon's column) | 1722, 1099 | 15.5 | 116 |
  | 22 (on past it) | 1666, 1096 | 16 | 110 |
  | 26 (turned, running off) | 1654, 1070 | 33 | 54 |
  | 28-34 (fading into the harbour) | 1664-1673, 1059-1047 | 59-244 | 31-7 |

  - **Beyond the beacon.** At the beacon's column the ferry's waterline is y 1099, beyond the beacon's foot
    (1134), and the beacon's post and topmark stand in front of it.
  - **To port.** On the way in the beacon lies on its port side (tested). On the way back the same way is
    run in reverse.
- **Model** (`ferry_model`): 36 m long, 9 m beam, a black hull with a red boot top, a white lounge, an upper
  deck and a bridge with rows of windows, a buff funnel with a black top, and a mast. At the beacon it is
  about 116 px long and 55 px to its masthead.
- **Pace.** It crosses the near bay at a steady 0.10 radian of the view a minute (about 65 px a minute, under
  a hull length). After the turn it runs off at a quarter of its distance a minute, so it shrinks steadily
  toward the horizon. In the last 6 minutes it fades into the harbour. A crossing takes 34.5 minutes, about
  25 of them in view.
- **After dark** (`ferry_lights`, `sea_lights`, `sea_emitters`):
  - the windows glow warm;
  - the navigation lights keep their real arcs: the masthead light from ahead to 22.5 degrees abaft the beam;
    the sidelight on the side we see (red to port, green to starboard), both when it comes head on; the stern
    light from astern;
  - they are drawn after the fog and mirrored in the sea.

### The creel boat

- **Model** (`creel_model`): a 7.5 m creel boat.
  - a red hull with a white rubbing strake and black boot top, a rust weep or two;
  - a white wheelhouse with a raked windscreen, a door aft and a lifebuoy;
  - a mast with a radar bar, the hauler's davit on the starboard bow;
  - a stack of creels aft, tyres hung over the side.

  At the pots it is 130-153 px long, 61-72 px to the wheelhouse roof, 100-119 px to the masthead.
- **Its morning** (`SeaPlan._creel`, `creel_pose`):
  - It comes round the point from behind the hill: from (1440, 1237), out of sight, by (1685, 1255) and
    (1800, 1289) to the dahn.
  - It hauls the string in toward the shore, each pot in turn: alongside (1 minute), hauling (2-3 minutes),
    setting the pot again (1 minute, with a splash), on to the next (1 minute). While it hauls, the float is
    aboard: `sea_marks` leaves it out, a rope runs from the davit to the water, and in the last part the pot
    hangs at the davit.
  - It lies head to the tidal stream and the wind (`set_on`), turned at most 30 degrees off broadside to us so
    it stays readable.
  - It turns, and goes back out beyond the floats, by (2030, 1312), (1800, 1282) and (1665, 1251), round the
    point. The whole visit is 47-52 minutes.

### Extra yachts

- **Model** (`yacht_model`): a 10 m sloop.
  - hull white, navy, dark green or red; a coachroof; a 14 m mast;
  - a mainsail and a jib, white or (one in four) tan;
  - the sails swing out to leeward by the wind's angle (8-80 degrees), and the boat heels to leeward by the
    breeze (up to 18 degrees).
- **Lanes** (`YACHT_LANES`, waterline), one leg each, at a steady pace:
  - **far**: along the left of the bay in front of the far coast, behind the tower and the tree, from
    (-202, 1065) to (1627, 1072). Hull 12-17 px, mast 20-27 px. 80-120 minutes end to end.
  - **bay**: across the outer bay right of the beacon, from (1800, 1112) to (3082, 1102). Hull 34-40 px, mast
    55-64 px. 55-85 minutes.
- **Course.** Each goes whichever way along its lane is not within 50 degrees of the wind. It takes its seed's
  pick when both will do.

### Seals

- **Spots** (`SEAL_SPOTS`, on part 1's skerry field):

  | seal | spot (x, y) | dry while the tide is below |
  |---|---|---|
  | 0, the pale cow | (2286, 1232), the middle knob | 0.58 |
  | 1 | (2332, 1233), the right knob | 0.42 |
  | 2 | (2198, 1237), the left of the shelf | 0.39 |
  | 3 | (2250, 1241), the front of the shelf | 0.37 |

- **Look** (`draw_seal`): grey seals, about 52 px from the hind flippers to the nose (1.9x).
  - **The pale cow** is the recognisable one: silvery cream, blotched dark. She always lies on her own knob.
    This is phase 5's "a seal returns to the same rock".
  - **The others** are blue-grey or brownish.
  - **Poses** change every 6 minutes: flat, the "banana" (head and tail up), head up, or scratching with a
    fore flipper.
  - **Wet or dry.** Just hauled out, a seal is darker with a bright sheen of sky along its back; it dries to a
    soft gleam as the water drops away.
- **In the water** (`seal_heads`, `draw_seal_head`): a head up, about 2x. It has a round crown, a long muzzle
  and a wet gleam, with a lap of foam and a reflection. It is seen:
  - by its spot just before the seal hauls out and just after it slips off (only while the tide is running);
  - on 2-6 short swims a day near the skerry (`seal_swims`).

### The cormorant

- **Where:** the skerry's top knob, (2229, 1228), dry while the tide is below 0.77. It is there only while the
  knob stands at least 0.004 units (6 cm) clear.
- **Look** (`draw_cormorant`): about 20 px tall, 27 px across its spread wings (1.9x). Black-brown with a
  bronze sheen on the wings, a pale chin, yellow at the base of the hooked bill.
- **Poses**, in 5-minute blocks:
  - wings held out to dry (likely at the start of a visit);
  - folded;
  - preening;
  - it changes the way it faces every 13 minutes.

### Gannets

- **Where:** a patch of the outer bay right of the island, x 2405-2779, waterline y 1102-1121 (11-17 units
  out).
- **Each bout:** 3-7 birds circle 12-30 m up, on rings of 9-36 m.
- **Each minute,** each bird does one of these:
  - flies (long narrow wings with black tips, a pointed tail and bill; the span foreshortens as it turns,
    and the wings beat now and then);
  - folds into a white arrow, straight down at the sea (8%);
  - hits the water: a ragged plume with spray and a ring of white water (6%).

  The minute after a dive it is a fading ring of foam, or the bird sitting on the water.
- **Size:** 3x, up to 19-25 px across.

### Dolphins

- **Where:** a pod of 4-8 crosses the bay beyond the skerry: y 1159-1202 (about 6 units out), from x 2995 to
  1728 or the other way, over 26-42 minutes.
- **Each minute,** each dolphin is one of:
  - an arched back with a tall falcate fin (30%);
  - the fin and back going down (18%);
  - rising with a soft blow (12%);
  - now and then a leap with spray (1.5%);
  - or under.
- **Size:** 2x: a back of about 27 px and a fin of 7 px, dark grey with a paler flank and a wet gleam, foam
  where it breaks the water, and a reflection.

## Schedule and weather rules

Everything is a function of:
- the date (and its weekday);
- the minute;
- the weather (`day.wx`);
- the tide (`day.tide`, `day.tide_phase`).

So a given minute always renders the same (probe 2). Things that move are placed so that from one minute to
the next they move at most about their own length (tested for the ferry). Boats move slower than life, as the
sailing boat always has. The ferry's near crossing is about 1.5-4 km/h. The creel boat takes about 45 minutes
over five pots.

**Keeping clear** (`SeaPlan.clear_of`, every minute): a new boat's screen box must not meet another's. Where it
would, the new thing is moved or dropped:

| new thing | keeps clear of | if it would meet |
|---|---|---|
| ferry | the sailing boat, the ships on the horizon | runs up to 24 minutes late (3-minute steps), else drops that crossing |
| creel boat | the sailing boat | 25-75 minutes earlier or later |
| yachts | the sailing boat, the ships, the ferry, the creel boat, each other | moved by up to an hour, else none |
| gannets | the sailing boat, the ships, the ferry, the yachts | that bout is dropped |
| dolphins | the sailing boat, the ferry, the creel boat, the yachts, the gannets | none that day |

On the few days a rare event in `docs/SPOILERS.md` uses the bay, nothing new is scheduled around it
(`SeaPlan.quiet`), and the dolphins keep away that day. The ferry, the creel boat, the yachts, the dolphins and
the gannets keep clear of those waters.

| what | shows when | driven by |
|---|---|---|
| ferry | timetable (below); one round trip fewer on Sundays; none in a gale (wind over 15 m/s or gusts over 22 during the crossing) or thick fog (`fog` over 0.5, about 500 m); lights after dark (`lights_on`) | the date, the weekday, `wind_ms`, `gust_ms`, `fog` |
| creel boat | Tuesdays, Thursdays and Saturdays in the season (late March to November); Saturdays only in winter; three weeks in four; starts between sunrise + 0.5 h (not before 06:00) and 10:30; not in wind over 10 m/s, gusts over 15, fog over 0.3, visibility under 2 km, rain, thunder | the date, the weekday, sunrise, the weather over the visit |
| yachts | some fair days with a sailing breeze: chance 0.6 x the season (spring to autumn; 0.12 in winter); one, or two (35%); between 10:00 and 16:30, an hour and a half after sunrise to half an hour before sunset; wind 2.8-9.5 m/s, gusts at most 14, no rain or fog, visibility 8 km or more | the season, `wind_ms`, `wind_dir_deg` (course, sails, heel), `gust_ms`, rain, fog, visibility |
| seals hauled out | each low water (counted across days, so a haul-out over midnight is the same on both sides): the pale cow comes to 65% of low waters, the others 40, 30, 20%; fewer in 11-15 m/s, none above. A seal lies out while its spot stands far enough above the water: the cow 27-60 cm, the others 6-24 cm, a depth drawn for each low water | `day.tide`, `day.tide_phase`, `wind_ms` |
| seal in the water | by its spot for the last 3-7 cm before hauling out and after slipping off (while the tide runs); 2-6 swims a day of 3-7 minutes between 05:00 and 21:00 | the tide, the date |
| cormorant | 0-3 visits a day, 25-90 minutes, between sunrise + 0.6 h and sunset - 0.4 h, at least 30 minutes apart; only while its knob is dry; not in wind over 14 m/s or rain | the date, `day.tide`, `wind_ms`, rain |
| gannets | in season (rising through April, gone by early November): chance 0.45 x the season; one or two bouts of 15-37 minutes between 07:00 (or sunrise + 1 h) and 18:30 (or sunset - 1.5 h); not in wind over 12, fog, visibility under 5 km, rain | the date, the weather |
| dolphins | rare: chance 1.2% a day plus 5% at the height of summer and autumn; 08:30-16:30, 26-42 minutes; not in wind over 10, fog, visibility under 4 km, rain | the date, the weather |

**Ferry timetable** (local clock; mainland departures leave the right edge, island departures leave the
harbour):

| season (day of year) | from the mainland | from the island |
|---|---|---|
| summer (152-258, June to mid-September) | 08:00, 13:00, 19:00 | 09:45, 14:45, 20:45 |
| spring (91-151) and autumn (259-304) | 08:30, 13:30, 17:30 | 10:15, 15:15, 19:00 |
| winter (305-90) | 09:00, 15:30 | 10:45, 17:00 |

Each crossing leaves 0-3 minutes late (seeded), plus any delay to keep clear. On Sundays the first round
trip does not run. The winter afternoon and the late summer evening crossings are in the dark.

**Probe 5: how often each shows.** `tools/sea_schedule.py` walks every minute of a sample of dates and counts
the minutes each thing is in view. "In view" means:
- the ferry and yachts inside the frame;
- the creel boat out from behind the point;
- seals or the cormorant drawn.

It also counts how many of the eight show at once in daylight (sun above -4 degrees). This run covers the 1st
and the 15th of every month of 2027 in synthetic weather:
`$PY tools/sea_schedule.py --weather synthetic`:

```
weather synthetic; minutes in view per day (all 1440 / daylight, sun above -4 deg)
date               ferry        creel        yacht    seals out seal in wate    cormorant      gannets     dolphins   at once in daylight: 0/1/2/3/4+
2027-01-01 Fri   122/92         0/0          0/0        288/87       109/26         0/0          0/0          0/0        69/26/6/0/0 %
2027-01-15 Fri   122/92         0/0          0/0        387/156      116/56         0/0          0/0          0/0        52/42/5/0/0 %
2027-02-01 Mon   122/96         0/0          0/0        426/107      168/39         6/6          0/0          0/0        69/21/9/0/0 %
2027-02-15 Mon   122/116        0/0          0/0        316/194      103/44         0/0          0/0          0/0        56/34/10/0/0 %
2027-03-01 Mon   122/122        0/0          0/0          0/0         25/18        59/59         0/0          0/0        72/27/1/0/0 %
2027-03-15 Mon   122/122        0/0          0/0          0/0          9/9          0/0          0/0          0/0        83/17/0/0/0 %
2027-04-01 Thu   183/183        0/0          0/0          0/0         16/16        25/25         0/0          0/0        73/26/1/0/0 %
2027-04-15 Thu   152/152        0/0          0/0        415/264       71/58         0/0          0/0          0/0        51/43/6/0/0 %
2027-05-01 Sat   183/183       41/41         0/0         13/13        16/16       126/126        0/0          0/0        64/30/5/0/0 %
2027-05-15 Sat   183/183       42/42         0/0        272/272       66/66        64/64        55/55         0/0        49/33/15/3/0 %
2027-06-01 Tue   183/161       41/41         0/0        447/437       75/57         0/0         25/25         0/0        40/46/13/0/0 %
2027-06-15 Tue   183/171       41/41         0/0        279/271       62/53         0/0          0/0          0/0        57/35/7/1/1 %
2027-07-01 Thu   183/174       41/41         0/0        517/474      116/86        48/48         0/0          0/0        38/44/16/2/0 %
2027-07-15 Thu   183/168        0/0          0/0        237/207       64/44        88/88        49/49         0/0        53/38/8/1/0 %
2027-08-01 Sun   122/92         0/0          0/0        296/115       68/47        89/89         0/0          0/0        69/26/4/1/0 %
2027-08-15 Sun   122/92         0/0          0/0        559/399       62/55        41/41        22/22        28/28       42/46/11/1/0 %
2027-09-01 Wed   183/153        0/0          0/0        495/283       52/30       116/116        0/0          0/0        50/33/17/1/0 %
2027-09-15 Wed   183/134        0/0          0/0        601/317       53/27         0/0          0/0          0/0        49/42/9/0/0 %
2027-10-01 Fri   152/122        0/0          0/0        262/248       83/62         0/0          0/0          0/0        54/35/11/1/0 %
2027-10-15 Fri   152/122        0/0          0/0        533/257       53/27         0/0          0/0          0/0        46/50/4/0/0 %
2027-11-01 Mon   122/92         0/0          0/0        483/240       82/23        46/46         0/0          0/0        55/30/12/3/0 %
2027-11-15 Mon   122/92         0/0          0/0        518/253       58/45        55/55         0/0          0/0        47/38/9/6/0 %
2027-12-01 Wed   122/92         0/0          0/0        250/250       20/17        65/65         0/0          0/0        47/31/22/0/0 %
2027-12-15 Wed   122/92         0/0          0/0        176/0         21/7         84/84         0/0          0/0        68/30/1/0/0 %
mean/day         149/129        9/9          0/0        324/202       65/39        38/38         6/6          1/1
% of daylight         16.6%         1.1%         0.0%        26.0%         5.0%         4.9%         0.8%         0.2%
daylight minutes showing 0/1/2/3/4+ of them: 55.7% / 34.9% / 8.6% / 0.8% / 0.0%
```

The same dates in `fair` weather (`--weather fair`), totals:

```
mean/day         150/130       10/10        18/18       324/202       65/39        38/38        10/10         1/1
% of daylight         16.8%         1.3%         2.4%        26.0%         5.0%         4.9%         1.3%         0.2%
daylight minutes showing 0/1/2/3/4+ of them: 53.0% / 37.0% / 9.1% / 0.8% / 0.0%
```

The 24 sample dates catch no yacht day in synthetic weather, so here is every day of 2027 counted by what is
planned (the cormorant's visits show only while its knob is dry):

| weather | creel boat days | yacht days (two yachts) | gannet days | dolphin days | cormorant days | ferry crossings |
|---|---|---|---|---|---|---|
| synthetic | 82 | 38 (7) | 63 | 9 | 251 | 1636 |
| fair | 96 | 114 (26) | 77 | 8 | 262 | 1729 |

**Restraint.** In daylight:
- just over half the minutes show none of the new things;
- about 35-37% show one, 9% two;
- under 1% three or more.

The commonest are the seals (a quarter of daylight, quiet and still) and the ferry (a sixth; much of its
crossing far off). `tests/test_sealife.py` checks that three or more at once stay under 4% of daylight
minutes.

## Probes

All run on the branch head's code (`40fc096`, rebased on `main` `614cd93`); the doc commit changes no code.
Load 4-8 throughout, one render at a time, `nice -n 15`, `--jobs 1`.

1. **Tests.** `$PY -m unittest discover -s tests`:
   ```
   Ran 96 tests in 96.816s

   OK
   ```
   That is 77 before, plus 19 in `tests/test_sealife.py`:
   - plan: the same date gives the same plan; reference mode has an empty bay;
   - ferry: the timetable by season and Sundays; none in a gale; it passes beyond the beacon (y < 1125 at
     its column) with the beacon to port and ends at the harbour; no jumps between minutes;
   - creel boat: the weekly rhythm, mornings only, not in fog; every pot hauled with its float aboard and not
     drawn; drawn at the pots;
   - seals: hauled out only where dry; the pale cow's spot and how often she comes; a haul-out spans midnight
     the same;
   - the cormorant: only on a dry knob by day;
   - rare things: gannets in season, dolphins rare; nothing new on the bay around the rare event;
   - keeping clear: new boats never meet the sailing boat or the ships; restraint;
   - drawing: deterministic; an ordinary minute adds nothing.

   `$PY tests/test_shore_reference.py`:
   - Its watched drawers now include `far_sea`, `ferry`, `yachts`, `gannets`, `creel_boat`, `skerry_life`,
     `draw_seal_head`, `dolphins`, `sea_lights`.
   - Seven new cases, which normal mode draws and reference mode must not:
     - 2027-06-10 08:25 (the creel boat, the ferry);
     - 2027-01-19 17:24 (the ferry's lights, the pale seal);
     - 2027-05-20 08:15 (seals, the cormorant);
     - 2027-05-20 07:15 (a seal in the water);
     - 2027-05-20 16:00 (a yacht);
     - 2027-06-08 12:30 (gannets);
     - 2027-06-18 15:30 (dolphins).
   - The reference test also asserts the plan is empty.

   ```
   ok    test_reference_mode_draws_no_creature_or_rare_event (24.6s)
   ok    test_reference_mode_has_no_grain_and_holds_the_tide (0.2s)
   ok    test_reference_build_is_deterministic_and_leaves_the_tree_clean (46.8s)
   ok    test_existing_set (0.0s)
   4/4 passed
   ```
   `tests/test_shore_render.py` (fails 5 of 7 on `main`, stale cairn fixture) was left alone. **PASS.**
2. **Determinism.** These were each rendered twice, one after the other, and every frame compared with `cmp`:
   - 2027-06-10 `--minutes 480-509 --scale 0.75 --weather fair` (the creel boat hauling, the ferry crossing,
     the sailing boat);
   - 2027-05-20 `--minutes 435-444 --scale 0.375` (a seal waiting in the water, then hauling out);
   - 2027-01-19 `--minutes 1025-1034 --scale 0.375` (the ferry after dark, its lights).

   Result: `50 frames compared, 0 differ`. **PASS.**
3. **Shore reference.** `$PY tools/shore_reference.py out/sealife-dev/r2 --reference r2`:
   ```
   reference r2 written to .../out/sealife-dev/r2: digest 7cbee1f442afce967826b8e6f6aaffddd8921391b138a487f359b4d9024d35fa
   ```
   **PASS** (unchanged, so no r3).
4. **Cost.** Each run is one process per checkout, run in turn: `main`
   (`/Users/eddelord/Documents/Projects/listening_point` at `935d190`, which renders fair weather as `614cd93`
   does) against this worktree's code before the rebase (the same sea-life code). The command was
   `nice -n 15 listening_point.py OUT --minutes M0-M1 --scale 0.75 --jobs 1 --weather fair` (30 minutes, with
   keyframes every 10, as the nightly job renders), timed with `/usr/bin/time -p`.

   | run | date, minutes (what shows) | main real / user+sys s | branch real / user+sys s | ratio real / cpu |
   |---|---|---|---|---|
   | A | 2027-06-10, 480-509 (creel boat, ferry) | 71.46 / 73.92 | 72.68 / 74.16 | 1.017 / 1.003 |
   | B | 2027-05-20, 470-499 (seals, cormorant) | 76.38 / 78.52 | 79.72 / 80.82 | 1.044 / 1.029 |
   | C | 2027-06-08, 740-769 (gannets, seals) | 75.22 / 77.19 | 73.21 / 75.58 | 0.973 / 0.979 |

   At most **1.04** (limit 1.15). **PASS.** Building a day's plan adds about 0.05-0.1 s per process.

   **Peak memory**, one native frame (2027-06-10 08:22 fair, the creel boat hauling and the ferry, rendered in
   one process with its own keyframe):
   - `tracemalloc` peak: main 1044.0 and 1044.0 MB, branch 1044.2 and 1044.1 MB: **+0.02%**.
   - `/usr/bin/time -l` maximum resident set size: main 869.5 and 1166.0 MB, branch 1166.3 and 1008.0 MB.
     The means are +6.8%, but RSS swings by 300 MB between runs of the same code here (swap in use).

   **PASS** (limit 15%). The keyframe's foreground still sets the peak.

## Look test

Folder `out/look/v3/sea-life/` of the main checkout:
- `pair-<scene>.jpg`: the whole frame at Evan's 1440 x 900, `main` on top and this branch below.
- `crop-<scene>.jpg`: a native-size crop round the subject, `main` above the branch.
- The full renders are in `main/` and `branch/`. `look.py` there rebuilds the set.

Everything was rendered with `listening_point.py --scale 0.75 --jobs 1 --quality 90 --weather fair`, one at a
time.

| scene | when | what to look at |
|---|---|---|
| `creel` | 2027-06-10 08:22 | The creel boat hauling the third pot: its float aboard, the rope from the davit, the pot coming up; the other floats; the ferry crossing beyond and the sailing boat by the pier. At desktop size the red boat and white wheelhouse read at a glance. |
| `yacht` | 2027-05-20 16:00 | An extra yacht (red hull, white sails) in the outer bay in front of the island, at high water. |
| `yachts-far` | 2027-06-12 11:40 | Two small sails on the far lane: one tan-sailed off the left edge, one white by the lamp, in front of the far coast. The cormorant is on the knob, wings folded. |
| `ferry-day` | 2027-07-07 13:30 | The ferry mid-crossing, side on, in front of the island's reflection. The sailing boat is near the beacon. |
| `ferry-night` | 2027-01-19 17:24 | The ferry on its way back after dark: lit windows, its stern light and the light's reflection. |
| `ferry-turn` | 2027-01-19 17:10 | The ferry coming out of the harbour after dark, between the lamp and the beacon: its masthead light, both sidelights head on, lit windows. |
| `seals-out` | 2027-05-20 07:40 | Low water: the pale cow on her knob and two grey seals on the shelf. |
| `seal-in-water` | 2027-05-20 07:15 | A seal's head in the water by the right knob, waiting for it to dry. |
| `cormorant` | 2027-05-20 06:15 | The cormorant on the top knob, wings spread to dry, in the early sun. |
| `seals-cormorant` | 2027-05-20 08:15 | The busiest the skerry gets: three seals hauled out and the cormorant drying its wings. |
| `dolphins` | 2027-06-18 15:45 | Dolphins' backs and fins beyond the skerry, in the sun's glitter. |
| `gannets` | 2027-06-08 12:37 | Gannets over the outer bay right of the island: two plumes where birds have just gone in, one folded into a dive, others flying low. |
| `ordinary` | 2027-05-20 14:30 | High water, nothing new on the bay: byte-identical to `main` (max pixel difference 0). This is what most minutes look like. |

## Known issues

- **Slower than life.** Boats move slower than they would, as the sailing boat always has, so nothing jumps
  between minutes:
  - the ferry crosses the near bay at 1.5-4 km/h;
  - after its turn it shrinks by a quarter a minute rather than at a true speed (at the very end that is faster
    than a real ferry, but it is a few pixels by then);
  - the creel boat takes about 45 minutes over five pots.
- **Larger than life.** The animals are drawn bigger so they read: seals 1.9x, cormorant 1.9x, dolphins 2x,
  gannets 3x. Even so, at desktop size the seals and the cormorant are small (the pale cow reads; the grey
  seals are subtle), and the gannets flying near the horizon are white dashes; the splashes carry them.
- **Low-poly models.** The boats are flat-shaded, ink-edged models. Up close the wheelhouse and the ferry's
  decks are clean boxes: judge `crop-creel` and `crop-ferry-day` against "pasted-on CG". There is no
  weathering beyond a few rust weeps and the haze.
- **Ferry and beacon.** At the beacon's column the beacon stands in front of the ferry's hull for a minute or
  two (it passes beyond it, as asked).
- **No crossing in thick fog.** In moderate fog the ferry is mostly veiled beyond about 300 m, as the far scene
  is.
- **Seals and the weather.** They decide by the current minute's wind, so a wind rising past 11 or 15 m/s can
  send seals off mid haul-out.
- **The creel boat's heading** is turned at most 30 degrees off broadside to us, so it is not always fully head
  to the stream.
- **Yachts** sail one leg along their lane. They do not tack, and they choose a direction that is not into the
  wind.
- **Running late.** The ferry's crossings can run up to 24 minutes late to keep clear of the sailing boat and the
  ships, and one is dropped if that is not enough. The 2027 timetable has 1784 crossings: in fair weather 1729
  ran (55 dropped to keep clear), in synthetic weather 1636 (gales, thick fog and keeping clear).
- **Test time.** The unit tests now take about 97 s (31 s before): `tests/test_sealife.py` builds many days'
  plans.
- `tests/test_shore_render.py` still fails 5 of 7 (stale cairn fixture, on `main` too); not touched.

## Status

- 2026-11-03: built on `v3/sea-life`. Probes 1-5 pass. The look test is in `out/look/v3/sea-life/` (13 pairs and
  13 crops). Not merged, not installed. Reference r2 is unchanged.
- Next: the lead reviews the look test, then merges and installs. Phase 5 can build on the pale cow (seal 0,
  `SEAL_SPOTS[0]`), her low-water count (`SeaPlan.low_water`) and the creel boat's string.
