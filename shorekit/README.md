# shorekit

The shore kit is how things get left on the shore at The Listening Point. Makers send small
pictures, written as a grid of coloured cells in a JSON file, with a spot to put them and an
optional short label. The kit decides whether each one fits, previews it, and keeps the record of
everything that has ever landed.

It is one file, `shorekit.pyz`, written in plain Python 3.9+ with no dependencies and **no
fractions anywhere**: every decision is integer arithmetic. So the copy in a maker's sandbox, the
copy the carrier runs and the copy on the Mac all reach the same verdict, pixel for pixel.

## Commands

```sh
python3 shorekit.pyz status                  # is this the pinned kit? what is on the shore?
python3 shorekit.pyz check  my-thing.json    # run every rule; PASS or the problems, each naming the spot
python3 shorekit.pyz preview my-thing.json   # draw sheet.png (four lights) and zoom.png (x4) to a temp folder
python3 shorekit.pyz import  my-thing.png -o my-thing.json --id 2026-11-05-pebble --maker maker-a \
                             --on shingle --at 2620,1665 [--label STONE]
python3 shorekit.pyz replay                  # re-check the whole record (carrier and Mac)
```

`--shore DIR` points at the extracted shore branch; by default the kit finds it from where
`shorekit.pyz` sits. Pictures are written to a temporary folder unless `--out` says otherwise, so
they never land in a repository by accident.

## The rules, in plain terms

1. **Size.** 16 to 2,500 filled cells, at most 64 x 64, drawn at 1 or 2 pixels a cell; nothing
   taller than the spot's depth allows (smaller further back).
2. **Colour.** Up to 16 colours, each close to a colour the scene already uses, none too bright.
3. **Place.** Within the shore and clear of the scenery (the pier's posts, the boat, the rocks)
   and of the places creatures come to rest.
4. **Resting.** Its bottom row sits on dry shingle above the tide, on the pier's deck, or at least
   half on top of another object it is built onto. Nothing floats.
5. **Add, never erase.** Every older object stays at least 60% visible, a newcomer covers at most a
   quarter of any one of them, and no label is ever covered. The newcomer is at least half visible.
6. **Label.** Up to 12 capital letters, digits, spaces and `.'-`, carved on a driftwood plank in the
   kit's own pixel font. There is no way to write a web address or a look-alike letter.
7. **Quota.** One object per maker per day, and at most 48 on the shore. When the shore is full
   and one more comes, a storm takes the oldest until 40 remain, with anything built on them. The
   owner may also take any object away, with whatever rests on it. Either way the record says only
   that the sea took them: a storm and the owner look the same. They stay in the record; they are
   just not drawn.

## Shadows

Everything standing on the shingle or the pier has a small contact shadow under its foot and, since
kit 1.3.0, a **cast shadow** that falls away from the sun, or from a bright moon. `preview` draws it
for each of the four lights, and on the wallpaper it turns through the day, so an upright thing works
as a sundial. The rule is whole numbers (`SCHEMA.md` 4.6): each light is two integers, and every
shadow pixel can be worked out by hand from them. Shadows are drawn, never judged: nothing about a
cast shadow can make a check pass or fail, and a thing built onto another casts none.

## What it promises

- **Exactly the same everywhere**, given the same kit, record and reference set: the verdict and
  its messages, every pixel an object covers, the order things are drawn in and who covers whom,
  the label's letters, the pixels each cast shadow falls on, and the preview's pixels. Tests check
  this on Linux and macOS, x86 and ARM, Python 3.9 and 3.12.
- **The same pixels on the Mac:** at every minute the wallpaper's cast shadow is this kit's rule,
  given that minute's sun or moon.
- **Close, not exact:** colour, and how dark a shadow is. The Mac lights each object through the real
  renderer every minute; at the four reference lights the result stays within a small tolerance of
  the preview.
- **Not promised:** other weather and hours, snow on objects, creatures passing in front. Under
  cloud or in fog there is no cast shadow at all.

## Safety

Objects are text, not images, so nothing on the Mac ever decodes a maker's picture. Every input
is size-checked before it is read; JSON with fractions, duplicate keys, escapes or non-ASCII is
refused; `import` checks a PNG's header before inflating a byte and never inflates more than the
header allows. The test suite throws 341 malformed inputs at it.

## For developers

```sh
python3 -m unittest discover -s shorekit/tests   # the tests (synthetic data only)
python3 -m shorekit.build                         # dist/shorekit.pyz, byte-identical every time
```

`SCHEMA.md` is the precise contract: manifests, the ledger, reference sets, the compositor and the
carrier's queue. This repository holds code and synthetic test data only; real shore data never
goes here.
