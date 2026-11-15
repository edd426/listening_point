# Intent: no whirl in the clouds

Author: Evan (accepted Claude's proposal, 2026-11-15: "Please do 1-3 and 6"; this is item 2),
written up by Claude. Status: built on branch `v3/cloud-horizon`, 2026-11-15; **waiting for Evan's
verdict on the look test** (`out/look/cloud-horizon/`). Not installed.

## Problem

- On 2026-11-15 at 12:00 the whole upper sky was a whirl: cloud streaks fanning out of a point on the
  horizon and bending round toward the frame's edges. Claude called it "the most computer-made thing
  in the picture".
- Claude's proposal named the mid-level layer, after `STATUS.md`'s known weakness ("Mid-level clouds
  near the horizon streak toward the vanishing point"). **That was wrong for this frame:** its cloud
  was the high layer (cirrus, 100% cover; mid-level 0%). The cause is shared by all three layers.
- The cause: the layers are flat planes drawn on a 220-degree panorama. On it a plane's parallel rows
  must bend, and round cloudlets are drawn at least twice as wide as tall.
- Up close the cloud edges show the texture's own squares (up to ten pixels a texel).

## Proposed outcome

- Cloud rows run straight across the picture. Nothing fans out of a point inside the frame, except
  briefly when the wind lies within a few degrees of the view's axis.
- The sky still follows the forecast (cover per layer), the wind (drift, the slant of the cirrus) and
  the sun (a cloud over the sun still dims the light).
- Cloud edges are smooth up close.

## Affected users and systems

- `renderers/procedural/sky.py` (the three noise layers), `core.py` (a smoother sampler).
- Through them: the sun's dimming, the cloud shadows on the sea (`water.py`), the sunset colours.
- Not the shore's reference set: it is rendered without cloud.

## Constraints

- The layout, colour and mood stay (`intent.md`). Restraint.
- A look test first: before and after, at half size, of the frame Evan saw and of each cloud type.
- Render time: no more than a few percent.
- The reference set r3 keeps its digest.

## Open questions

- **Evan: go, or not?** The pairs are in `out/look/cloud-horizon/pair-*.jpg` (top before, bottom
  after).
