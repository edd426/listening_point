# v3 phase 5, part 3: echoes of the worlds

Branch `v3/story-echoes`, from `main` `7a969b1` (parts 1 and 2 merged). Evan asked, for phase 5, for "a story that
builds over weeks". Part 3 is its strand "echoes of the worlds: the listener's boat and life answer the shore's
history". The shore is a shared place where two agent worlds, each in its own repo, leave small objects. Its ledger
records two kinds of event:
- `add`: an object lands at `lands`;
- `sea`: the sea takes objects at `at`. That is a storm at 48 live objects, or the owner's veto, and the ledger
  never says which.

The listener lives aboard the boat moored at the end of the pier. The listener is never seen and never stands for
Evan. Their lamp (two lit panes in the deckhouse) is their own signal and is untouched here. The worlds render their
previews against the reference set (`--reference`), so the echoes are for Evan alone. They are absent in reference
mode, and the reference set stays bit-identical.

The listener answers through traces only, all on the boat:
- a **pennant** at the masthead in the colours of the newest thing on the shore;
- a **trip** out on the bay the day after the sea takes things;
- **washing** hung out on a quiet day.

## What was added

- `shore.py`:
  - `History`: the ledger as the echoes read it, in plain numbers. For each add: when it landed, its seq, its main
    colour, and when the sea took it. For each sea event: its time. No ids, makers, worlds or labels.
    `History.upto(t)` is the history as it stood at UTC second t.
  - `main_colour(p)`: the paint an object is mostly made of. It weighs each albedo by its pixel count times
    (0.25 + saturation), leaving out the label board.
  - `load_shore` hangs the history on the `ShoreDay` (`day.shore.history`).
- `story.py`: the echo strand.
  - `pennant_at(hist, t)` and `echoes(day, hist)` (an `Echo`), plus `wash_draws(D)`.
  - `Story._echoes` keeps `pennant`, `sail` and `washing`.
  - `Story.apply` sets `day.events.trip` when the boat goes out.
  - `EchoView.pennant_at(m)` and `washing_at(m)` read them at a clock minute. `NoStory` has none of them.
