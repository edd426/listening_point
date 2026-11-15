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
