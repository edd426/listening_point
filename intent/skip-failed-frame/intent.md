# Intent: a frame that fails is skipped

Author: Evan (2026-11-15, on Claude's offer: "yes, let's skip the frame instead"), written up by
Claude. Status: built 2026-11-15.

## Problem

- When one frame crashes, the renderer stops. The frames after it in the same span are not made.
- The render job retries the span every 15 minutes and fails at the same minute, until the forecast
  changes or the day is over. On 2026-11-04 the contrails did this at 09:27.
- The desktop then shows the helper's fallback (the same minute of an earlier day) for the rest of
  the day, not for one minute.

## Proposed outcome

- A frame that cannot be drawn is skipped and reported; the frames after it are made.
- The run still ends with an error, so the log and the render job know.
- A renderer that fails on every frame still stops quickly.

## Affected users and systems

- `renderers/procedural/listening_point.py` (the worker and the end of `main`).
- `tools/nightly.py` only through the exit code it already logs.
- `tests/sweep.py` and CI: a skipped frame still fails them.

## Constraints

- No change to any frame that renders.
- A full disk or an unwritable folder must still stop the run.

## Open questions

- None for Evan.
