# shorekit schema (kit 1.0.0)

This file is the contract for everything that reads or writes shore data: the kit itself, the
reference builder that renders reference sets on the Mac, the carrier that judges and publishes
objects, and the renderer that draws them. Where this file and the code disagree, the code's tests
decide and this file is wrong; fix it.

All coordinates are **frame pixels** of the 2880 x 1800 frame, origin top left, x right, y down,
unless a field says otherwise. All numbers are integers. "Inclusive" ranges include both ends.

---

## 1. Shared conventions

### 1.1 Strict JSON

Every JSON file the kit reads is parsed strictly:

- Bytes are printable ASCII (0x20-0x7E) plus tab, LF and CR. **No backslash anywhere**, so no
  string escapes. A byte outside this set is `E_PARSE`.
- No floats, exponents, `NaN` or `Infinity`. Integers have at most 15 digits.
- No duplicate keys. The top level is an object.
- `true`/`false` are never accepted where an integer is expected.
- Size and nesting limits per file:

| File | Max bytes | Max depth |
|---|---|---|
| manifest (`objects/<id>.json`, an author's file) | 16384 | 4 |
| `ledger.json` | 16 MiB | 4 |
| `queue.json` | 65536 | 4 |
| `kit.lock` | 4096 | 2 |
| `surfaces.json` | 262144 | 5 |
| `palette.json` | 65536 | 5 |
| `conditions.json` | 524288 | 5 |

**Canonical JSON** is `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`
encoded as ASCII, with no trailing newline. Because strings never contain escapes, this is the same
byte string in every language that sorts keys by code point and writes integers plainly.

### 1.2 Names and times

| Thing | Pattern |
|---|---|
| object id | `[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]{1,40}`, and the first ten characters are a real date, years 2000-2999 |
| maker | `[a-z0-9][a-z0-9-]{0,31}` (opaque: `maker-a`) |
| world | `[a-z0-9][a-z0-9-]{0,31}` (opaque: `world-1`) |
| reference id | `r[1-9][0-9]{0,3}` |
| kit version | `N.N.N`, each part 1-3 digits |
| time | `YYYY-MM-DDTHH:MM:SSZ`, UTC, a real date and time (hour 00-23). Times compare as strings. |
| sha256 | 64 lowercase hex |
| commit | 40 or 64 lowercase hex |

An object's **identity** is the sha256 of its canonical JSON. The id is its name; ids are never
reused, not even after the sea takes the object.

---

## 2. The shore directory (the `shore` branch, as extracted)

```
kit/shorekit.pyz          the kit (status checks it against kit.lock)
kit.lock                  section 3
ledger.json               section 6
objects/<id>.json         every object ever added, canonical bytes (section 4)
reference/<rid>/...       reference sets (section 5); kit.lock names the current one
lamp.json                 carrier-owned; the kit ignores it
returned/<id>.json        carrier-owned; the kit ignores it
```

`shorekit` finds this directory from `--shore DIR`; else, when run as `<root>/kit/shorekit.pyz`
with `<root>/kit.lock` present, from `<root>`; else from the working directory if it holds
`kit.lock` or `ledger.json`.

## 3. `kit.lock`

```json
{"shore_kit_lock": 1, "kit": "1.0.0", "commit": "<listening_point commit>",
 "pyz_sha256": "<sha256 of kit/shorekit.pyz>", "reference": "r1"}
```

Exactly these keys. `shorekit status` prints `KIT OK` when the running archive's sha256 equals
`pyz_sha256` and its version equals `kit`, else `KIT MISMATCH` (exit 1). `reference` selects
`reference/<reference>/`.

---

## 4. Objects

### 4.1 Manifest

```json
{"shore": 1, "id": "2026-11-02-cairn", "maker": "maker-a", "kit": "1.0.0", "reference": "r1",
 "palette": {"a": [122, 118, 110], "b": [134, 130, 122]},
 "rows": ["..aa..", ".abba.", "aabbaa"],
 "scale": 1, "anchor": [3, 2],
 "place": {"on": "shingle", "x": 2600, "y": 1655},
 "label": {"text": "FIRST STONE", "side": "right"}}
```

| Key | Rule |
|---|---|
| `shore` | `1` |
| `id`, `maker`, `kit`, `reference` | section 1.2 |
| `palette` | 1-16 keys, each one letter `a`-`z`; each value `[r, g, b]`, integers 0-255. Colours are **albedo** (unlit paint). Every key must be used. |
| `rows` | 1-64 strings, all the same length 1-64. Each character is a palette key or `.` (transparent). The grid must be trimmed: the first and last rows and the first and last columns each hold an opaque cell. Row 0 is the top. |
| `scale` | 1 or 2: pixels per cell side. |
| `anchor` | `[column, row]` of a cell in the grid (it may be transparent). |
| `place.on` | `"shingle"`, `"pier"`, or the id of a live object to build onto (not its own id). |
| `place.x`, `place.y` | 0-9999. |
| `label` | optional; exactly `{"text", "side"}`; `side` is `"left"` or `"right"`. `text` is checked by rule 6. |

No other keys, at any level.

### 4.2 Placement

With scale `s`, anchor `(ac, ar)`, grid `w` x `h` and place `(x, y)`:

```
ox = x - s//2 - ac*s            the grid's top-left pixel
oy = y - ar*s - (s - 1)
cell (c, r) covers pixels  ox + c*s .. ox + c*s + s-1   by   oy + r*s .. oy + r*s + s-1
foot_y = oy + h*s - 1           the bottom pixel row (the last row always has an opaque cell)
left = ox, right = ox + w*s - 1
```

So the anchor cell's bottom pixel row is row `y`, and its columns are `x - s//2 .. x - s//2 + s-1`.
(`//` is floor division.)

**Foot pixels** are the bottom pixel row (`foot_y`) under the opaque cells of the grid's last row.

### 4.3 The label plaque

A label of `n` characters is carved on a driftwood plaque standing on the same foot row:

```
pw = 12*n + 6, ph = 20
side "right": px0 = right + 3        side "left": px0 = left - 2 - pw
py0 = foot_y - 19
```

Plaque row `r` (0 at the top), column `c`:
- transparent where `c < inset` or `c >= pw - inset`, with inset 2 on rows 0 and 19, 1 on rows 1 and 18, else 0;
- **ink** where a glyph pixel falls: character `i` starts at `(px0 + 4 + 12*i, py0 + 3)` and each
  pixel of its 5 x 7 glyph (`shorekit/font.py`) is a 2 x 2 block;
- otherwise **grain** on row 2 where `c % 7 < 4` and on row 17 where `(c + 3) % 9 < 5`;
- otherwise **wood**.

Wood, grain and ink albedos come from `palette.json` (`plaque`). The plaque's **foot pixels** are its
row-19 pixels. Plaque pixels are part of the object's solid pixels and are its **label pixels**.

### 4.4 Footprint, contact shadow, draw order

An object's **solid pixels** are its opaque grid pixels plus its plaque pixels.

Objects placed `on` `shingle` or `pier` cast a **contact shadow**. Take the sorted set of columns of
the foot pixels and plaque foot pixels; for each maximal run of consecutive columns `[a, b]` the
candidate shadow pixels are `(a-1 .. b+1, foot_y+1)` and `(a .. b, foot_y+2)`. A candidate is kept if
it is inside the region, not on keep-out, not one of the object's own solid pixels, and on ground:
for `shingle`, column x has a dry band and `y >= dry.top[x]`; for `pier`, it is on the deck.
Objects built onto another object cast no shadow (it would fall on an object).

The **footprint** is the solid pixels plus the shadow pixels it actually casts (below).

**Ground y**: `foot_y` for `shingle` and `pier`; for an object built onto another, the ground y of
the object it rests on (transitively). **Draw order**: ascending `(ground y, seq)`.

**Painting** (the only definition of who covers whom): in draw order, each object first casts its
shadow pixels on every pixel that no earlier object's solid pixel occupies (shadows never fall on
objects), then writes its solid pixels over everything before it. The final image shows, per pixel,
the last object to write a solid pixel there; else a shadow if any object cast one there; else the
crop. An object's solid pixel is **visible** if the object owns that pixel at the end; a cast shadow
pixel is visible if no object owns it at the end.

