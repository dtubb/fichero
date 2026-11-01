# Source Model — Rights, consent and access — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — a "Who may see this" section: recording rights and consent on a source or any
> part of it; community protocols and labels; restricting, redacting and truly removing
> material; and what exports and training sets do with restricted material.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT — raised by review, 2026-09-19. The maintainer has
> ruled that it belongs in this set and who may act; the rest is PROPOSED.** A slice of the source model: read
> `source-model.md` first. Every behaviour below is tagged **[GAP]** with its issue. Nothing here is built.
> What exists today (VERIFIED on disk, `fichero_server/security/authz.py`): a person has one of
> three roles in a project: **owner**, **editor** or **viewer**; and **grant-and-deny overrides
> on a target and everything under it** already exist, enforced on every audited write
> (`actions/registry.py`) and in search. They stop at a document, not a word. The sharing and
> accounts specs have not been read in full for this slice, and must be before approval.
>
> **Routed fact, 2026-09-20 (#4917, read in review; in the worktree, not yet committed when this
> was written).** The permission layer's one ancestor walk now resolves an artifact, segment,
> pass, match, version, forwarding note or carry to its document, then walks the folders above
> it. So a grant or deny on a document or folder reaches everything the source model hangs on
> that document, and a lookup fault denies. The walk still does **not** go below a document:
> an override placed on a segment id matches that id alone, because the walk does not follow
> `Segment.parent_segment_id`. If the maintainer rules that rights become grants and denies on
> a segment, the build is one more step in that same walk (segment, parent segment, document),
> never a second check. This changes nothing about the block below.
>
> **BLOCKED (purge only).** Purge waits on the audited-action layer's split of each record into a
> chained part (who, what, when, ids, version numbers, a keyed fingerprint) and a content part
> outside the chain that a purge can blank, so the chain still checks out and the words are gone
> (ruled 2026-09-20; see "Rulings of 2026-09-20" in `source-model.md`). That split belongs to the
> audited-action layer, not to this set, and is not built yet. The other blocking question is
> answered: see Rulings.

## Intent

Fichero is meant to serve under-resourced and Indigenous languages. Material in those
languages often carries obligations: a community's protocols about who may see, hear or
share something; a speaker's consent, which can be withdrawn; a family's privacy; a
repository's conditions. The field's name for the principle is CARE (collective benefit,
authority to control, responsibility, ethics), alongside FAIR; its working tools include
Traditional Knowledge and Biocultural labels.

Because the source model lets anything be addressed down to a word, a restriction must be
able to apply down to a word too: one name in a diary; one passage of a recording; one
photograph on a page. And because the model exports everything and builds training sets,
restrictions have to hold **before** any of that exists, not be added after.

(Evidence note: CARE and the TK labels are named from general knowledge and are to be checked
against their sources before approval.)

## The design (proposed)

- **A rights record** can be attached to a project, a source, or any segment. It says: who
  holds rights or authority; what was consented to, by whom, when; any conditions; any
  **labels** from an open list; who recorded this, and when. Traditional Knowledge and
  Biocultural labels belong to the communities that apply them and are administered by Local
  Contexts; Fichero carries them faithfully and does not invent them. A project can also keep
  labels of its own.
- **It passes downward, and only tightens.** A rights record on a project covers everything in
  it; a record lower down may restrict further, never loosen what is above it.
- **Who may do what** (ruled 2026-09-19). **Owners and editors** can set rights records,
  restrict and redact. **Only the owner can purge.** A **viewer** never sees restricted
  material. **Ruled 2026-09-20: only the people a rights record names see restricted
  material**; being an editor is not enough.
