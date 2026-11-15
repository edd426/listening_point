# Intent: render tomorrow once

Author: Evan (accepted Claude's proposal, 2026-11-15: "Please do 1-3 and 6"; this is item 1),
written up by Claude. Status: built 2026-11-15.

## Problem

- The render job renders all of tomorrow as soon as today is done, then again after 18:00 when the
  forecast has changed.
- The evening check has fired on each of the 14 days from 2026-11-01 to 11-14
  (`~/Library/Logs/listening-point.log`): it asks whether any one hour's cloud, rain, snow or fog
  moved by more than 0.3, and over a day one always does.
- A day takes about 2.5 hours to render on this Mac (8,655 to 9,385 s for an undisturbed day,
  11-12 to 11-15). So about 2.5 of roughly 5 hours of daily background rendering are thrown away,
  on an 8 GB laptop Evan also games on.

## Proposed outcome

- Tomorrow is rendered once, from 18:00, with the evening's forecast.
- The daily render load falls by about half.

## Affected users and systems

- `tools/nightly.py` (the installed render job) and its description in `README.md`, `STATUS.md`,
  `tools/install.sh`.
- Evan's desktop just after midnight, on a day when the Mac was not awake on power the evening
  before.

## Constraints

- The desktop must still show the right minute: the helper's fallback (the same minute of the
  newest earlier day) and "the rest of today" cover a missed evening.
- Battery behaviour stays as it is.
- The shore and lamp re-render rules stay as they are.

## Open questions

- None for Evan.