- `day.py`: the shore is loaded and the story built **before** the bay's plan (`SeaPlan`), because the plan keeps
  its yachts and creel boat clear of the sailing boat, which an echo may send out. `SeaPlan.__init__` reads nothing
  from the story (the pale seal's state is read per frame). The byte-identity probes below guard the reorder.
- `events.py`: `Schedule.window` holds the day's sailing times, drawn whether or not the boat goes.
  `Schedule.fit_to_sail(dep, ret)` is the schedule's own weather test, moved out of `__init__` unchanged.
- `props.py`:
  - `boat(..., pennant=None)` draws the pennant (`pennant()`), on the moored and the sailing boat;
  - `moored_boat()` draws the washing (`washing()`);
  - `downwind()` gives where the real wind blows them on screen.
- `tools/story_calendar.py --echoes --shore DIR` (and `--weather offline`).
- `tests/test_echoes.py` (17 tests).

New seeds, all in the story's range: 5518 the washing's day draws (times, and whether it is a washing day), 5531 the
washing's look, 5532 the pennant's ripple, 5533 the washing's sway. Nothing draws from an existing generator.

## The echoes

Coordinates are pixels of the production frame (2880 x 1800). The moored boat is 127 px from bow to stern, with its
masthead at about (2545, 1270). It faces left: the bow is toward the pier's end, the stern is on the right.

### The pennant: the newest thing on the shore

- **Fact.** The newest object still on the shore: landed (`lands` at or before now) and not yet taken (no `sea`
  event at or before now takes it).
  - If the sea takes the newest object, the pennant falls back to the newest one still there. When none is left,
    it comes down.
  - It also comes down once nothing new has landed for three days (`PENNANT_QUIET`), counting every arrival, even
    one since taken.
- **Look.** A narrow pennant, 0.23 x 0.05 of the boat (29 x 6 px), in the object's main colour.
  - It streams downwind from the top of the mast: a wind from the east blows it to the right, one from the west to
    the left. Wind blowing toward or away from you foreshortens it.
  - It lifts from hanging in a calm to flat out at 5 m/s or so.
  - It ripples, and each ripple is lit as cloth across the wind.
  - It flies on the sailing boat too.
- **When it changes.** From the minute an add lands, from the minute the sea takes something, and three days after
  the last arrival. The carrier lands objects at its morning pass, so in practice it changes in the night, at about
  03:30-04:30 local.
- **How often.** At about one object a day from each world it is always up, and changes colour about daily as the
  worlds alternate. A blue object gives a blue pennant against a blue sea, and tar gives a dark one.

### Out on the bay the day after the sea takes things

- **Fact.** A `sea` event at any time on the local date before. The response is the same whatever was taken (one
  object or a storm's eight and more) and whenever on that date: it cannot tell a storm from a veto.
- **Look.** The boat makes its usual trip round the bay. It uses the schedule's own departure and return
  (`Schedule.window`) and the schedule's own weather test (`fit_to_sail`: no rain, thunder, fog or snow, wind 10 m/s
  or less). That holds in any season, in winter too.
  - If the weather fails that day, it stays in. The response is for that day only.
  - If the schedule already sails that day, nothing changes.
  - Like every trip it ends half an hour before sunset, so the lamp's look, timing and meaning are as they were. The
    trip never depends on the lamp.
- **How often.** Storms start once 48 objects are live, about 24 days from an empty shore at two objects a day, and
  then come every four to six days. Vetoes come on top. In the synthetic steady state below there were 32 sea
  events in 180 days:
  - the boat went out on 21 of the days after them;
  - on 4 it sailed on its own (April);
  - on 7 the weather was unfit.

  So it shows mainly from October to April, four to six times a month. In summer the boat mostly sails anyway.

### Washing on a quiet day

- **Fact.** Nothing has landed since the start of the day before, up to the moment the washing goes up. There must
  also have been at least one arrival ever, so an empty ledger never hangs washing.
- **Draws.** Each date draws a hanging time (09:00-10:30) and a taking-in time (14:30-16:00, and at the latest half
  an hour before sunset). It also draws whether it is a washing day at all (`WASH_P` = 0.5). Without that draw, a
  shore whose worlds go quiet for a while would hang washing on nearly every dry day.
- **Weather.** No rain, drizzle, snow or thunder for its first hour, at least 3 C, and wind under 10 m/s. It is
  taken in at the first wet minute or a blow over 12 m/s. Only on a day the boat stays in.
- **Look.** Three or four pale, worn cloths (white, pale blue, grey, faded red, cream, sea-green) pegged on a line.
  - The line runs from the mast, 0.38 of the boat above the water, to a short pole at the stern. It is on the
    boat's right, away from the pier.
  - The cloths are 6-10 x 6-13 px. They blow a little downwind, and glow faintly when the sun is behind them.
- **How often.** Rare at the assumed pace. It needs both worlds to miss the morning pass two days running. In the
  synthetic steady state below (each world leaving something on 85% of mornings) it hung on none of 180 days. On a
  quiet shore it hangs on about half the dry days.

### The re-render rule and reference mode

- **Each echo at clock minute m reads only the ledger events at or before that minute's moment**, an add from its
  `lands` and a sea event from its `at`:
  - the pennant at m reads the events at or before m;
  - the trip on date D reads only sea events before D's midnight;
  - the washing reads only adds at or before its hanging time.

  That is exactly what `tools/nightly.py` relies on. When the ledger grows, it re-renders today and tomorrow only from
  the new event's moment on (`shore_sync.stale_from`). A sea event on date D therefore re-renders all of D + 1 (if it
  is tomorrow), which is where its trip shows.
- **Reference mode** has `NoStory`, so no echoes at all. In reference mode the trip is held off anyway
  (`Day._hold_still`).
- **No shore, or an empty ledger**, gives no echoes and makes no new draw: the frames are byte-identical to `main`.

## The calendar

`tools/story_calendar.py --echoes --shore DIR` prints what the boat shows on each date. That is the pennant's colour
(albedo) from each time it changes ("down" when it comes down), the trip with its times, and the washing. It builds
each date's whole `Day`, which takes about half a second. For real weather use `--weather offline`, which reads only
the weather cache.

The look test's synthetic shore, in fair weather. Two worlds each leave an object on the mornings of 16-22 November
2026. The newest is vetoed on the 22nd at 15:00. Nothing comes on the 23rd-26th, then one object each on the 27th
and the 28th.

