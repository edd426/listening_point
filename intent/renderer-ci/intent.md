# Intent: catch renderer crashes before the render job does

Author: Evan (accepted Claude's proposal, 2026-11-15: "Please do 1-3 and 6"; this is item 3),
written up by Claude. Status: built 2026-11-15.

## Problem

- CI runs the shore kit's tests only. The renderer's tests (158 on 2026-11-15) run when someone
  remembers to run them on this Mac.
- `tests/test_shore_render.py` failed 5 of 7 on `main` from 2026-11-01 to 11-10 and nobody saw.
- On 2026-11-04 the contrails crashed on one forecast at 09:27. The render job retried every 15
  minutes and the crash went away only when the forecast changed.
- `requirements.txt` gives ranges (`numpy>=2.0,<3`, `pillow>=11`, `scipy>=1.13`). A new install
  could pick up Pillow 13, which removes a parameter the renderer uses (`Image.fromarray(a, "F")`;
  the tests print its deprecation warning today).

## Proposed outcome

- Every push runs the renderer's tests on macOS, on the interpreter the Mac uses.
- Every push and every night, small frames of random dates are rendered, and today and tomorrow with
  the live forecast; a crash fails the run and prints the command that repeats it.
- The installed versions are the pinned versions.

## Affected users and systems

- `.github/workflows/renderer.yml`, `tests/sweep.py`, `requirements.txt`.
- GitHub Actions on the public repository (free for public repositories). A failed nightly run sends
  GitHub's usual failure email to Evan.
- Open-Meteo gets one forecast request a run from a GitHub runner, for Budapest's coordinates, which
  are already public in this repository.

## Constraints

- Nothing from the real shore in CI (`.github/scripts/no_shore_data.py` stays).
- No secrets, read-only permissions, actions pinned by commit as in `shorekit.yml`.

## Open questions

- None for Evan.
