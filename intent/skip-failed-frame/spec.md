# Spec: a frame that fails is skipped

## Concerns

- **A skipped frame is tried again every 15 minutes** (it is missing, so the render job asks for it).
  Each try costs the day's setup and one keyframe, about 20 s, and writes the traceback to the log
  again. That goes on until the forecast changes or the day is over.
- **Ten in a row stops the run.** A keyframe that cannot be drawn fails all ten of its minutes, and a
  broken install fails every frame. Carrying on past that would burn hours of CPU on nothing. So a
  fault that lasts ten minutes or more still stops its span, as before this change.

## Requirements

1. In a worker, an exception while drawing a frame (`frame_image`) skips that frame: nothing is
   written for it, the full traceback is printed with the minute, and the next minute is drawn.
2. Errors while saving (a full disk, an unwritable folder) are not caught.
3. `SKIP_MAX` (10) failures in a row in one worker raise the last one: the run stops as it used to.
4. `main` prints the skipped minutes at the end and exits with code 1 when there are any.
5. Frames that render are byte-identical to before.

## Proof

- `./venv/bin/python -m unittest tests.test_skip`: one bad minute in a run; ten in a row; a save
  error; the worker's return value.
- By hand, with a crash planted at one minute: the other frames exist, the exit code is 1, the
  summary names the minute. Then with the plant removed, `--skip-existing` renders just that frame.
- `tests/sweep.py` still fails on the planted crash.
