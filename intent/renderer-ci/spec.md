# Spec: catch renderer crashes before the render job does

## Concerns

- **The sweep finds a crash only by chance.** Ten random dates a night is about 3,650 a year out of
  a six-year window; the contrail crash needed one forecast and one minute. The live pass (today and
  tomorrow on the hour, with the forecast) is the part aimed at that case, and it sees 48 of 2,880
  minutes. This lowers the odds of a surprise; it does not remove them.
- **CI is not the Mac.** A crash that needs this Mac's shore cache or its memory pressure will not
  show.
- **Cross-machine pixels.** The tests that compare bytes compare two runs on one machine, so they
  hold anywhere; nothing here claims a frame has the same bytes on Linux and on the Mac.

## Requirements

1. `renderer.yml`, on push, pull request and by hand: `python -m unittest discover -s tests`, then
   the script tests (`test_astro.py`, `test_weather.py`, `test_shore_reference.py`,
   `test_shore_render.py`), on macOS with `/usr/bin/python3` (3.9, the Mac's) and on Ubuntu with 3.12.
2. `tests/sweep.py`: N random dates (seeded; the seed defaults to the date and is printed), made-up
   weather, per date four scattered minutes and a run of six across a keyframe, at a fifth of full
   size, one renderer process a command. `--live`: today and tomorrow on the hour with the live
   forecast. A failed command prints the renderer's last lines and a command that repeats it. Exit
   code: the number of failed commands.
3. `renderer.yml` runs both sweeps on push, pull request, by hand and every night (03:17 UTC). The
   nightly run skips the unit tests.
4. `requirements.txt` pins the versions both venvs on the Mac hold today: numpy 2.0.2, scipy 1.13.1,
   Pillow 11.3.0 (all have wheels for Python 3.9 to 3.12).

## Proof

- The workflow's first run on GitHub is green on both systems (`gh run watch`).
- `tests/sweep.py --dates 3` passes locally; with a crash planted in the renderer it fails, prints
  the traceback and the command, and that command fails the same way.
