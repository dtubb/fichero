# HANDOFF - lane-sharing (final, 2026-11-04)

Built and landed through the harness (bb1, bb2, bb3) or in this last batch (bb4): sharing Stages 1-5 code, and workflows Steps 1.x, 2.1-2.6, 3.2-3.4.
Swift in all of it was written and parsed/linted but NEVER built or run by me (no xcodebuild): the harness build rung is the only compile evidence.

## Open items (issue number where one exists; "none" = file one)
- Sharing umbrella: #5049. Open owner questions 1, 3 and 6 in `docs/contributor_manual/specs/source/sharing-two-macs.md` (owner's call; none filed).
- `applinks:tubb.ca` associated-domains entitlement + the AASA file on tubb.ca: owner's signing/site change; I never edit `.entitlements`. Issue: none (owner action).
- Real-device walks 0.5 and 5.5 (two Macs / a phone): owner. Address order and labels may change after the walk. Issue: none.
- Sharing picker when a link names no project and the host shares several: not built (the sequence discards the pairing and says "ask for a link from the project you want"). Under #5049.
- Workflows 2.4: scoreboard #4344 and comparison node #4328 are DEFERRED by manager ruling (tag [PROPOSED]); both issues stay open.
- Workflows 3.2: the ensemble preset (N transcribe -> one critical-review -> resolve) is specified, not built; #3905 needs a real-model CER run and is unclaimed.
- Workflows 3.3: DeepL is no longer a shipped preset (the owner may want a provider choice on Translate; none filed); Catalogue stages have no consistency check (none filed).
- Workflows 3.4: recipes user-level / library-pinned runs need a design: #4277. Seeder drift: #4450.
- Workflows 3.5 (engine) not started; Step 4.4-4.6 app halves (run trace view #4312 residue, Test button #4370) not built; their spec tags stay [GAP]/[PARTIAL].
- Generated/guard data changed in this batch and needs the manager's by-name approval: `scripts/check_endpoint_coverage_matrix_known_gaps.json` (drops GET /api/pair/addresses, adds POST /api/workflow-execution/dry-run), `scripts/check_undo_coverage_known_gaps.json` (adds the dry run: it changes nothing).
- Two trimmed tests were approved earlier (bb3): test_a_paused_page_is_paused_not_failed_5919.py, test_text_reflow.py (each has a new test that is red on the old engine).
- Fixed on the way: #4306 (artifact.translate event loop on a worker thread), the dry-run route's missing read check.

## Rules I kept
Never push, close issues, touch main, run xcodebuild or edit .entitlements; temp libraries only; split to fix size caps, never raise them; every commit has Directed-By and cites an issue; the boundary scan reads each commit, so no /Users/<name>/ paths.