### 4.5 Rules

A candidate is judged in this order; a stage with errors stops the judging.

1. **Ledger checks** (section 6.4): `E_TAKEN` the id was ever used; `E_QUOTA` the maker already
   has an object accepted on this UTC day; `E_ID` the id's date is after the pass's date; `E_KIT`
   the manifest's kit major version differs from the running kit's; `E_REFERENCE` the manifest's
   reference is not the shore's current reference.
2. **Local rules.** Rule 1 count: 16-2500 opaque cells (`E_SIZE`). Rule 2 (`E_PALETTE`): every
   palette channel is at most 240, and some entry `P` of `palette.json` satisfies
   `(1024 + R+Rp)*dR^2 + 2048*dG^2 + (1534 - R-Rp)*dB^2 <= 512*D^2` (exactly 512 times the squared
   redmean distance). Rule 6 (`E_LABEL`): text matches `[A-Z0-9 .'-]{1,12}`, does not start or end
   with a space, holds no two spaces in a row, and a `.` is followed only by a space, another `.`,
   or the end (so no domain names).
3. **Support**: `on` names a live object, else `E_ON`.
4. **Placement.** Rule 3 (`E_REGION`): every solid pixel is inside the region and not on keep-out.
   Rule 1 height (`E_SIZE`): `h*s <= max_h[ground y]` (when the ground y is inside the region).
   Rule 4 (`E_REST`), nothing floats: on `shingle`, every foot pixel's column has a dry band with
   `top <= foot_y <= bottom`, and the same for every plaque foot pixel; on `pier`, every foot pixel
   and plaque foot pixel is on the deck; built onto object `S`, at least half of the foot pixels
   (`2n >= total`) have the pixel directly below them, `(x, foot_y + 1)`, among `S`'s opaque grid
   pixels (not its plaque), and the same, counted separately, for the plaque's foot pixels.
