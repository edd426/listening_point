# Plan: render tomorrow once

1. `tools/nightly.py`: add `TOMORROW_FROM`, `tomorrow_due`; `main(argv, clock)`; remove
   `refresh_tomorrow` and the `evening` flag; reword the module docstring.
2. `tests/test_nightly.py`: `render`, `power` and the side jobs replaced by recorders; a temp root.
3. Words: `README.md` (How it runs), `STATUS.md` (Decisions, cost), `tools/install.sh` (its closing
   message).
4. Merge to `main`, run `tools/install.sh`, check the log on the following days.

Risk: a missed evening (spec, Concerns). Undo: revert the commit and run `tools/install.sh`.
