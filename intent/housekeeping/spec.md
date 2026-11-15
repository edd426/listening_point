# Spec: housekeeping after v3

## Concerns

- **Deleting branches.** Only branches `git branch --merged main` lists, so every commit stays
  reachable from `main`. Remote branches are deleted the same way.
- **Deleting `pre-cast/`.** Evan's go: "Please do 1-3 and 6" (2026-11-15), where 6 named the folder.
  It holds frames of 2026-11-10 and 11-11 in the old look; both days have passed.
- **The release** is public and waits for the cloud look (intent, Open questions).

## Requirements

1. **Disk guard.** `render()` renders nothing while less than `FREE_MIN` (3 GB) is free on the
   volume that holds the frames, logs why once per run, and returns False. Old days are pruned
   before rendering instead of after, so their space is free first.
2. **STATUS.md** states: the shore, the owner controls and the cast shadows are installed; the render
   cost since v3; this change's decisions; no stale "not installed" lines.
3. **README.md** describes v3 (the hillside, the animals, the sea life, the story over weeks, the
   shore in outline), lists the current modules and tests, and names `intent.md`.
4. **Branches.** No local or remote branch other than `main` and work in progress.
5. **`pre-cast/`** removed.

## Proof

- `./venv/bin/python -m unittest tests.test_nightly` (the guard and the order of pruning).
- `git branch -a` shows `main` and open work only.
- `ls ~/Pictures/Wallpapers/"The Listening Point"` has no `pre-cast`.