5. **Add, never erase** (rule 5). Compare the painting of the live objects without the candidate
   (*before*) and with it (*after*). For each live object `A` whose bounding box meets the
   candidate's: `F` = `A`'s footprint before; `lost` = pixels of `F` visible before and not after.
   `E_COVER` if `100*(visible_before - lost) < 60*F` ("would leave A n% visible") or
   `100*lost > 25*F` ("takes n% of A"). `E_LABEL_COVER` if any of `A`'s label pixels is not
   owned by `A` after. For the candidate `N` (after): `E_HIDDEN` if `100*visible < 50*footprint`;
   `E_LABEL_COVER` if any of its own label pixels is not owned by `N`.

Every message names the spot: a cell `(column,row)` and a frame pixel `(x,y)` or column `x=`, the
first in raster order. Percentages shown are floored, except "takes", which is rounded up.

---

## 5. Reference sets: `reference/<rid>/`

Written on the Mac by the reference builder; never committed to listening_point. All files are
required. The kit refuses a set that breaks any rule below (`E_REFDATA`).

### 5.1 `surfaces.json`

```json
{"shore_surfaces": 1, "reference": "r1",
 "frame": {"w": 2880, "h": 1800},
 "crop": {"x": 1600, "y": 1150, "w": 1280, "h": 640},
 "region": {"x0": 1640, "y0": 1150, "x1": 2879, "y1": 1789},
 "dry": {"x0": 1640, "top": [ ...1240 ints ], "bottom": [ ...1240 ints ]},
 "deck": [[2016, 1544], [2471, 1420], [2465, 1408], [2008, 1532]],
 "max_h": {"y0": 1150, "h": [ ...640 ints ]}}
```

- `crop`: where the 1280 x 640 crops and `keepout.png` sit in the frame. Must be 1280 x 640 and
  inside the frame. Crop-local index of frame pixel (x, y) is `(y - crop.y)*1280 + (x - crop.x)`.
- `region`: inclusive bounds every solid pixel must lie in; inside the crop.
- `dry`: the **always-dry band** (dry at high water), per column `x = dry.x0 + i` for `i` in
  `0 .. region.x1 - region.x0`: `top[i] .. bottom[i]` inclusive, or `-1, -1` where there is none.
  `dry.x0` equals `region.x0`; `region.y0 <= top <= bottom <= region.y1`.
