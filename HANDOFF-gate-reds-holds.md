# Handoff: fix/gate-reds-holds, head 50d1c3fc8 (review 4 = agent-work/status/briefs/review-gate-reds-4-verdict.md)

Done and tested (tests/unit/security/test_holds_close_6320.py, 24 tests; guard in test_every_id_param_reaches_its_document.py, 13 tests; both pass):
N1 snapshots, N2 registry delete, N8 tasks + policies (all `dependencies=[Depends(_require_owner_or_bootstrap)]`), N3 chains (`_check_chain` in routes/workflow/chains.py),
G4 (assert_library_* counts only with named=/_every; NO_CALLER_CLEARED sweep, 51 entries PUBLIC/OPEN #6325), P1 test-file claim.

NOT done (in verdict order):
- N4 reads: GET /api/claims, /api/claims/{id}, /api/agent-memory, /api/chat/conversations (+/{id}) show denied text to alice/bob (and carla/dana with a decoy for claims, agent-memory). Filter through readable_documents / document_reader (api/main.py).
- N5: set `may_read` in `action_context` (api/auth.py) so /api/actions/invoke and chat share one reader (ActionContext.may_read exists); filter claim.list, claim.get, entity_*; search.query still reports total_results of the unfiltered set (fix the count).
- N6: POST /api/workflow-execution/threads/{id}/resume: check the checkpoint's documents; return no state to a caller who may not read them.
- N7: shared-folder person: POST /api/documents/dataset/query {parent_id: A} -> 403 (carla). In routes/document/dataset.py the read_check passes parent_id, but the dependency/`assert_library_read_authorized` with scoped user and `None`... find which check refuses (probably the query-less library read in get_library_database); give the dataset route the body's parent_id as the target, as other body routes do.
- Each needs a test in test_holds_close_6320.py (fixture `four`, helper `_all_refused`) that fails without the fix. Then rerun: tests/unit/security, tests/unit/scripts (guards), the changed test files; all scripts/check_*.py (only check_engine_imports_bundled and check_swiftlint_warning_ratchet are red, known).
- Remember: one pytest, named files, OMP_NUM_THREADS=2, PYTHONPATH=src, zsh needs ${=VAR} to split file lists.
