# Intent: housekeeping after v3

Author: Evan (accepted Claude's proposal, 2026-11-15: "Please do 1-3 and 6"; this is item 6),
written up by Claude. Status: done 2026-11-15 but for the README pictures and the v3 release
(Open questions).

## Problem

- `STATUS.md` calls the shore and the owner controls "not installed", though the render log shows
  both running, and gives v2.0's render cost.
- `README.md`, its three pictures and the latest release (v2.0, 2026-10-06) show v2. Nothing public
  shows v3 or mentions the shore.
- There was no `intent.md` (the AI-native SDLC rule of 2026-11-15).
- 13 merged branches remain, locally and on GitHub.
- `~/Pictures/Wallpapers/The Listening Point/pre-cast/` holds 1.6 GB of old-look frames kept since
  2026-11-10 "until the new look has been seen".
- The render job does not look at free disk space. The disk filled on 2026-11-03 and a render died
  with "No space left on device".

## Proposed outcome

- The docs say what is installed and what it costs today.
- The README describes and shows v3; a v3 release carries the hourly HEIC.
- The merged branches and `pre-cast/` are gone.
- The render job stops while the disk is nearly full, and says so in the log.

## Affected users and systems

- `STATUS.md`, `README.md`, `docs/`, `intent.md`; `tools/nightly.py`; the GitHub repository's
  branches and releases; one folder under `~/Pictures`.

## Constraints

- Nothing from the real shore in git or in the README pictures (the repository is public).
- No spoilers in the README.
- Rendered frames and HEICs stay out of git; the release carries the HEIC.

## Open questions

- The README pictures and the v3 release should show the sky Evan chooses in
  `intent/cloud-horizon/`, so they wait for his verdict on that look test.
