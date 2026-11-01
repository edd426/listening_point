# Working on this repo

- Read STATUS.md first: it holds the current state, decisions, macOS gotchas, and the idea list.
  Update it when any of those change.
- Iterate at low resolution: `SCALE=0.25 EVERY=60 ./build.sh`, or render chosen minutes with
  `./venv/bin/python renderers/procedural/listening_point.py out/prev --date 2026-12-21 --times 08:30,16:00 --scale 0.3 --jobs 3 --sheet`.
  Use `--weather fair` (or `synthetic`) for repeatable previews. Check full-res crops before a final render.
- Never commit rendered frames, HEICs or the weather cache; attach releases to GitHub.
- After installing, confirm what is on screen with `tools/capture_wallpaper.sh`, not by reading the wallpaper store.
- Every renderer writes `HHMM.jpg` (0000-2359) for local-clock minutes, so `tools/` stays shared.
- The installed copy (tools/install.sh) runs from ~/Library/Application Support/The Listening Point; re-run
  `tools/install.sh` after changing the renderer, or the nightly job keeps using the old code.
- Spoilers: docs/SPOILERS.md lists the hidden events. Don't describe them in chat or the README.
- Worktrees go in `.claude/worktrees/<name>` inside this checkout (gitignored), never as sibling folders in
  `~/Documents/Projects` (Evan doesn't want them scattered there). Remove a worktree once its branch is merged.
- Keep look-test images for Evan in `out/look/<topic>/` (gitignored), not only in a session scratchpad, which a
  restart wipes.
- This Mac is an 8 GB M1 that Evan also games on (e.g. Slay the Spire 2 co-op, run by `sts2-coop-*` sessions).
  Before heavy renders, check `uptime` and swap. Render with `--jobs 1` under `nice`, and pause (`kill -STOP` the
  render job) if a game session asks.
- The v3 plan and its current handoff: `docs/V3-PLAN.md`.

