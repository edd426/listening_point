# Plan: a frame that fails is skipped

1. `listening_point.py`: `SKIP_MAX`, `render_chunk` returns `(done, failed)`, `main` collects and
   exits 1.
2. `tests/test_skip.py`.
3. The planted-crash run by hand; the sweep on the plant.
4. Merge, install with the cloud change.
