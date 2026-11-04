# v3 phase 5, part 2: animal lives

Branch `v3/story-lives`, from `main` `09fe743` (part 1 merged). Evan asked, for phase 5, for "a story that builds
over weeks. All of it is decided by the date, as the mysteries are, so a given day always renders the same." Part 2
is its strand "animal lives: lambs grow up, the cat has kittens, a seal returns to the same rock". It hangs its state
on part 1's story (`day.story`, `renderers/procedural/story.py`), and reads the weather of earlier days only through
part 1's `History` (the cache, never the network). No people: the sale, the new homes and the breeding colony all
happen offstage, and show as things that are there one morning and gone the next.

## What was added

No new module. `story.py` gains three strands, and the drawing goes where each animal already lives:
- `story.py`:
  - `flock_years(year)`, `litters(year)`, `seal_year(year)`: each year's draws (cached), from `LIVES_FROM = 2027`
    for the flock and the cat (before it the flock is phase 3's four ewes and there are no kittens); the seal's year
    needs no start;
  - `Story._flock`, `_kittens`, `_seal`: the state on a date; `NoStory` has an empty default for each (`lambs = ()`,
    `ewes = None`, `kittens = ()`, `kittens_in = False`, `pale = pale_before = None`, `sold = None`), so reference
    mode has none of it;
  - `lamb_size(age)`, `kit_size(age)`, `pale_state(date)`.
- `events.py`:
  - `Schedule.sheep(t, lambs=(), ewes=None)` replaces phase 3's `sheep(t, lambs=False)` and its fixed pair of lambs
    (`season.lambs`, mid March to May, is gone). Each sheep is now `(x, y, facing, grazing, size, view, who)`:
    `who` is None for a grown ewe, a kept ewe lamb's record in a ewe's place (a hogg), or a lamb;
  - `Schedule.lamb_at`: where a lamb is by its mother and what it is doing;
  - `snoise`: `vnoise` from the story's own seeds.
- `fauna.py`: `sheep()` draws the story's flock; `lamb()` and `draw_lamb()` the lambs; a hogg is a smaller ewe in
  a whiter fleece; the crows' "beside a sheep" spot uses the same flock.
- `life.py`: `kittens_now()` (where each kitten is), `kit_place()`, `kittens()` and `draw_kitten()`, drawn in
  `front()` right after the cat.
- `seaplan.py`: `SeaPlan.pale(m)`; `seals_at` and `seal_swim_at` leave the pale cow out while she is away, and bring
  her to every low water the first days she is back. `sealife.py`: `draw_seal(..., lean)`, the pale cow thin.
- `tools/story_calendar.py --lives`.

Nothing new draws from any existing generator. The story's seeds are `[5500 + strand, ...]`; part 2's are:
- 5509 phase 3's ewes' ages (once), 5510 each year's lambing (by the year), 5513 each year's litter, 5517 the pale
  cow's autumn;
- 5526 a lamb's wander, 5527 its pose and facing (by the date, the lamb, the minute), 5528 a kitten's play about its
  place, 5529 its pose and facing, 5530 a lamb's own look (its markings and curls, by the lamb: the same every day).

The ewes keep phase 3's draws exactly (their places, drift, folds, grazing): adding lambs moves no ewe (tested).

Coordinates are pixels of the production frame (`--scale 0.75`, 2880 x 1800), x from the left, y from the top.

## What the story shows

### The lambs, and the flock from year to year

- **The flock.** Four blackface ewes, phase 3's, each keeping her slot in the schedule's draws (`Schedule.sheep`:
  her place for the day, her drift, her fold, her grazing). The story gives each slot a ewe with a birth year: phase
  3's four were born 2022-2025 (seed 5509).
- **Lambing** (`flock_years`, seed 5510 by the year). The year's first lambs come between 25 March and 15 April (its
  tupping); each ewe lambs within 18 days of them. A ewe lambs first the spring she is two, so a hogg (a ewe lamb
  kept the autumn before) has none. Each lambing ewe has a lamb (barren with a chance of 0.1), twins with a chance of
  0.2; at most three lambs a year (Evan's restraint: phase 3 had two). A lamb is born in the night and shows from
  that morning.
- **Growing** (`lamb_size`): its size against a grown ewe's is `1 - 0.52 exp(-age / 130 days)`: 0.48 at birth,
  0.58 at four weeks, 0.66 at eight, 0.78 at sixteen, 0.82 at the sale. Its shape (`draw_lamb`) changes too, by
  `g = exp(-age / 40 days)` (1 newborn, 0.5 at four weeks, 0.06 at sixteen): a newborn is leggy (legs 0.39 of its own
  metre against 0.26 grown), short in the barrel (half length 0.42 against 0.56) and big-headed (1.52x against
  1.2x); week by week it gets longer and sturdier.
- **Look.** A tight white coat (whiter than the ewes'), scalloped along the back, with small curls; a blackface
  lamb's face and legs, black speckled with white in a pattern of its own, white patches at some knees; a long tail.
  Its markings and curls come from its own seed (5530), so it looks the same every day.
- **At her side.** Each lamb keeps to one side of its mother (a twin to the other), close at first (0.75 m from her
  middle) and farther as it grows (1.65 m from about 14 weeks), wandering a little (seed 5526). What it does changes
  every three minutes (seed 5527):
  - suckling (under eight weeks, while she stands side on): alongside her, facing her tail, its head up under her
    flank, its tail out;
  - lying down: often while it is small (45% of the time in its first three weeks), and always at night in the fold
    beside her, and in rain, snow or a strong wind while it is under eight weeks (pressed against her, in her lee);
  - grazing (from two weeks, when she grazes) or standing; it turns to face away from her now and then;
  - walking with her to the fold at dusk and out of it after dawn.
  It stays on her side of the field walls and out of the garden (`keep_to_field`), and walls, gates and rocks hide
  it as they hide her.
- **The sale** (`Story._sale`). The lambs are weaned and sold together: on the first day fit for work (part 1's
  `History.workable`: the hill can be gathered) from a date between 25 August and 18 September (seeded), or a day
  with no weather on record, and at the latest 21 days after that date. They show on that day and are gone the
  next morning. At about 19 weeks in the synthetic 2027.
- **A ewe lamb kept back** (chance 0.8 a year, when there is a ewe lamb): she stays, and the oldest ewe goes with the
  lambs, so the flock stays at four. She takes the old ewe's slot (her places in the schedule) the morning after the
  sale, as a hogg: smaller (her own `lamb_size`: 0.82 the morning after the sale, 0.93 by New Year, 0.97 by her
  first lambing season) and in a whiter fleece, until she is 540 days old; she lambs first the spring after next. So the flock's
  make-up carries from year to year: which slots lamb, how old each ewe is, who replaces whom.

### The cat's kittens

- **A litter** (`litters`, seed 5513 by the year) in some years (chance 0.5), born indoors on a date between 1 April
  and 9 June: two to four kittens, each with a coat (black like her 20%, black and white 30%, grey 15%, tabby 20%,
  ginger 15%: most can be told from her) and its own day for a new home at 70-84 days old (ten to twelve weeks).
- **Out from four weeks.** From 28 days old they come out with her (`life.kittens_now`): at the step (on the mat
  and beside it), in the grass by the tower, and from seven weeks also in the grass at the foot of the wall she sits
  on and in front of the bench. While she is anywhere else (indoors, by the lamp at night, and on the wall or the
  bench while they are small) they are indoors. When she moves, they follow, each a minute or two behind her at a
  kitten's pace, coming out and going in by the door. At dusk they go in. Each plays about its place (seed 5528) and
  changes what it does every three minutes (seed 5529): sitting, crouched to pounce (rump up, tail out), trotting
  with its tail straight up, or curled asleep (often while small).
- **Kept in.** On a day after a wet spell (8 mm of rain the day before, or 3 mm on each of the two days before:
  `History`, the cache only for real weather) the young ones stay indoors all day. The cat herself still goes in
  whenever it rains (her plan, as before).
- **Look** (`draw_kitten`): drawn as the cat is (her ellipses and lines, lit by the frame), in proportion to her
  (`kit_size`: 0.45 of her at four weeks, 0.7 at twelve), with a bigger head and ears; a bicolour's white bib, muzzle
  and front socks, a tabby's or a ginger's bars. They hide behind what stands nearer, and the cat hides the ones
  behind her.
- **New homes.** Each goes on its own day, between ten and twelve weeks: the litter thins over a week or two.
- **One stays** (chance 0.4 of a litter, once): one of a different coat from hers if the litter has one. It keeps
  near her as the kittens do, a little farther off, grows to her size by 300 days (`kit_size`) and into her shape,
  and from then on is the second cat, at her side wherever the kittens would be; its eyes catch the lamps as hers do.
  The first litter is 2028 (four, none stays); the 2029 litter's tabby stays (the litters do not depend on the weather).

### The pale seal's autumn

- **Away** (`seal_year`, seed 5517 by the year). In north and west Scotland grey seals pup mainly from September to
  late November, and haul out to moult between December and April (the Special Committee on Seals' main advice
  reports of 2009-2012, https://www.smru.st-andrews.ac.uk/files/2016/08/SCOS-2009.pdf and its siblings, as a web
  search summarised them; not read in full). A cow comes ashore at a breeding colony, nurses her
  pup for two to three weeks while she fasts, mates and leaves (the textbook figure; not checked against a source
  here). So in most autumns (chance 0.85) the pale cow (seaplan's seal 0) is gone from a date between 15
  September and 15 October, for 30-46 days. While she is away no seal lies on her knob (`SEAL_SPOTS[0]`) and her head
  is never one of those in the water; the other seals still come to their own spots as before.
- **Back.** From her return she comes to every low water for three days (as the wind allows: fewer in 11-15 m/s,
  none above), then to 65% of them as before. For 35 days she is thin from the fast (`draw_seal(lean)`): her back
  sunk by up to a quarter of its height, so her neck and head show, filling out day by day.
- **Across midnight.** A low water that began before midnight keeps the day before's state (`SeaPlan.pale(m)`), so a
  haul-out over midnight is one haul-out on both days, the nights she leaves and comes back included.

## The calendar

`tools/story_calendar.py --lives` prints only the lives: a line on each date they change (a birth, the sale, a kitten
gone to a new home, a wet spell keeping the kittens in, the seal away or back), and every Monday between, so the ages
can be read week by week. The lambs' ages are in weeks (the youngest to the oldest), a hogg's size against a grown
ewe's. The synthetic 2028 (its second year, with the hogg kept from 2027, the first litter and the seal's autumn):

```
$ ./venv/bin/python tools/story_calendar.py --lives --from 2028-01-01 --days 366
weather synthetic; from 2028-01-01 for 366 days. A date's line is what shows that day (from the days before it); 'work' means that day itself was fit for work, so its work shows the next morning.
2028-01-01 Sat  | hogg 2027-0a (0.93)
2028-04-06 Thu  | lambs 2 (0w), hogg 2027-0a (0.97)
2028-04-10 Mon  | lambs 2 (0w), hogg 2027-0a (0.97)
2028-04-13 Thu  | lambs 3 (0-1w), hogg 2027-0a (0.97)
2028-04-17 Mon  | lambs 3 (0-1w), hogg 2027-0a (0.97)
2028-04-24 Mon  | lambs 3 (1-2w), hogg 2027-0a (0.97)
2028-05-01 Mon  | lambs 3 (2-3w), hogg 2027-0a (0.97)
2028-05-08 Mon  | lambs 3 (3-4w), hogg 2027-0a (0.97)
2028-05-15 Mon  | lambs 3 (4-5w), hogg 2027-0a (0.98)
2028-05-22 Mon  | lambs 3 (5-6w), hogg 2027-0a (0.98)
2028-05-29 Mon  | lambs 3 (6-7w), hogg 2027-0a (0.98)
2028-06-03 Sat  | lambs 3 (7-8w), hogg 2027-0a (0.98), kittens 4 (4w)
2028-06-05 Mon  | lambs 3 (7-8w), hogg 2027-0a (0.98), kittens 4 (4w)
2028-06-12 Mon  | lambs 3 (8-9w), hogg 2027-0a (0.98), kittens 4 (5w)
2028-06-19 Mon  | lambs 3 (9-10w), hogg 2027-0a (0.98), kittens 4 (6w) kept in
2028-06-20 Tue  | lambs 3 (9-10w), hogg 2027-0a (0.98), kittens 4 (6w)
2028-06-26 Mon  | lambs 3 (10-11w), hogg 2027-0a (0.98), kittens 4 (7w)
2028-07-03 Mon  | lambs 3 (11-12w), hogg 2027-0a (0.98), kittens 4 (8w)
2028-07-10 Mon  | lambs 3 (12-13w), hogg 2027-0a (0.98), kittens 4 (9w)
2028-07-16 Sun  | lambs 3 (13-14w), hogg 2027-0a (0.99), kittens 3 (10w)
2028-07-17 Mon  | lambs 3 (13-14w), hogg 2027-0a (0.99), kittens 3 (10w)
2028-07-19 Wed  | lambs 3 (13-14w), hogg 2027-0a (0.99), kittens 2 (10w)
2028-07-24 Mon  | lambs 3 (14-15w), hogg 2027-0a (0.99), kittens 1 (11w)
2028-07-26 Wed  | lambs 3 (14-15w), hogg 2027-0a (0.99)
2028-07-31 Mon  | lambs 3 (15-16w), hogg 2027-0a (0.99)
2028-08-07 Mon  | lambs 3 (16-17w), hogg 2027-0a (0.99)
2028-08-14 Mon  | lambs 3 (17-18w), hogg 2027-0a (0.99)
2028-08-21 Mon  | lambs 3 (18-19w), hogg 2027-0a (0.99)
2028-08-28 Mon  | hogg 2027-0a (0.99)
2028-09-21 Thu  | hogg 2027-0a (0.99), pale cow away
2028-09-25 Mon  | hogg 2027-0a (0.99), pale cow away
2028-10-02 Mon  | hogg 2027-0a (0.99), pale cow away
2028-10-03 Tue  | pale cow away
2028-10-09 Mon  | pale cow away
2028-10-16 Mon  | pale cow away
2028-10-22 Sun  | pale cow back (0d)
2028-10-23 Mon  | pale cow back (1d)
2028-10-25 Wed  | pale cow back (3d)
2028-10-30 Mon  | pale cow back (8d)
2028-11-06 Mon  | pale cow back (15d)
2028-11-13 Mon  | pale cow back (22d)
2028-11-20 Mon  | pale cow back (29d)
2028-11-26 Sun  | -

366 days: 252 fit for work (69%), 1 with gusts of 20 m/s or more, 4 with an onshore blow of 8 m/s, 11 with snow lying.
days showing: wall 99, branch 9, logs 28, driftwood 24, drifts 4, spade 38, garden 110
lives: lambs 144, hogg 276, kittens 53, kept in 1, young cat 0, away 31 (days; 'away': the pale cow)
story per date: median 0.2 ms, max 172.2 ms (this process, its caches warm as it goes)
```

The years' draws, which do not depend on the weather (only the sale's day does):

| year | lambs (born) | ewe lamb kept, in whose place | litter (born; coats) | stays | pale cow away |
|---|---|---|---|---|---|
| 2027 | 3 (10-12 April; ewe 2's lamb over the cap) | 2027-0a, in ewe 0's (her own mother's) | none | | 20 Sep - 24 Oct |
| 2028 | 3 (6-13 April; none from the hogg) | none | 4 (6 May; 3 black and white, a ginger) | none | 21 Sep - 21 Oct |
| 2029 | 3 (11-18 April; twins from 2027-0a, now two) | none | 4 (4 May; 2 black and white, a tabby, a black) | the tabby | 15 Oct - 23 Nov |
| 2030 | 3 (6-16 April) | 2030-1a, in ewe 1's | 3 (8 April; a tabby, a grey, a black and white) | (one has stayed) | she stays |
| 2031 | 2 (13 April; none from the hogg) | 2031-0a, in ewe 3's | none | | 9 Oct - 12 Nov |

From `story.flock_years`, `story.litters` and `story.seal_year`. In the synthetic weather the sale fell on 25 August
2027, 27 August 2028 and 12 September 2029 (the lambs gone the next morning); the young kittens were kept in on 1 of
2028's 57 days out and 15 of 2029's (a wet summer).

## Probes

Run on 2026-11-04 on the renderer code of `0b69d2a` (the later commits change only `tests/test_lives.py`, before the
full test run, and this doc), one at a time, `nice -n 15`, `--jobs 1`, with the Mac quiet (load about 3).

1. **Tests.** `$PY -m unittest discover -s tests`:
   ```
   Ran 118 tests in 109.177s

   OK
   ```
   That is 106 before, plus 12 in `tests/test_lives.py`:
   - lambs: their size rises every day of their age, from under 0.55 to over 0.75, and they are all gone by 20
     October (and never before 20 March), never more than three; a lamb keeps its mother, side, seed, birthday and
     sex from day to day, and the ewe lamb kept back is the hogg in the flock the morning after the sale; four ewes
     always, and a hogg never lambs the spring after she was kept; each lamb is within a few metres of its mother and
     on her side of the field walls, and adding the lambs moves no ewe;
   - kittens: out only in a litter year (or the one that stayed), from four weeks to each one's own day for a new
     home, 2-4 of them, gone after the last one's day; the same kittens from day to day, never one back; settled
     kittens within eight of the cat's size units of her, none while she is indoors or by the lamp, none from a
     quarter of an hour after dusk; none of the young ones out on a day after a wet spell;
   - the pale cow: no seal 0 on the rock or in the water while she is away (the low water carried over from the night
     before she goes aside), on her knob at a low water the day she is back, untouched by the story five days before
     she goes; a haul-out across the midnights she goes and comes back is the same on both sides;
   - reference mode has no lives (story, `sea.pale()`, `kittens_now()`); the story's lives are deterministic.

   `tests/test_fauna.py` uses the new `sheep()` (the story's lambs instead of `lambs=True`).
2. **Shore reference.** `$PY tests/test_shore_reference.py`. `kittens` is now one of the watched drawers, with a new
   case, 2028-06-15 11:45 fair (the kittens at the step, the lambs), which normal mode draws and reference mode must
   not; the reference test also asserts the story has no lives and the bay's plan no pale cow.
   ```
   ok    test_reference_mode_draws_no_creature_or_rare_event (26.1s)
   ok    test_reference_mode_has_no_grain_and_holds_the_tide (0.2s)
   ok    test_reference_build_is_deterministic_and_leaves_the_tree_clean (44.5s)
   ok    test_existing_set (0.0s)
   4/4 passed
   ```
3. and 4. **Determinism.** Each set rendered twice into two folders, one after the other, every frame compared with `cmp`
   (`--scale 0.375 --jobs 1 --weather fair --quality 90`):
   - A (probe 3): 2027-03-24 `--minutes 1058-1063` (the lead's set; before 2027's lambing, so no lambs, where phase 3
     had two);
   - B (probe 4): 2028-06-15 `--minutes 705-710` (three lambs of nine and ten weeks, the 2027 hogg, four kittens of 40 days at
     the step with the cat, all six minutes).
   ```
   12 frames compared, 0 differ
   A: 1738.jpg ... 1743.jpg  (first frame's md5 5544144b3d2ab362604f651ee99a0c72)
   B: 1145.jpg ... 1150.jpg  (ca05e87ca3976a6fdf71a471de1bc0c8)
   ```
5. **Shore reference digest.** `$PY tools/shore_reference.py OUT --reference r2`:
   ```
   reference r2 written to .../r2: digest 7cbee1f442afce967826b8e6f6aaffddd8921391b138a487f359b4d9024d35fa
   ```
   Unchanged, so no r3.
6. **Cost.**
   - **Frames.** `main` (the main checkout at `b5b6d76`, whose renderer is `09fe743`'s) against this worktree,
     `listening_point.py OUT --date 2028-06-15 --minutes 700-719 --scale 0.75 --jobs 1 --weather fair --quality 90`
     (20 minutes with two near-scenery keyframes, as the nightly job renders; the branch draws three lambs, the hogg
     and, from 11:45, four kittens), CPU time (user + sys) from `/usr/bin/time -l`, two rounds in opposite orders:

     | round | main real / cpu s | branch real / cpu s |
     |---|---|---|
     | 1, main first | 49.50 / 52.23 | 49.14 / 52.38 |
     | 2, branch first | 50.80 / 53.60 | 49.28 / 52.43 |
     | sum | 100.30 / 105.83 | 98.42 / 104.81 |

     **Ratio (CPU) 0.99** (limit 1.15). Peak RSS 1280-1359 MB on main, 1415-1446 MB on the branch (part 1 saw swings
     of hundreds of MB between runs of the same code; not a probe).
   - **The story, per Day** (once per render process), `Story.cost_ms` in a fresh process: 0.8 ms fair (2028-06-15),
     63 ms synthetic (2028-06-15), 35 ms synthetic (2027-09-01), 37 ms from the real weather cache (2026-11-04). The
     lives add a few ms to part 1's figures: the years' draws are cached per process, and only the sale and the wet
     spell read the weather.
7. **The calendar.** `tools/story_calendar.py --lives` (above).
8. **Ordinary days.** The `ordinary` scene (2027-02-17 14:30 fair) is byte-identical to `main` (`cmp` silent). Days
   with no lambs, no hogg, no kittens and the pale cow as phase 4 has her render as before: every new draw has its
   own seed, and with nothing in the story every changed function makes the calls it made before.

## Look test

Folder `out/look/v3/story-lives/` of the main checkout (`look.py` there rebuilds it; `look.py plan` prints the
minutes and boxes):
- `pair-<scene>.jpg`: the whole frame at Evan's 1440 x 900, `main` on top and this branch below;
- `crop-<scene>.jpg`: a native-size crop round the subject, `main` above the branch;
- `seq-<name>.jpg`: the branch across successive dates, each crop following the animal, shown 2x (the seal's 3x), the
  date and time in its corner.

All rendered with `listening_point.py --scale 0.75 --jobs 1 --quality 90 --weather fair`, one at a time.

| scene | when | what to look at |
|---|---|---|
| `ordinary` | 2027-02-17 14:30 | Nothing in the story: byte-identical to `main`. |
| `lambs-young` | 2027-04-20 11:00 | Main: phase 3's two lambs, small ewes. Branch: three lambs of ten days by their mothers in the upper field, small, leggy and black-faced: one lying under her mother, one standing by its mother at the garden wall, one at a ewe's head. |
| `lambs-summer` | 2027-07-15 15:00 | Main: no lambs (phase 3 ended them in May). Branch: the three at thirteen weeks, three quarters of a ewe's size, by the ewes along the upper field wall. |
| `hogg` | 2027-09-08 12:00 | Neither has lambs (on the branch the sale was 25 August). Of the two ewes on the path, the right one (slot 0) is the kept ewe lamb: 0.84 of a ewe's size, whiter. |
| `kittens-step` | 2028-06-15 11:45 | Four kittens of 40 days round the cat at the step (three black and white, a ginger). Tiny at desktop size: see Known issues. |
| `kittens-grass` | 2028-06-24 12:33 | Four kittens of seven weeks round the crouching cat in the grass: three black and white ones sitting, the ginger crouched. |
| `seal-away` | 2027-10-03 12:00 | Main: the pale cow on her knob and a grey seal. Branch: only the grey seal; her knob is empty. |
| `seal-back` | 2027-10-27 09:20 | Both have her (two days after her return on the branch): on the branch she lies lower in the back, thin. Subtle. |

| sequence | dates | what it shows |
|---|---|---|
| `seq-lambs` | 2027-04-11 to 08-22, 11:00 | One lamb (2027-1a, a twin, born 10 April) at one day, one week, three, six, nine, twelve, fifteen and nineteen weeks: from a small leggy thing lying by its mother to a sturdy lamb near her size, always by her. |
| `seq-kittens` | 2028-06-03 to 07-29, weekly | The 2028 litter: at the step on its first day out (four weeks), in the grass, at the foot of the wall and in front of the bench (from seven weeks), thinning in late July (three on 16 July, then two, one), and the cat alone at the step on 29 July. |
| `seq-seal` | 2027-09-19 to 12-01 | The skerry at low water by day: the pale cow with the others (19 Sep); away: the grey seals only, her knob empty (26 Sep, 3 and 17 Oct); back on the evening of 25 Oct, thin, head up; 27 Oct and 3 Nov thin; 1 Dec filled out. |

## Known issues

- **The kittens are tiny.** They are drawn in proportion to the cat, as asked, and the cat is still its phase 1
  size: about 12 px tall at the step and 15-18 px in the grass at 2880 x 1800, so a kitten is 5-9 px (2.5-4.5 points
  on Evan's screen). They show when you look for them (the black and white ones best, in the grass), not at a glance.
  To read at a glance the cat and the kittens would have to be drawn larger together, as phase 3 did for the sheep.
- **The second cat.** The 2029 litter's tabby stays and grows into a second cat beside her (at her side wherever the
  kittens would be, and indoors with her). From July 2029 on, every frame with the cat out by day has two cats.
  `KIT_STAY_P = 0` in `story.py` turns it off without moving any other draw.
- **The hogg is subtle.** 0.82 of a ewe after the sale, 0.93 by New Year, 0.97 by her first spring: by then she reads
  as a ewe. The whiter fleece is the other sign.
- **The thin seal is subtle.** Her back up to a quarter lower for five weeks: visible up close, not at desktop size.
- **The return day's low water can be at dusk.** On 25 October 2027 the day's low water by daylight is at 17:09, so
  the first sight of her back is in the evening light.
- **Changes at midnight.** A lamb born in the night appears at 00:00 lying in the fold; the lambs leave the fold at
  00:00 after the sale; the kittens' days change while they are indoors. Only the seal's haul-outs span midnight, and
  those keep the day before's state (above).
- **Kittens walk straight.** Following her, going in and coming out, a kitten walks a straight line at a steady
  pace (from the bench to the door it crosses the path), as the cat does.
- **Lambs are always side on.** A ewe walking toward you or away has her lambs side on beside her.
- **The live frames change on install.** In 2026 the pale cow was away from 23 September to 1 November, so on
  2026-11-04 she is two days back: she comes to every low water that day and is thin until 6 December. The flock and
  the cat change nothing until the lambing of 2027.
- **Real weather.** The sale waits for a day fit for work; a day the weather cache does not cover counts as fit (the
  flock has a calendar of its own, as the garden does), and 21 days on it happens whatever the weather. A wet spell
  is read only from cached days, so with no cache the kittens are never kept in.

## Status

- 2026-11-04: built on `v3/story-lives`. Probes 1-8 pass (numbers above). The look test is in
  `out/look/v3/story-lives/` (8 pairs, 8 crops, 3 sequences). Not merged, not installed. Reference r2 is unchanged.
- Next: the lead reviews the look test, then merges and installs. Part 3 (echoes of the shore) hangs its strand on
  `Story` the same way (strands 18 and up for the calendar, 31 and up for drawing).
