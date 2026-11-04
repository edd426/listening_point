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
  sale, as a hogg: smaller (her own `lamb_size`, 0.82 at the sale, 0.9 by Christmas, 0.97 by her first lambing
  season) and in a whiter fleece, until she is 540 days old; she lambs first the spring after next. So the flock's
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

- **Away** (`seal_year`, seed 5517 by the year). Grey seals on the west coast of Scotland pup from September to
  late November (SCOS); a cow comes ashore at a breeding colony, nurses her pup for about 18 days while she fasts,
  mates and leaves. So in most autumns (chance 0.85) the pale cow (seaplan's seal 0) is gone from a date between 15
  September and 15 October, for 30-46 days. While she is away no seal lies on her knob (`SEAL_SPOTS[0]`) and her head
  is never one of those in the water; the other seals still come to their own spots as before.
- **Back.** From her return she comes to every low water for three days (as the wind allows: fewer in 11-15 m/s,
  none above), then to 65% of them as before. For 35 days she is thin from the fast (`draw_seal(lean)`): her back
  sunk by up to a quarter of its height, so her neck and head show, filling out day by day.
- **Across midnight.** A low water that began before midnight keeps the day before's state (`SeaPlan.pale(m)`), so a
  haul-out over midnight is one haul-out on both days, the nights she leaves and comes back included.

TBD
