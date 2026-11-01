# v3 phase 1: definition (ground + objects), merged

Branch `v3/phase1` = `v3/ground` (`08c6d6c`) + `v3/objects` (`064b772`), then the shore's reference
moved to r2 (`374c502`). Details per part: `phase1-ground.md`, `phase1-objects.md`.

## Probes on the merged tree (2026-11-01)

1. Tests: `Ran 45 tests ... OK`.
2. Determinism: 2026-11-01 12:00 rendered twice, `cmp` identical (`f5628eeefee79e07523d5177f68f07ff`).
3. Shore strip: rebuilding r1 from `86b544a` keeps `surfaces.json`, `keepout.png`, `palette.json`,
   `conditions.json`, the shingle, deck and sea identical; the grass changes from 5 rows below the
   shingle's lower edge, so the four crops and the digest change (`f8f163b3...`). E_FAINT's 6 px ring
   can reach 1-2 of those rows for an object at the shingle's lower edge, so the Mac moves to **r2**
   (`tools/shore_sync.py` `REFERENCE`). The shore is empty (ledger seq 0), so nothing is re-judged.
4. Render time, one frame per process, main vs v3 (busy machine): noon 7.7/9.6 s, golden 7.8/12.3,
   night 6.8/9.3, fog 7.7/10.0, summer 9.2/10.4, winter 8.1/11.7: 1.1-1.6x, inside the 2x budget.
   Per-process startup (the ground fields, ~0.8 s) is in these numbers; the nightly job amortises it.

## Look test

Six scenes before/after at the real frame (2880x1800): noon, golden, night, fog, summer (2027-06-21),
winter snow (2027-01-28, synthetic weather). Session scratchpad `v3/look/`. Observed: tufted grass,
path ruts and stones, coursed walls with cast shadows, tree crowns with volume, a stonier tower.
Summer grass reads lighter and yellower than before; snow hides most of the change, as it should.

## Install (only on Evan's go)

1. Merge `v3/phase1` into `main` (merge commit) and run `tools/install.sh`.
2. The render job builds `shore/reference/r2/` on its next run (about a minute).
3. Publish that set to `edd426/shore` `reference/r2/`; set waypost `config.json`
   `shore.reference` to `{"id": "r2", "digest": <its digest>}` and check it against the Mac's
   `shore/sync.json`. Until then the carrier's pass waits; a manifest made against r1 after the
   switch comes back with `E_REFERENCE`.