```
$ ./venv/bin/python tools/story_calendar.py --echoes --shore out/look/v3/story-echoes/.caches/story --weather fair --from 2026-11-14 --days 18
weather fair; shore out/look/v3/story-echoes/.caches/story; from 2026-11-14 for 18 days. Times are local clock times.
2026-11-14 Sat  | -
2026-11-15 Sun  | -
2026-11-16 Mon  | pennant 00:00 down 03:30 #c43428 04:28 #e2ba34
2026-11-17 Tue  | pennant 00:00 #e2ba34 03:30 #2c5c9c 04:28 #287454
2026-11-18 Wed  | pennant 00:00 #287454 03:30 #c43428 04:28 #1c1a1a
2026-11-19 Thu  | pennant 00:00 #1c1a1a 03:30 #7e604b 04:28 #c43428
2026-11-20 Fri  | pennant 00:00 #c43428 04:28 #e2ba34
2026-11-21 Sat  | pennant 00:00 #e2ba34 03:30 #2c5c9c 04:28 #287454
2026-11-22 Sun  | pennant 00:00 #287454 03:30 #c43428 04:28 #e2ba34 15:00 #c43428
2026-11-23 Mon  | pennant 00:00 #c43428, out on the bay 9.81-15.50h (the sea took things yesterday)
2026-11-24 Tue  | pennant 00:00 #c43428, washing 09:10-14:44
2026-11-25 Wed  | pennant 00:00 #c43428 04:28 down, washing 09:18-15:28
2026-11-26 Thu  | washing 09:50-15:27
2026-11-27 Fri  | pennant 00:00 down 03:30 #e2ba34
2026-11-28 Sat  | pennant 00:00 #e2ba34 04:28 #2c5c9c
2026-11-29 Sun  | pennant 00:00 #2c5c9c
2026-11-30 Mon  | pennant 00:00 #2c5c9c
2026-12-01 Tue  | pennant 00:00 #2c5c9c 04:28 down

18 days; the ledger holds 16 adds and 1 sea events. Days with the pennant up 15, out on the bay after the sea 1, washing 3.
```

On the 20th the 03:30 arrival is red like the one before it, so no change shows. On the 25th the pennant comes down
three days after the last arrival (the vetoed one, at 04:28 on the 22nd). The 30th is quiet, but its draw makes it
no washing day.

**Synthetic steady state.** The kit's synthetic reference (`shorekit/tests/support.py`), with each world leaving one
object on 85% of mornings (seeded) from 2026-11-05 for 180 days. The kit's own storms make room. Synthetic weather.
- 301 adds and 32 storms; 45 live at the end.
- The pennant was up on all 180 days.
- The boat went out after the sea on 21 days: 4 in December, 5 in January, 4 in February, 6 in March, 2 in April.
- Washing hung on none of the 180 days.

## Probes

Run on 2026-11-04 on the renderer code of `3178557` (the commit after it adds only this doc and STATUS), one at a
time, `nice -n 15`, `--jobs 1`, with the load at about 5.

1. **Tests.** `$PY -m unittest discover -s tests`:
   ```
   Ran 135 tests in 181.028s

   OK
   ```
   That is 118 before, plus 17 in `tests/test_echoes.py`. Every ledger is synthetic, made at run time in a temporary
   folder in the kit's layout, against the kit's own synthetic reference. The tests cover:
   - the history: plain numbers in seq order, with no ids or names; the main colour leans to the saturated paint and
     skips the label;
   - the pennant:
     - up from the first landing's minute, not before;
     - the newest's colour, falling back when the sea takes the newest;
     - down three days after the last arrival, and down when nothing is left;
     - it streams to the right in an east wind and to the left in a west wind;
   - **no anticipation**, for every minute of a day and the day after, on two ledgers. One is a week from two worlds
     with a veto of the newest and a late arrival. The other is a full shore with a storm (48 live), a veto and a late
     arrival, and the day after. At each minute the pennant, the washing and where the boat is equal what the history
     cut at that minute's moment (`History.upto`) gives;
   - the trip:
     - the day after a veto and the day after a storm (which takes more than one object) it goes out, in January, on
       the schedule's own times, the same for both;
     - not the same day and not the day after that;
     - home half an hour before sunset;
     - in synthetic weather, only when the schedule's own test passes;
   - the washing:
     - on exactly the quiet days whose draw makes them washing days;
     - never with an empty ledger;
     - in synthetic weather never through rain or a blow;
   - **reference mode has no echoes** (a shore cache with history passed in: `NoStory`, no trip, no pennant, no
     washing);
   - **no shore and an empty ledger** have no echoes, the same trip, and identical frames (rendered in-process at
     three minutes on three dates);
   - drawing: the pennant and the washing change only pixels on and about the moored boat, and none of a shore
     object's pixels.
