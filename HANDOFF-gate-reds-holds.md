# Handoff: fix/gate-reds-holds (review 4 = agent-work/status/briefs/review-gate-reds-4-verdict.md)

Closed, each with a test in tests/unit/security/test_holds_close_6320.py that fails without the fix (reverted once to check) and a spec line in docs/contributor_manual/specs/source/rights-and-access.md:
N1 snapshots, N2 registry delete, N8 tasks + policies, N3 chains (earlier). This session:
- N4 plain reads: GET /api/claims, /claims/{id}, /agent-memory(+/{id}), /chat/conversations(+/{id}) leave out or refuse (403) what rests on a page the caller cannot read (`document_reader`).
- N5: `action_context` sets `may_read` (api/auth.py `_action_reader`); claim.list/get, entity.list/get/neighborhood, search.query (total_results minus the dropped rows) use it.
- N6: resume checks the checkpoint's, the run start's and the call's document ids with `write_check`; `/threads/{id}/resume` left BODY_IDS_CLEARED.
- N7: `document.dataset:dataset_query` is on authz.SCOPED_LIBRARY_READ_ROUTES (its body `read_check` walks the folder); walker test accepts `read_check(` as the filter.

Also closed (second pass): search.query gives no exact total_results to a caller with a reader (None; has_more from the raw count); entity routes list/get and kg/graph/neighborhood and kg/search filter via `entity_visible`/`claim_visible` (api/main.py); whole-library routes (entity top, claim-counts, digest, documents, co-occurrence, drill-down, biography, export, place, linked-places, alias-map, resolve; kg graph metrics/paths/centrality/etc.; claim similar/contradictions/evidence-chain/semantic search; entity semantic search) take `whole_library_reader_only` and are 403 for such a caller. Conversations: withheld by scope_document_id/document_ids (rule stated in the spec); unscoped messages are not scanned.

Third pass: every route under /api/kg, /api/claims, /api/claim-links, /api/entities either filters its rows (GET entities, entities/{id}, claims, claims/{id}, kg/search, kg/graph/neighborhood, claim-links/{id}) or depends on `whole_library_reader_only` (router-level in the kg/claim/entity modules, per route for the claim and entity writes). Guard: test_a_new_knowledge_route_must_filter_its_rows_or_refuse_a_caller_with_a_deny. pykeen model delete / stored verify left NO_CALLER_CLEARED (they depend on the caller now).

Open / known:
- Nothing known unwalked in the entity, claim and KG families. Other families (not these prefixes) are as in #6325.
- has_more on search.query reveals that more raw rows exist (stated in the spec).
- A caller with a deny loses the whole-library views (by design).
- check_engine_imports_bundled (rc 2, needs an app_packages path) and check_swiftlint_warning_ratchet (rc 1) are red and not caused here.
- test_check_spec_milestones::test_real_specs_pass_offline fails from fichero-server/, passes from the repo root.
- pytest-asyncio is missing in the Air/M4 venvs (P1); not touched.
Run: OMP_NUM_THREADS=2 PYTHONPATH=src, integration .venv python, one pytest at a time.

Fourth pass (review 5, NOT READY at 1cb2be776): O1 DONE (authz.reads_every_gated_page; document_reader returns None for a caller who reads every gated page; test_o1_...). 
NEXT, per the Manager's plan (message 2026-11-01): (2) turn briefs/sweep_permissions_probe.py (reviewer writing it) into a real test: seed a secret, fire every served route and action as alice, bob, carla, dana; known holes = named xfails citing #6325; controls owner/plain editor/plain viewer must keep working. (3) work review-gate-reds-5-verdict.md "What Monday needs" in order: H5 (a query param is a target id only if the route declares it), H7, H9, H1/H8/N6, H2, H3/H4, H6; unscoped conversations per author; fix at the choke point. (4) update #6325 text (what stays open) with a comment; no names/page text. Commit after each item. Final message to team-lead: head, sweep result, suites, what stays open.

Fifth pass (review 5 list, all done in this order, one commit each, sweep green): the route sweep is `fichero-server/tests/unit/security/test_route_sweep_permissions_6325.py` (refuses to run unless HOME, the MLX runtime and the library are inside the test's scratch dir; network, subprocess, kill and deletes outside temp raise; known holes are strict xfails in `HOLES`, empty now). H5 `authz._declared_query_names` (a query name counts only if the route declares it); H7 `_ID_LIST_KEYS`; H9 `accounts._require_owner_for_writes` on the local-inference, local-models, machines and registry routers and the chain preset; H2; H3/H4 `chat.conversation_visible` (unscoped = its author's alone, `metadata.author`); H1/H8/N6 `main.run_check` + router-level `run_routes_checked` + `run_scope.run_document_ids/node_document_ids` (execute also checks the recipe's nodes); H6 owner-only export routes. #6325 text updated with what stays open.
Open: the 20 OPEN entries in the no-caller guard list; a run that names no page on its record; legacy conversations with no author; body-id routes fail closed for a shared-folder person; sweep takes about 3 min at load 30-40 (3 phases of ~1 min).
Run the suites in the FOREGROUND: a pytest started with `&` ignores SIGINT and fails test_the_engine_is_stopped_on_ctrl_c_through_atexit.