- `deck`: the pier deck's top surface, 3-64 vertices, each inside the region. A pixel `(x, y)` is
  on the deck if the integer point `(x, y)` is inside the polygon or on its boundary (even-odd
  crossing test plus an exact on-segment test, integers only; `reference.point_in_polygon`).
- `max_h`: the tallest object, in pixels, that may stand with ground y = `max_h.y0 + j`; one value
  per region row, each 1-1000. The plan's value is `round(64 * persp(y))`.

### 5.2 `palette.json`

```json
{"shore_palette": 1, "reference": "r1", "d": 40,
 "entries": [{"name": "rock", "rgb": [134, 130, 122]}, ...],
 "plaque": {"wood": [152, 140, 118], "grain": [120, 108, 90], "ink": [54, 46, 38]}}
```

- `d`: the redmean distance D of rule 2, 1-765.
- `entries`: 1-256 albedos the renderer uses on the shore (rock, shingle, wrack, timber, iron, sail,
  glass, seasonal grass, ...); names unique, `[a-z][a-z0-9-]{0,31}`; channels 0-255.
- `plaque`: the plaque's three albedos.

### 5.3 `conditions.json`

```json
{"shore_conditions": 1, "reference": "r1", "cell": 16,
 "vignette": [[ ...80 ints ], ... 40 rows],
 "conditions": [
   {"name": "noon", "light": [300, 296, 288],
    "lut": [[ ...512 ints ], [ ...512 ], [ ...512 ]],
    "veil": {"rgb": [0, 0, 0], "alpha": [ ...640 ints ]},
    "shadow": {"rgb": [22, 24, 30], "alpha": 110}},
   ... exactly 4 conditions ]}
```

- `cell` is 16. `vignette[j][i]` is the vignette x256 (0-256) for crop pixels
  `16i .. 16i+15` by `16j .. 16j+15`.
- `conditions`: exactly four, names unique `[a-z]{1,16}`; their order is the sheet's order. Each
  condition's crop is `<name>.png`.
- `light`: the light x256 (0-4096) per channel on an upright surface at that minute, the `light()`
  of the renderer without local pools.
- `lut`: per channel, 512 values 0-255: the tone curve of `grade()` without grain or vignette,
  indexed by linear value 0-511.
- `veil`: the fog veil: colour (linear 0-255) and alpha x256 (0-256) per crop row (640 values).
  All-zero alpha means no veil.
- `shadow`: the contact shadow's display-space colour and alpha x256.

### 5.4 Images

`keepout.png` and `<name>.png` for each condition. Both are 1280 x 640, 8-bit, non-interlaced,
**filter type 0 on every row**, and hold only `IHDR`, `IDAT` and `IEND` chunks; nothing may follow
`IEND`. Write them with `shorekit.png.write_png`.

- `keepout.png`: greyscale (colour type 0); each pixel is 0 (open) or 255 (keep-out). Max 2 MiB.
  It marks pixels no solid pixel may cover and no shadow may fall on: scenery silhouettes (pier
  side and piles, bollards, lantern post, the moored boat and its line, rocks) and the resting
  lanes of creatures and scheduled events. Mark the columns left of `region.x0` too. **Do not mark
  the tidal band** above the dry band: an object standing on the dry band rises in front of it on
  screen. Rule 4 already keeps feet off it, and shadows only fall on dry ground.
- `<name>.png`: RGB (colour type 2), the graded frame cropped to the crop rectangle, rendered with
  the `--reference` flag (no creatures, rare events or grain). Max 8 MiB each.

`context.jpg`, if present, is for people and is ignored.

### 5.5 Digest

`sha256("shorekit-reference-1\n" + concat over files sorted by name of "<name> <sha256 of bytes>\n")`
over `conditions.json`, `keepout.png`, `palette.json`, `surfaces.json` and the four crops. Printed by
`status` and written to `result.json`, so two machines can confirm they judge against the same set.

---

## 6. The ledger

### 6.1 File