2. **Shore reference.** `$PY tests/test_shore_reference.py`:
   ```
   ok    test_reference_mode_draws_no_creature_or_rare_event (26.1s)
   ok    test_reference_mode_has_no_grain_and_holds_the_tide (0.2s)
   ok    test_reference_build_is_deterministic_and_leaves_the_tree_clean (45.9s)
   ok    test_existing_set (0.0s)
   4/4 passed
   ```
3. **Determinism.** Each set was rendered twice into two folders, one after the other, and every frame compared with
   `cmp` (`--scale 0.375 --jobs 1 --weather fair --quality 90`):
   - A: 2027-03-24 `--minutes 1058-1063`, the lead's set, with no shore;
   - B: 2026-11-24 `--minutes 720-725 --shore <the look test's synthetic shore>`: the pennant and the washing;
   - C: 2026-11-23 `--minutes 720-725`, the same shore: the boat out on the bay after the sea, its pennant flying.
   ```
   18 frames compared, 0 differ
   A: 1738.jpg ... 1743.jpg  (first frame's md5 5544144b3d2ab362604f651ee99a0c72)
   B: 1200.jpg ... 1205.jpg  (3411e7913f800f762480b9c36899b845)
   C: 1200.jpg ... 1205.jpg  (38a26a550bce708db13ca066de058932)
   ```
   A's md5 is the one part 2 recorded for the same set.
4. **Shore reference digest.** `$PY tools/shore_reference.py OUT --reference r2`:
   ```
   reference r2 written to .../r2: digest 7cbee1f442afce967826b8e6f6aaffddd8921391b138a487f359b4d9024d35fa
   ```
   Unchanged, so no r3.
5. **Byte-identical to `main` without echoes.**
   - `pair-noshore` (2026-11-22 12:00 fair, no `--shore`, `--scale 0.75`): the main and branch frames are
     byte-identical (`cmp` silent).
   - With an empty-ledger cache (`{"events":[],"shore_ledger":1}`, reference r2) the branch's frame at the same
     minute is byte-identical to main's without a shore.
   - So are all six frames of set A (main without a shore, the branch with the empty ledger).
6. **Cost.** `main` (`git archive main`) against this worktree, `listening_point.py OUT --date 2026-11-24 --minutes
   700-719 --scale 0.75 --jobs 1 --weather fair --quality 90 --shore <the synthetic shore>`. That is 20 minutes with
   two near-scenery keyframes; main draws the objects, and the branch also draws the pennant and the washing. CPU
   time is user + sys from `/usr/bin/time -l`, two rounds in opposite orders:

   | round | main real / cpu s | branch real / cpu s |
   |---|---|---|
   | 1, main first | 49.66 / 52.55 | 49.44 / 52.11 |
   | 2, branch first | 50.81 / 53.59 | 50.06 / 53.02 |
   | sum | 100.47 / 106.14 | 99.50 / 105.13 |

   **Ratio (CPU) 0.99** (limit 1.15). Peak RSS 1439-1526 MB on main and 1380-1579 MB on the branch (it swings by
   hundreds of MB between runs of the same code). `echoes()` takes 0.5-1.2 ms per Day, and `Story.cost_ms` is
   1.2-1.6 ms in fair weather with a shore of 16 or 301 adds.
7. **Privacy.**
   - Grepped `git diff main...HEAD` with `grep -F -f` against a pattern file built from a scratch copy of the live
     shore: its object ids, the objects' labels, their sha256s and commits. **0 matches.**
   - No test, doc or commit message holds anything read from the live shore. The look test reads a temporary copy
     at render time.

## Look test

Folder `out/look/v3/story-echoes/` of the main checkout. `look.py` there rebuilds it; `look.py plan` prints the
scenes.
- `pair-<scene>.jpg`: the whole frame at Evan's 1440 x 900, `main` on top and this branch below.
- `crop-<scene>.jpg`: a native-size crop of the boat's corner of the bay (or the boat, the pier and the shingle),
  main above the branch.
- `seq-story.jpg`: the branch at noon on ten dates, the boat at 2x, the date in its corner.

Rendering:
- Everything was rendered with `listening_point.py --scale 0.75 --jobs 1 --quality 90`, one at a time, in fair
  weather, except `real`.
- `main` is `git archive main`.
- The synthetic shores are built by `look.py` in the kit's layout against reference r2, with small made things
  (floats, crates, posts, cairns) in the palette's boat paints. They are stand-ins and garish; the shore objects are
  not under review here.

