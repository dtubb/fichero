# Zero-discoveries inventory — every check that discovers-then-asserts

The invariant (the day's six instances, named): **a mechanism must prove it
measured something before it may pass.** "I found no violations" is only
meaningful with "…among the N things I actually examined", and N must have a
floor — otherwise a broken scanner, an emptied allowlist, a moved root, or an
unset bash array all report the same thing as a clean tree.

This is the successor to #4382 (empty-tree exits) one level up: #4382 made
checks fail when their INPUTS are missing; this makes them fail when inputs
are present but the check *resolved nothing from them*.

## Method (honest about its limits)

Mechanical signal scan over all 66 `scripts/check_*.py`:
- **disc** — discovery verbs (rglob/walk/finditer/…): the script scans a
  population rather than checking a fixed fact.
- **exit2** — has a distinct "could not check" exit (mostly the #4382 sweep).
- **floor** — any signal of a minimum-discovery assertion (regex; crude —
  a false negative just means a human looks; a false positive is caught in
  the per-script pass).
- **self** — a `--self-test` proving the check can fail.
- **allow** — allowlist/baseline (the two-sided-contract risk: an emptied
  baseline can remove the scanner's proof of life, the check_dead_files /
  Button-chain shape).

Raw table committed alongside this note (below). Headline numbers:

- **66 checks; 56 discover-then-assert; 50 of those have NO floor signal.**
- Only 6 have both a blind-exit AND floor-ish signal today
  (comment_hygiene, coverage_ratchet, duplicate_paths,
  pydantic_persistence_writes, stacked_presentation_modifiers,
  environment_forwarding — the worked precedent).
- 38 carry allowlists/baselines: every one of those can go blind the day
  its allowlist empties, even with a floor on raw discoveries — floors must
  be on the SCAN population, not the violation count.

## Gate legs (same question, non-Python)

- `resolve_area` — FIXED today (#4480): empty swift-prefix column aborted
  under `set -u` and exited 0 having run nothing.
- `gate part` Swift leg — zero matched test classes prints
  "(no Swift tests in area X)" and continues: **legitimate-zero, declared
  out loud** — the model to copy.
- Engine pytest legs — pytest itself exits 5 on "no tests collected", and
  the gates treat nonzero as red: a native floor already exists there.
- `verify_all --fast` guardrail loop — inherits whatever each check_*.py
  does; it cannot add floors from outside.

## Classification

1. **HAS a floor or native equivalent (8):** environment_forwarding (the
   worked precedent), coverage_ratchet, duplicate_paths, comment_hygiene,
   pydantic_persistence_writes, stacked_presentation_modifiers, pytest legs
   (exit 5), resolve_area (today).
2. **ZERO legitimately possible, must be DECLARED (small set):**
   release_size_ratchet (not-armed vs blind is already its worked example),
   unmerged_work (manager-only), verify_all_modes / features_freshness /
   mac_app_store_target (fixed-fact checks, no population). These need a
   sentence, not a floor.
3. **NEEDS a floor (~45):** everything else that scans Views/, routes,
   services, or tests and asserts absence. Highest risk first — the checks
   guarding architecture and data integrity whose silent blindness costs
   the most: ui_wiring, emit_change_coverage, undo_coverage,
   endpoint_coverage_matrix, artifact_type_contract, change_event_contract,
   accessibility, action_surface_matrix, appkit_imports, dead_files,
   test_assertions, view_endpoint_access.

## Scoping proposal (the count IS large — per the mandate, scope not absorb)

- **Phase 1 (one pass, small):** a shared primitive —
  `scripts/_check_floor.py::require_scan_floor(count, floor, what)` — that
  exits 2 (blind, never 1, never 0) with the found-vs-expected sentence,
  plus a pointed-at-nothing test template. Convert the 12 highest-risk
  checks named above. Each conversion is: count the SCANNED population
  (files examined, sites parsed — not violations), one call, one test that
  the check FAILS against an empty dir.
- **Phase 2 (mechanical tail):** the remaining ~33, in batches, same
  two-line pattern. Good lane fodder; each batch is verifiable by running
  the check against /dev/null-shaped input.
- **Floor values:** current-count × 0.5 rounded down, committed as a
  constant WITH the date and the current count in a comment — a floor is a
  tripwire, not a ratchet; it exists to catch "suddenly zero-ish", not to
  creep upward.
- **The two-sided-contract rule rides along:** where an allowlist exists,
  the floor goes on the scan population so an emptied allowlist cannot
  remove the proof of life (the Button-chain precedent, floor 100 under
  1185 found).

## Raw signal table

(script · discovers · exit2 · floor-signal · self-test · allowlist)

See the generated table in the EPIC body — committed there so the issue is
self-contained; this note is the method + classification + scope.
