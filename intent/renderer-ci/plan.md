# Plan: catch renderer crashes before the render job does

1. `tests/sweep.py`; try it locally, and with a planted crash.
2. `requirements.txt`: exact pins.
3. `.github/workflows/renderer.yml`.
4. Push the branch, watch the run, mend what CI shows (a test that only passes on this Mac is a
   finding: fix it or say why it is skipped there).
5. Merge to `main`.

Risk: the shore render tests take several minutes of full-size rendering on a runner. If a run goes
over about 20 minutes they move to macOS only.