| scene | when | what to look at |
|---|---|---|
| `noshore` | 2026-11-22 12:00 | No `--shore`: byte-identical to `main`. |
| `first` | 2026-11-16 11:00 | The first object ever landed at 03:30. The branch flies a red pennant (its colour) at the masthead, streaming left in the westerly. |
| `week` | 2026-11-22 12:00 | Fourteen objects from two worlds. The pennant is yellow: the newest, the crate with a yellow frame on the shingle. |
| `sea-fallback` | 2026-11-22 15:10 | The newest was vetoed at 15:00 and is gone from the shingle in both. The branch's pennant fell back to the one before it (red). |
| `after-sea` | 2026-11-23 12:30 | The day after: main's boat is moored. On the branch the mooring is empty and the boat sails by the island. |
| `quiet` | 2026-11-24 12:00 | Nothing new since the 22nd. Washing on the line from the mast to the stern; the pennant is still up. |
| `quiet-down` | 2026-11-26 13:00 | Three days since the last arrival: the pennant is down. Washing. |
| `real` | 2026-11-04 14:00 | A copy of the live shore, real weather from a copy of the weather cache (`--weather offline`). The pennant in the colour of the newest object, hanging in the calm. |

`seq-story`, 20-29 November at 12:00:
- yellow, green and yellow pennants (20th-22nd, before the veto);
- the empty mooring (23rd, out on the bay);
- red and washing (24th);
- washing with the pennant down (25th, 26th);
- yellow again (27th), then blue (28th, 29th), and no washing.

## Known issues

- **The pennant is small.** It is 29 x 6 px on a 2880-wide frame (14 x 3 points on Evan's screen): a fleck of colour
  at desktop size that reads up close. Blue and tar objects make a pennant that is hard to see against the sea.
- **One pennant, one colour.** A many-coloured object gives its main paint, leaning toward a saturated one. Up close
  you match it to the object on the shore by colour alone.
- **It changes in the dark.** Arrivals land at the carrier's morning pass, so the colour changes at about 03:30-04:30
  local and shows from first light.
- **The trip is the ordinary trip.** The same route round the bay, on the schedule's own times. In summer the boat
  mostly sails anyway, so the echo shows from October to April. It is for the day after only: a sea event followed
  by unfit weather leaves no trip (7 of 32 in the synthetic steady state).
- **The washing is rare at the assumed pace.** It needs both worlds to miss two morning passes running (0 of 180
  synthetic days at 85% each). When the worlds go quiet for a while it shows on about half the dry days. The line's
  pole is drawn only with the washing.
- **The cloths are 6-13 px.** They read as washing up close and as a few pale specks at desktop size.
- **The boat itself is unchanged.** It is the same flat-shaded shape as before, and the pennant and the cloths are
  flat polygons in its style.
- **A real-weather trip reads the day's own forecast.** The schedule's sailing test runs on the forecast the day is
  rendered with. A forecast refreshed mid-day can change whether the boat goes, which is the same seam as v2's own
  trips.

## For Evan to judge

- **The pennant falls back when the sea takes the newest** (the lead's call). Storms take the oldest objects, so in
  practice only Evan's own veto of the newest object makes the pennant change colour back at that minute. The lead
  chose this so that a vetoed object's colour is not flown for three days, and only Evan sees live frames. Every
  other echo answers a storm and a veto alike.
- **Is the pennant worth it at its size** (`crop-first`, `crop-week`), or should it be larger, or two pennants (one
  per world)?
- **The trip after the sea** (`pair-after-sea`): readable at a glance as an empty mooring. Is going out in winter,
  four to six times a month, too much?
- **The washing** (`crop-quiet`, `crop-quiet-down`): pale cloths, half the quiet days. Too rare, or too domestic?

## Ideas not built

- **Dressed overall.** A line of small plain pennants from the bow to the masthead to the stern, the day after every
  50th arrival, about once every 25 days at two a day. A variant that builds up: a short flag line of the last eight
  arrivals' colours, newest at the top, in place of the single pennant. It would read at a glance, but it could read
  as a celebration or as clutter.
- **Stove smoke.** A wisp from a deckhouse stovepipe on cold mornings after an overnight arrival. Smoke reads as
  ambient life rather than as an answer.

## Status

- 2026-11-04: built on `v3/story-echoes`. Probes 1-7 pass (numbers above). The look test is in
  `out/look/v3/story-echoes/` (8 pairs, 8 crops, 1 sequence). Not merged, not installed. Reference r2 is unchanged.
- Next: the lead reviews the look test, then merges and installs.
