# Handoff: fix/gate-reds-holds (review 4 = agent-work/status/briefs/review-gate-reds-4-verdict.md)

Closed, each with a test in tests/unit/security/test_holds_close_6320.py that fails without the fix (reverted once to check) and a spec line in docs/contributor_manual/specs/source/rights-and-access.md:
N1 snapshots, N2 registry delete, N8 tasks + policies, N3 chains (earlier). This session:
- N4 plain reads: GET /api/claims, /claims/{id}, /agent-memory(+/{id}), /chat/conversations(+/{id}) leave out or refuse (403) what rests on a page the caller cannot read (`document_reader`).
- N5: `action_context` sets `may_read` (api/auth.py `_action_reader`); claim.list/get, entity.list/get/neighborhood, search.query (total_results minus the dropped rows) use it.
- N6: resume checks the checkpoint's, the run start's and the call's document ids with `write_check`; `/threads/{id}/resume` left BODY_IDS_CLEARED.
- N7: `document.dataset:dataset_query` is on authz.SCOPED_LIBRARY_READ_ROUTES (its body `read_check` walks the folder); walker test accepts `read_check(` as the filter.

Open / known:
- search.query total_results is only reduced by this page's drops (a later page's hidden rows are still in the total).
- Entity HTTP routes (not actions) and the KG neighborhood route are not filtered; entities hide only when ALL their source_document_ids are unreadable.
- Conversations are withheld by scope_document_id/document_ids, not by message text.
- check_engine_imports_bundled (rc 2, needs an app_packages path) and check_swiftlint_warning_ratchet (rc 1) are red and not caused here.
- test_check_spec_milestones::test_real_specs_pass_offline fails from fichero-server/, passes from the repo root.
- ruff: 3 old errors in tests/unit/transport/test_share_scope_5967.py (lines 7, 17, 38), not touched.
- pytest-asyncio is missing in the Air/M4 venvs (P1); not touched.
Run: OMP_NUM_THREADS=2 PYTHONPATH=src, integration .venv python, one pytest at a time.