- **Restricted** means those not allowed do not see a segment's picture, readings, marks or
  statements. For them it is **hidden, and the fact that something is hidden is shown** ("one
  passage on this page is restricted"). It is never silently dropped.
- **A reference does not leak.** A citable reference to a restricted segment opens to
  "restricted" for someone not allowed, never to its content.
- **Exports, training sets and the synced folder leave restricted material out by default**
  and say how many segments they left out. Including it takes a deliberate, recorded act by
  someone allowed to restrict (an owner or an editor). The filter sits **once**, in the
  exporter's one record stream, not in each writer (routed to `export/exporter.md`).
- **Sent to a model?** Whether a segment may be sent to a cloud model, to a local model only,
  or to none, is part of its rights record. The engine refuses, and says why, when a workflow
  would break it.
- **Redaction** is a verb of its own, different from delete: the segment stays, its content is
  covered for everyone not allowed, and the covering is visible as a covering (in the Source
  view, the Reader, exports and pictures of the page).
- **Removal on request.** "Nothing is ever destroyed" cannot be the whole story when consent
  is withdrawn. A **purge** truly removes a segment's content. Its reach is stated: the
  readings, pictures, marks and rights-holder's words; everything worked out from them
  (search entries, vectors, word-level analysis); the files in the synced folder; and the
  quoted words inside any claim that rested on it. A claim itself is kept, with a plain note
  that its evidence was removed, so nothing points at nothing. A purge cannot reach what has
  already left the machine (an export, a shared training set), and Fichero keeps no list of
  what was exported (ruled 2026-09-19): following that up is the researcher's own job, and
  the purge says so plainly. A purge is rarer and louder than delete; it cannot be
  undone; and it leaves a note that something was purged, by whom, when and why, without
  saying what it was.
- All of these are audited actions, and work the same from the app, MCP and the command
  line.

## Behaviors (every one is **[GAP]**: designed, not built; each cites its issue on milestone `source-model`, 322)

- `source.rights.one-check` — **[PARTIAL]** (#4953) a rights record is enforced by the existing permission layer (a
  grant or deny on a segment id, inherited the way it already is); there is no second check. The record
  says what is meant and why (ruled 2026-10-04).
  **Built, engine side (2026-09-28):** `authz._allowed` ends in `_rights_refuse`, so a restricting record refuses
  every account it does not name -- owner and editor included (ruled 2026-09-20) -- for reads and writes, on its
  target and everything under it; two restrictions on the chain need both names; a withdrawn one restricts
  nothing; a library with no restricting record costs one query and behaves as before; a lookup error refuses.
  `rights.set` refuses a restriction that does not name the person setting it, out loud, rather than lock them
  out or silently add them (`fichero-server/tests/unit/security/test_rights_enforcement.py`, 11 tests, 8 failing
  on the code before). **Not built:** the app saying WHY something is refused (a restricted page reads as denied).
- `source.rights.record` — **[PARTIAL]** (#4953) a rights and consent record can be attached to a project, a source
  or any segment, with labels from an open list. **Built, engine side:** `RightsRecord` (`models/rights.py`)
  with holders, consent (what, by whom, when), conditions (capped: it enters the audit chain), open labels,
  a restriction with the accounts it names, and model use. `rights.set` / `rights.withdraw` are audited and
  undoable (`fichero-server/tests/unit/api/test_rights_records.py::TestARecordSaysWhatItSays::test_a_record_hangs_on_the_library_a_source_or_a_segment_with_open_labels`,
  `::TestWithdrawingAndUndo::test_a_withdrawn_record_stops_applying_and_undo_brings_it_back`). A restriction
  that names nobody is refused. **Not built:** any surface; enforcement (`one-check`).
- `source.rights.tighten-only` — **[OK]** (→ #4953) a record passes downward; a lower level may restrict further
  and never loosen. `effective_rights` combines every live record from the library down: restricted if ANY
  record restricts, readers the INTERSECTION of each restricting record's names, model use the STRICTEST
  stated. A record that would loosen model use is refused out loud, naming what is above it, rather than
  silently ignored (`fichero-server/tests/unit/api/test_rights_records.py::TestItPassesDownAndOnlyTightens::test_a_lower_record_narrows_who_may_see_and_cannot_widen_it`,
  `::TestItPassesDownAndOnlyTightens::test_an_unrestricted_record_below_does_not_lift_a_restriction_above`,
  `::TestItPassesDownAndOnlyTightens::test_model_use_takes_the_strictest_and_a_looser_record_is_refused_out_loud`).
- `source.rights.who-acts` — **[PARTIAL]** (#4953) owners and editors set rights records, restrict and redact; only
  the owner can purge. **Built:** setting and restricting, through the existing write check (a record's
  target is a write target, so a viewer is refused before the action runs:
  `fichero-server/tests/unit/api/test_rights_records.py::TestWhoActs::test_a_viewer_cannot_set_a_record_and_an_editor_can`). **Not built:** redact and purge.
- `source.rights.restricted-is-said` — **[GAP]** (#4953) for anyone not allowed to see it (always a viewer, and any editor or owner the
  rights record does not name: ruled 2026-09-20), a restricted segment's content is hidden, and the page says
  that something is hidden.
- `source.rights.citation-does-not-leak` — **[GAP]** (#4953) a reference to a restricted segment opens to
  "restricted" for someone not allowed.
- `source.rights.exports-leave-out` — **[GAP]** (#4953) exports, training sets and the synced folder leave
  restricted material out by default and report how much.
- `source.rights.model-use` — **[GAP]** (#4953) a segment's record says whether it may go to a cloud model, a
  local model, or none; the engine refuses a workflow that would break it, and says why.
- `source.rights.redact` — **[GAP]** (#4953) redaction covers a segment's content visibly, everywhere it would
  appear, without deleting it.
- `source.rights.purge-is-an-action` — **[GAP]** (#4953) a purge is an action in the one audited registry, the same
  shape as the purge that exists for draft entities; not a separate route.
- `source.rights.purge` — **[GAP]** (#4953) a purge removes a segment's content, cannot be undone, and leaves a
  note that says who, when and why.
- `source.rights.purge-reaches-derivatives` — **[GAP]** (#4953) a purge also removes search entries, vectors,
  pictures, synced-folder files and quoted evidence; a claim that rested on it is kept with a
  stated absence.

## Test matrix

To be filled at approval.

## Open questions

Most were ruled on 2026-09-19: see "Rulings of 2026-09-19" and "Still open" in
`source-model.md`. The former blocking question (who enforces a rights record) is answered; see
Rulings.

## Rulings

- **2026-10-04 (#4953): one check.** The existing permission layer enforces; a rights record says
  what is meant and why, and is turned into grants and denies on segment ids, inherited the way
  they already are. There is no second permission system (`source.rights.one-check`).
- **2026-10-04 (#5182, confirming the ruling of 2026-09-28): a page deny hides the claims drawn
  from it.** Entity, claim and project reads filter out items drawn only from denied pages and
  count them as withheld; an entity or claim with no source page stays visible
  (`source.rights.claims-with-only-denied-evidence-are-hidden`).
- **2026-11-01 (#6320): the plain list and read routes hide them too.** `GET /api/claims`, `/api/claims/{id}`,
  `/api/agent-memory`, `/api/agent-memory/{id}` and the chat conversation list and read leave out (list) or refuse
  (read, 403) a claim, note or conversation resting on a page the caller may not read (`source.rights.claims-with-only-denied-evidence-are-hidden`).
  `POST /api/actions/invoke` and the chat tools share that reader: `claim.list`, `claim.get`, `entity.list`, `entity.get`,
  `entity.neighborhood` (no edge from a hidden claim) and `search.query` (it gives no exact `total_results` to a caller who reads only some pages, because a count would include the pages left out) answer as the plain routes do.
  The entity routes (`GET /api/entities`, `/{id}`), `GET /api/kg/graph/neighborhood/{id}` and `GET /api/kg/search` leave out
  (lists, edges, hits) or refuse (a single read, 403) what rests only on pages the caller may not read. The routes that count or
  walk the whole library's claims and entities (entity top, claim counts, digest, documents, co-occurrence, drill-down,
  biography, export, place, linked places, alias map, resolve; the KG graph metrics, paths, centrality, communities, similar,
  components, triangles and clustering; claim similar, contradictions, evidence chain and semantic search; semantic entity
  search) are refused to such a caller, since a count or a path cannot be filtered afterwards.
  The same refusal covers every other read and write of the entity, claim and knowledge-graph families (predictions, pykeen,
  review, mutations, inclusion, render, curation rules, entity curation and audit, triangulation, SPARQL and RDF export,
  claim links, the entity inspector, the review queues, rebuild, merge, dedupe, and the claim and entity create, change and
  delete routes): a caller whose reads differ page by page is refused them, and a new route under those prefixes fails the guard
  (`test_a_new_knowledge_route_must_filter_its_rows_or_refuse_a_caller_with_a_deny`) until it filters its rows or does the same.
  A caller is refused these only when their reads could differ from the owner's: a person with a deny, a folder-scoped role, or a
  restricted page they are not named on. The library's owner (with no override of their own) and a named reader keep them (O1): another editor's restriction on one page never turns the owner's views or whole-project Table off. The limit: those lists and counts include a restricted page's row and claims for the owner, though the page itself stays unreadable to the owner unless a rights record names them.
  **The limit of `search.query`'s answer: with no exact total it still gives `has_more`, taken from the raw result count, so a
  caller can tell that more rows exist beyond the page, though not how many or whether they are theirs.**
  **The rule for a conversation: one scoped to, or answered from, a denied page (`scope_document_id`, `document_ids`) is
  withheld. One with no scope has no page to test, and a deny cannot be told from message text, so for a caller whose reads
  differ page by page it is its author's alone (`metadata.author`, the person who started it or copied it); one with no author
  on record is withheld from them. The owner and a plain editor or viewer see all. The same rule covers read, list, change,
  copy, delete, save-as-workspace, reorder and continuing it in chat, through the routes and the `conversation.*` actions (H3, H4).**
  `POST /api/workflow-execution/threads/{id}/resume` is refused, and returns no run state, to a caller who cannot write
  every page the checkpoint, the run's start or the call names (`source.rights.every-id-in-a-request-is-checked`).
  A query parameter names a target only if the route declares it (`source.rights.every-id-in-a-request-is-checked`): `?x_id=<a folder
  I may read>` on a route that reads no `x_id` changes nothing, so it cannot turn a library-level read or write into a folder-level one (#6325, H5).
  A write's target pages are read from every `*_id`, `*_ids`, `ids` and `items` in its params, at any depth (H7), so `document.copy_into_project`
  and `document.transfer` are checked on the pages they name.
  The Mac's own machinery is the owner's: every write under `/api/local-inference`, `/api/local-models`, `/api/machines`, `/api/registry` and
  `POST /api/chains/presets/paleography` is refused to anyone but the owner (reads stay open); the MLX runtime, a model, a paired machine or
  the list of libraries is not changed by an editor or viewer (`POST /api/library` included, review 8 item 6; H9, `sharing.owner-only-asserted-in-the-action`).
  The gate holds at the action too, not only at the route: `provider.*`, `document.relink_originals` and its undo, `library.release`,
  `library.unicode_merge`, `model.download`, `import.file`, `import.folder`, `import.xlsx` and `kg.set_external_authority_enabled` are `owner_only`
  (the app's owner), so `POST /api/actions/invoke`, MCP and chat cannot reach them with library write alone; a guard
  (`test_an_owner_only_route_has_no_open_action_twin_6325`) fails when an owner-only route's action is open.
  The routes that rank or draw the whole library (`POST` and `GET /api/search/explain`, `GET /view/kg/global`, `POST /api/multilingual/entities/search`)
  are refused to a caller whose reads differ page by page; the roots list (`/api/documents/collections`) and the sample pages leave out a page the caller
  may not read, and `GET /api/kg/search` leaves out a note resting on a page or folder they may not read (H2).
  A run is shown, and acted on, only to a caller who reads (writes) every page its record names (`source.rights.every-id-in-a-request-is-checked`):
  the scope it resolved, the inputs it was started with and the ids its recipe's nodes name, which is where a folder source names its folder.
  `status`, `history`, `run`, `episodes`, `stream`, the diagrams, comparisons and `read-again` are reads or writes on those pages; `cancel`, `pause`,
  `resume` and delete are writes; starting a run (execute, chains, batches, schedules) goes through one check, `recipe_check`: the pages the recipe's nodes name must be writable, and a caller whose reads differ page by page may not start a recipe whose source names no page (a folder by name, a search, a whole collection or the artifact and annotation sources) or whose step writes to a path (`export_documents`, `write_file`); a `sub_workflow` step counts as the steps of the child it names, to 16 levels; four of the shipped recipes (the ones with such a step) are therefore the owner's to run, since a recipe with an `export_documents`, `write_file` or `cli_agent` step (a program on the Mac) is run, scheduled or batched only by the owner of the app (or anyone when multi-user is off), whatever pages it reads; deleting runs by state is refused to a caller
  whose reads differ page by page. A run whose record names no page, or whose recipe has a source that reads by a word or a name or a step that writes a path, is refused to such a caller on every run route (the record does not say who started it) (H1, H8, N6).
  An export that writes to a path the caller names on the Mac (`/api/export/jsonl`, `training`, `parquet`, `eleventy-site`, `markdown-folder`, `word`,
  `excel`: every one with an `output_path`) is an editor's right (owner ruling 2026-11-01, reversing H6): the body-id read checks are its gate, so a
  caller whose reads differ page by page exports only pages they read.
  Approving or rejecting an agent's write (`POST /api/agents/write/approve`) is the owner's (`sharing.owner-only-asserted-in-the-action`).
  What a person shared one folder loses by this (fail closed, none of it has an app caller but chat and search): `POST /api/search` (403 with or without a
  scope), chat of any kind (even scoped to their own folder), the catalogue workbook export and the image-batch preview, whose folder is in the body and
  so is no declared id (H5). They keep the page, its children, the Table on their folder, the Inspector and the knowledge graph tab.
  A person shared one folder opens the Table on it: `POST /api/documents/dataset/query` with that folder as `parent_id` answers,
  and a query for another folder, or none (the whole project), is refused (`source.rights.every-id-in-a-request-is-checked`).
- **2026-11-01 (#6325, review 8): the model-comparison routes that run a tool or a recipe go through the same check as a run.** `compare-tool` reads every id its inputs name (a `folder_id` too), treats the tool as a one-step recipe for `recipe_check`, and reads the library the request is for whatever `library_path` the inputs carry; `compare-workflow` and `compare-node` run `recipe_check` on the recipe they resolve. A caller whose reads differ page by page is refused a search or folder-by-name source or a step that writes a path there as at execute.
- **2026-11-01 (#6325, review 9; owner ruling): a recipe step that writes a path or runs a program (`export_documents`, `write_file`, `cli_agent`) is an editor's right to save, run and schedule.** Review 8's item 5 (owner-only for every caller) and H6 were reversed by the owner: writing a path on the Mac is part of an editor's work. A caller whose reads differ page by page is still refused such a recipe at the save (item 4) and at every start, so the save door and the run door agree. Library-wide sources (a search, a folder by name) are unchanged: refused only to a caller whose reads differ page by page.
- **2026-11-01 (#6325, review 8): a caller whose reads differ page by page cannot save a recipe that `recipe_check` would refuse them to run.** Creating (`POST /api/workflows`), importing and replacing the steps of a recipe (`PUT`), and the actions `workflow.create`, `workflow.import` and `workflow.update`, are 403 when the steps include a source that names no page or a step that writes a path (children of a `sub_workflow` step included), because a schedule or file watcher fires a saved recipe with no caller to check. `PATCH` changes only the name, description, format, folder and order and is unchanged.
- **2026-11-01 (#6325): a claim or entity action that names a record is refused to a caller whose reads differ page by page.** `claim.delete`, `entity.delete`, merges and the other claim/entity actions that take an id follow their routes (which sit behind the whole-library reader check): the library owner and a caller who reads every page may run them, a denied editor or a person shared one folder may not. Actions that create (no id) are unchanged (`source.rights.claims-with-only-denied-evidence-are-hidden`).
- **2026-11-01 (#6325, owner ruling): a viewer may not spend the owner's keys or use the network.** `POST /api/model-comparison/compare`, `/compare-node`, `/api/research/tools/web-search` and `/browser-navigate` need an editor or the owner (a viewer, or a person shared a folder to read, gets 403); the single-user app is unchanged (`source.rights.a-viewer-cannot-spend-keys-or-network`).
- **2026-11-01 (#6325, owner ruling): a person shared one folder to edit may write notes and annotations on that folder only.** `PUT /api/documents/{id}/notes` and `POST /api/annotations` with a `document_id`, `page_id` or `folder_id` inside the shared folder succeed; outside it, or naming nothing, they are 403, and a person shared to read only gets 403 everywhere. A research project's notes (`/api/research/notes`) are the project's, not a folder's, and stay editor-only (`source.rights.shared-folder-editor-writes-notes-on-that-folder`).
- **2026-11-01 (#6325, owner ruling): the library owner keeps the knowledge views and the Table when another editor restricts a page; approved as built** (the lists then include that page's row for the owner).

## Triaged from the backlog (2026-10-04)
- `source.rights.engine-wide-stores-follow-the-library` — **[GAP]** (#5181) engine-wide stores that mention a library's content (agent write audit, PyKEEN jobs and predictions, etc.) are filtered by that library's permissions, and truly global settings are owner-only.
- `source.rights.claims-with-only-denied-evidence-are-hidden` — **[PARTIAL]** (#5182; `fichero-server/tests/unit/security/test_holds_close_6320.py::test_n4_plain_reads_of_claims_agent_memory_and_conversations_leave_out_what_rests_on_a_denied_page`, `::test_n5_the_entity_and_kg_routes_hide_what_rests_on_a_denied_page_and_aggregates_are_refused`; left: the `withheld` count on every read and the claim supported by a readable page showing only the readable evidence are not pinned by a test) a claim whose only evidence is a denied page is hidden, and one also supported by a readable page stays showing only the readable evidence, across entity, claim and project reads. Each read counts what it filtered out as withheld; an entity or claim with no source page at all stays visible. (Ruled 2026-09-28, restated 2026-10-04.)
- `source.rights.every-id-in-a-request-is-checked` **[PARTIAL]** (#4958; `fichero-server/tests/unit/security/test_holds_close_6320.py::test_h5_a_query_name_no_route_declares_is_not_a_target`, `::test_h7_the_write_check_reads_ids_and_items`, `::test_h1_h8_n6_a_run_over_a_folder_source_is_shown_and_acted_on_only_to_a_caller_who_reads_its_pages`; left: the dataset-query, resolve-location and two-things-same-document cases are not pinned by a test of their own) a read whose ids travel in the request body (resolving a location, a dataset query, search explain) is checked against every document it names, and an action that names two things (a pass and its source result, two matched segments) refuses unless both belong to the same document.
- `source.rights.a-viewer-cannot-spend-keys-or-network` — **[OK]** (`fichero-server/tests/unit/security/test_holds_close_6320.py::test_viewers_cannot_spend_keys_or_use_the_network`, `::test_item6_a_viewer_does_not_make_a_library_of_his_own_and_so_an_owner_role_to_spend_keys`) `POST /api/model-comparison/compare`, `/compare-node`, `/api/research/tools/web-search` and `/browser-navigate` need an editor or the owner; a viewer cannot make a library of their own to become its owner (`POST /api/library` is the app owner's).
- `source.rights.shared-folder-editor-writes-notes-on-that-folder` — **[OK]** (`fichero-server/tests/unit/security/test_holds_close_6320.py::test_o2_a_person_shared_one_folder_writes_notes_and_annotations_on_that_folder_only`) a person shared one folder to edit writes notes and annotations on that folder only; outside it, or naming nothing, is 403.
- `sharing.every-route-keeps-a-denied-page-private` — **[OK]** (#6325; `fichero-server/tests/unit/security/test_route_sweep_permissions_6325.py::test_no_unlisted_leak`) every served route and action, fired as a caller with a deny on a folder, a viewer, and a person shared one folder, shows no text from the denied page and runs no machine-owned or spend route; a leak not named in the sweep's `HOLES` fails the test.
