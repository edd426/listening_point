# Plan: no whirl in the clouds

1. `sky.py`: `cloud_plane`, `streak_bearing`, `LENS_TOP`, `STREAK_MIN`, `STREAK_SWING`; use them in
   `_layer_field`. `core.py`: `sample_smooth`.
2. `tests/test_clouds.py`.
3. Look test: the 2026-11-15 12:00 frame with the forecast it was made with, a mid-level sheet at
   noon and at sunset, mid-level fleece, broken low cloud, part cirrus, high with mid, overcast.
4. Probes: unit tests, reference digest, determinism, cost.
5. `STATUS.md`: the known weakness, and this branch as waiting.
6. On Evan's go: merge, `tools/install.sh`, delete today's and tomorrow's frames so they render
   again, then the README pictures and the v3 release (`intent/housekeeping/`).

Risk: he prefers the old sky. Then the branch is dropped and nothing installed changes.

## Results (2026-11-15, commit b49267a plus this note)

- `./venv/bin/python -m unittest discover -s tests`: 158 OK (with `tests.test_clouds`, 9).
- `tests/test_shore_reference.py`: 4/4. A scratch build of r3 has the installed digest
  (`f237badc…093c`).
- Determinism: the look test's 8 frames rendered twice, 0 differ.
- Cost: 20 minutes of a cloudy noon (2026-11-13 12:20 to 12:39, full size, one process): 53.8 s of
  CPU on `main`, 56.1 s here: 1.04 times. The cubic sampling is the cost.
- Look test: `out/look/cloud-horizon/` (8 pairs, a README). Shown to Evan 2026-11-15; no verdict yet.
- `STATUS.md` is updated on `main`, not on this branch, so the merge stays clean.