```
{"events":[
{"at":"2026-11-02T04:30:00Z","commit":"<hex>","event":"add","id":"2026-11-02-cairn","kit":"1.0.0","lands":"2026-11-02T04:30:00Z","maker":"maker-a","reference":"r1","seq":1,"sha256":"<hex>","world":"world-1"},
{"at":"2026-12-20T04:30:00Z","event":"storm","for":"2026-12-20-gate","seq":51,"takes":["2026-11-02-cairn","2026-11-03-shell"]},
{"at":"2026-12-21T09:12:00Z","event":"veto","id":"2026-11-09-mast","seq":52,"takes":["2026-11-09-mast"]}
],"shore_ledger":1}
```

The kit accepts any strict JSON of this shape; it **writes** the canonical form above: `{"events":[`,
LF, the events' canonical JSON joined by `,` LF, LF, `],"shore_ledger":1}`, LF (an empty ledger is
`{"events":[],"shore_ledger":1}` LF). The ledger's sha256 is over these canonical bytes.

### 6.2 Events

| Event | Keys (exactly) |
|---|---|
| `add` | `seq, event, at, lands, id, maker, world, commit, sha256, reference, kit` |
| `storm` | `seq, event, at, for, takes` |
| `veto` | `seq, event, at, id, takes` |

- `seq`: 1, 2, 3, ... with no gaps.
- `at`: when the carrier recorded the event; never earlier than the previous event's `at`.
- `lands` (add): when the object first appears in the wallpaper; `lands >= at`. The carrier
  chooses it (decided 2026-10-31: at acceptance, the morning pass).
- `world`, `commit`: where the object came from (stamped by the carrier from the source repo).
- `sha256`: the object's identity; `objects/<id>.json` must parse to the same canonical bytes.
- `reference`, `kit`: the reference set and kit version that accepted it.
- `takes` (storm, veto): 1-48 distinct ids, in seq order.
- `for` (storm): the id of the add that the storm made room for; that add must be the next event.

### 6.3 Replay

Replay applies the events in order to an empty shore. An inconsistency is `E_LEDGER` (exit 3);
the Mac must then keep its last good ledger.

- **add**: the id was never used; fewer than 48 objects are live; no earlier add has the same
  maker on the same UTC date of `at`; the id's date is not after `at`'s date; `objects/<id>.json`
  exists (at most 16384 bytes), parses, has the event's sha256, id, maker and reference; then the
  object is judged by rules 1-6 against the live objects, with sequence number `seq`. If it fails
  and the event's `reference` and `kit` equal the current reference id and running kit version,
  the ledger is inconsistent. If it fails under a *different* reference or kit, it is a **misfit**:
  reported, still live, never removed automatically.
- **storm**: `need = live + 1 - 48` must be positive; `takes` must equal `storm_takes(need)`; those
  objects stop being live. The next event must be the add named by `for`.
- **veto**: `id` is live; `takes` must equal `pile(id)`; those objects stop being live.

`pile(id)`: the object and every live object resting on it, directly or through others, in seq
order. `storm_takes(need)`: walk the live objects in seq order, adding each one's pile (skipping
objects already taken), until at least `need` are taken; return them in seq order. So the sea
takes the oldest first, and what was built on a thing goes with it; nothing is ever left floating.

Taken objects stay in the ledger and in `objects/`; they are simply no longer drawn.

### 6.4 Judging a candidate

Against the replayed shore, with `day` = the UTC date of the pass (in a sandbox `check`, the id's
own date unless `--day` is given). If 48 objects are live, the storm that would make room is
computed first and the candidate is judged against the shore without them; if the candidate's
support is among them, `E_ON`. The candidate's sequence number is the next seq, after the storm's.

### 6.5 The carrier's pass: `queue.json`

```json
{"shore_queue": 1, "at": "2026-11-02T04:30:00Z", "lands": "2026-11-02T04:30:00Z",
 "candidates": [{"world": "world-1", "id": "2026-11-02-cairn", "commit": "<hex>"}]}
```

- At most 64 candidates, each `(world, id)` once. Each manifest is read from
  `<directory of queue.json>/<world>/<id>.json` exactly as the author committed it.
- **Priority**: sort the distinct worlds by name; rotate the list left by
  `days_since_1970_01_01(date of at) mod number_of_worlds`; candidates follow their world's rank,
  then their id. With two worlds this alternates first place with the parity of the UTC date.
- Each candidate in turn is judged against the ledger plus everything accepted earlier in this pass.
  Accepted: a storm event (if room is needed) then an add event with this pass's `at` and `lands`,
  the queue's `world` and `commit`, and the running kit. Returned: with its messages. A returned
  candidate is a **race** (`"race": true`, plus an `E_RACE` message) when another world's object
  was accepted earlier in the pass, none of its errors is `E_QUOTA`, and it passes against the
  ledger as it stood before the pass.

`shorekit replay --shore S --queue Q --out OUT` writes:

- `OUT/ledger.json`: the whole new ledger, canonical;
- `OUT/objects/<id>.json`: each accepted object's canonical bytes;
- `OUT/result.json` (canonical, then LF):

```json
{"shore_replay": 1, "kit": "1.0.0", "reference": "r1", "reference_digest": "<hex>",
 "ledger_in": {"events": 34, "sha256": "<hex>"}, "ledger_out": {"events": 36, "sha256": "<hex>"},
 "append": [<events appended, as in the ledger>],
 "returned": [{"world": "...", "id": "...", "commit": "...", "maker": "...|null", "sha256": "...|null",
               "race": false, "messages": ["E_..."]}],
 "misfits": [{"seq": 12, "id": "...", "messages": ["E_..."]}],
 "live": [<ids in seq order>], "draw_order": [<ids>], "plan_sha256": "<hex>"}
```

`replay --veto ID --at TIME --out OUT` appends the veto event the same way. `replay --previous
FILE` additionally requires the ledger to extend `FILE` event for event (the Mac's append-only
cache: a ledger that drops or changes a known event is refused, exit 3).

---

## 7. The compositor

For an object pixel of albedo `A` (per channel `c`) at crop pixel `(x, y)` under a condition:

```
t = A_c * light_c
u = t * (256 - alpha_y) + veil_c * 256 * alpha_y       alpha_y = veil.alpha[y]
w = (u * vignette[y >> 4][x >> 4]) >> 24
out_c = lut_c[min(w, 511)]
```

and for a shadow pixel over crop colour `G`: `out_c = (G_c * (256 - s) + shadow_c * s) >> 8`.

- `sheet.png`: the four conditions as a 2 x 2 grid (`[0 1; 2 3]`), 2560 x 1280.
- `zoom.png`: condition 0 around the object being previewed (its footprint's bounding box plus 24
  px, at most 400 x 250), x4; keep-out tinted red over everything, and on open ground the dry
  band's top and bottom rows in green and the deck's edge in cyan.

The promise is the **decoded pixels** (`pixels-sha256=` in the output): PNG file bytes may differ
with the zlib version. `PLAN sha256` digests every footprint pixel, the draw order and who covers
whom.

## 8. For the renderer (Python API)

```python
from shorekit.reference import load_reference
from shorekit.ledger import load_shore
from shorekit.compose import plan
ref = load_reference(".../reference/r1")
shore = load_shore(ref, ".../ledger.json", ".../objects")       # raises ShoreError E_LEDGER
for o in plan(ref, shore.live):          # draw order
    o["id"], o["seq"], shore.info[o["id"]]["lands"]
    o["solid"]    # [(x, y, (r, g, b) albedo, is_label, shown)], frame pixels
    o["shadow"]   # [(x, y, shown)]: the shadow pixels it casts
```

Drawing each object's solid pixels in this order, lit by the frame, reproduces the kit's coverage
exactly. The kit is importable straight from the zipapp (`sys.path.insert(0, "shorekit.pyz")`).

## 9. Exit codes

| Code | Meaning |
|---|---|
| 0 | pass, OK, or a pass whose candidates were returned (that is a normal outcome) |
| 1 | the object fails a rule or does not parse (`check`, `preview`); `KIT MISMATCH` (`status`) |
| 2 | a usage, file or reference-data problem |
| 3 | the ledger is inconsistent (`E_LEDGER`) |
