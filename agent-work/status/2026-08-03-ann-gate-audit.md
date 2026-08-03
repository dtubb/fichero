# Ann gate audit — #4421

**Audited against the code on `origin/integration` at `08562f092`, 2026-08-03.**
Not against commit messages, not against GitHub issue state. Where those disagree with
the code, the code wins and the disagreement is named.

---

## Verdict

**The gate is not met.** Three items block it outright, and one whole link of the core
path has no evidence at all.

**Blocking, in order:**

1. **#4415 — Catalogue re-run still destroys hand corrections on the flagship path.**
   The curation guard was built and tested, but it is wired into exactly one tool that
   the Catalogue preset does not call. This is a data-loss item and it is live.
2. **#4499 — an edited claim does not survive re-extraction.** Filed tonight, unfixed.
   Same defect class as #4415. Ann's corrections are the most valuable data she will
   produce and neither path protects them.
3. **#4496/#4497 — transcription quality.** The ensemble was storing model *commentary*
   as the transcription until a few hours ago; Apple Vision measures CER 0.398 on
   colonial Spanish and cannot be improved by configuration. The core path runs, but
   what it produces on Ann's actual material is not good enough to work from.

**Not blocking but must be decided before handover:** #4400 (the reported stale-engine
dead end is still open on the UDS path Ann would hit), and #4418's text regions being
off by default, which under the "no needless toggles" rule is a half-working affordance.

**What is genuinely good:** the drag/scope/selection cluster (#4401, #4396, #4419), the
reader cluster (#4385, #4373, #4393), and connection honesty (#4380/#4372) are all
fixed *and* pinned by real tests. That is most of the "what on earth" surface, and it is
the strongest part of this gate.

---

## Item-by-item

Categories: **FIXED+TESTED** / **FIXED-UNTESTED** / **PARTIAL** / **OPEN**.

### Data loss and destructive behaviour

| Issue | Verdict | Evidence |
|---|---|---|
| #4401 sidebar drag copies | **FIXED+TESTED** (unit only) | `SidebarDropClassification.swift:159-175` identifies an in-app drag positively by id *before* any file URL; `:132` `isFicheroInternalDragExport` defends the window-wide URL-typed drop that made this survive three prior fixes. Tests: `ContentPaneInternalDragImportGuardTests`, `LibraryDropPairingTests` (15), `SidebarDropPayloadTests`. |
| #4396 run widens scope | **FIXED+TESTED** | `WorkflowRunScope.resolve` (`:58-100`) returns a non-empty selection verbatim regardless of authored `inputSource`; `runWorkflowOnCollection` deleted. Tests: `WorkflowRunScopeTests.collectionWorkflowHonoursASingleSelection` (Daniel's exact case), server `test_catalogue_scope_isolation_e2e.py`. |
| #4419 non-active library unrunnable | **FIXED+TESTED** | `WorkflowRunTargetResolver` — a clicked row is always its own target; folders resolve breadth-first with a cycle guard; narrowing declared via `Resolution.ignoredSelection`. Tests: `WorkflowRunTargetResolverTests` (20). |
| **#4415 corrections survive re-run** | **PARTIAL — blocking** | See below. |
| #4283 empty run reports success | **PARTIAL** | See below. |
| #4414 Catalogue end to end | **PARTIAL** | See below. |

#### #4415 — the blocking detail

`curation_guard.py` (314 lines, new) is real and well tested —
`test_merge_dedup_curation_survival.py` proves a hand-corrected claim and a hand-merged
entity both survive a re-run, and that disagreement is recorded rather than silently
resolved. **But its only import site in `src/` is `tools/merge_dedup_only.py`.**

The Catalogue preset's nodes are `files, transcribe, extract_all,
{people,places,organizations,dates,events,keywords}_folder_cleanup, citations_extract,
aggregate, catalogue`. `merge_dedup_only` is not among them. On the path Ann will
actually run:

- `tools/catalogue.py:701-714` deletes every prior `catalogue`/`catalogue.*` artifact
  unconditionally, with no curation check.
- `tools/catalogue.py:771` sets `container.page_content = markdown` — an unconditional
  overwrite of the folder narrative.
- The word `curation` does not appear in `catalogue.py`, the transcribe tools, or any
  `*_folder_cleanup` tool.

So the issue's own sentence — "the moment Ann corrects an entity and re-runs, her
corrections are gone" — is still true for the Catalogue preset. The guard exists; it is
plumbed to the wrong pipe.

#### #4283 — partial

The guard is now genuinely *reachable*: `files` is a declared LangGraph channel
(`workflows/types.py:311`). Before that, `_detect_empty_text_output` read a top-level key
the builder never wrote, so it short-circuited to "not empty" on 16 of 16 families —
which is why this was green while broken. Now swept by
`test_empty_output_guard_family_sweep.py` across all 16 families against the real builder.

**What is still open:** only an *all files failed* run escalates to `status="failed"`
(`runner.py:1830`). A run that produces nothing without per-file errors is still recorded
`completed`. The only signal is `completion_metadata["empty_output"]` — and grepping the
tree, **nothing reads it**: zero hits in any Swift file, zero in `fichero-server/src`
outside `runner.py`. Per-*step* emptiness is surfaced in `RunTraceModel` (#4284), but
run-level emptiness reaches no surface.

#### #4414 — partial, item by item

| | Item | State |
|---|---|---|
| 1 | scope is exactly what the user chose | **DONE**, tested |
| 2 | folder run's output belongs to the folder | **DONE** — `sources.py:733` `folder_id` port; `test_catalogue_real_preset_run_e2e.py::test_folder_cleanup_writes_its_canonical_lists_to_the_folder` |
| 3 | run records **and displays** its scope | **HALF** — `workflow_runs.resolved_scope` is recorded (`activity_store.py:645`), but `resolved_scope` has **0 occurrences in `tests/contracts/openapi.json` and 0 in any Swift file**. Activity cannot display it. |
| 4 | stop actually stops | **DONE** (see #4402) |
| 5 | an empty run says so | **PARTIAL** (see #4283) |
| 6 | results appear without restart | claimed via #4392, see below |
| 7 | E2E test on the real preset | **DONE with a stated limit** — see the core-path section |

One further note that matters for handover: the shipped Mac client still sends legacy
untyped `inputs["selected_doc_ids"]` at all five call sites (`WorkflowEditor+Actions.swift:103`,
`SidebarItemRow+Workflow.swift:85`, `ContentView+WorkflowActions.swift:272`,
`LibraryView+BatchWorkflow.swift:111`, `BatchStore.swift:49`). The typed `selection`
field arrives via the legacy adapter as `kind=documents`. The "a folder run is
unrepresentable-if-wrong" property therefore holds for the *engine*, not for the client
Ann will run.

### Reader and SVO

| Issue | Verdict | Evidence |
|---|---|---|
| #4385 reader wrap | **FIXED+TESTED** | `document_view.html:185-190` `overflow-wrap:anywhere` + `max-width:100%`; both halves present. `ReaderTranscriptWrapTests` renders the *shipped* template in a real `WKWebView` at 4 pane widths with a 4000-char unbroken token and asserts `scrollWidth <= clientWidth`, with a negative control that catches the pre-fix styling. `ReaderTextPaneWrapTests` does the same for the AppKit pane. This is the best-evidenced item on the gate. |
| #4373 click-to-select page | **FIXED+TESTED** — CLOSED is correct | `ReaderPageActivationState.swift:37-52` — `movesBrowserSelection` true for `.clicked` only; per-window bus, not `.shared`. `ReaderPageActivationTests`, 22 cases, including empty untranscribed pages and "nothing is ever recorded as sent unless it was sent". |
| #4393 claims grouped/reachable/editable | **FIXED+TESTED** (all three clauses) | (a) grouped: `KnowledgeGraphInspectorSection+Grouping.groupedSections`; subject de-dup in `ClaimLine.swift:41-60`. (b) reachable at span level: `ClaimSourceRequest.Precision`, feeding the existing cursor. (c) **editable in place: real** — `EntityKindRow+ClaimBlock.swift:93-98` expands inline into `InlineClaimEditor`, editing S/V/O as separate fields, persisting via `invokeAction("claim.patch")`; `ClaimStore.patch` updates the single row by id, no wholesale re-render. Tests: `ClaimLineTests`, `ClaimSourceRequestTests`, `ClaimDisplayContractTests`. Bracketed internal filename closed and guardrailed. |
| #4394 confidence badge | **PARTIAL** | Client is fully fixed and heavily tested — `ConfidenceBand.swift` renders bands not decimals, `recorded(_:)` is a nil-in/nil-out seam so absence renders *nothing*, and `ordersBefore` keeps unrecorded out of the ranking instead of `?? 0`. 21 tests in `ConfidenceBandTests` including directory-walk sweeps. **But the engine still substitutes 0.5 for absent** at `workflows/tools/extractors.py:808, 842, 1934-1936, 2466`. For the main extractor path, absence never reaches the client, so the exact complaint — "absent and 0.5 are indistinguishable" — is still true end to end. |
| #4418 / #4309 text regions | **PARTIAL** | Capture is complete on **all** vision paths including PDF (`vision_base.py:416-469` flips bottom-left→top-left and links char spans; `:677+` `_pdf_text_layer_geometry` localises every word on the same pass). Exposed on artifact GET. Rendered in Preview for images (`OCRGeometryOverlay.swift`) and PDFs (`PDFPageView+OCRBoxes.swift`). **Three gaps:** both toggles default `false` (`imagePreview.ocrBoxesEnabled`, `pdfPreview.ocrBoxesEnabled`) so out of the box a user sees no regions; PDF rendering is macOS-only (`#if canImport(AppKit)`, iOS load skipped at `PDFPageWithToolbar.swift:253-256`); and the **Reader itself renders nothing** — the WebKit transcript draws no boxes, only the toolbar toggle is plumbed there. Also **NO TEST for `applyOCRBoxes`** — the cropBox-inset offset correction that already needed one bugfix is unguarded. |

### "What on earth" moments

| Issue | Verdict | Evidence |
|---|---|---|
| #4403 "3 results" / "No Documents" | **FIXED+TESTED** | `LibraryEmptyReason.swift` — `SearchHitCounts.total` drives the header, `.nonDocument` explains divergence, active search outranks the collection prompt. `LibraryEmptyReasonTests.theReportedCaseExplainsTheHeader`. |
| #4406 Find counts 314 for 7 | **FIXED-UNTESTED** | Fix is real and the root cause is right — all reader tabs stay in the DOM, CSS-hidden; `ReaderFindInPage.swift:96-141` adds `checkVisibility` and rejects text in hidden parents. **But `ReaderFindScopeTests` regexes the JS source string inside the Swift file.** Nothing executes the JS. The 314-vs-7 count is never measured. Compare #4385, where the same class of fix *is* measured in a real WebView — that is the standard this one does not meet. |
| #4400 stale engine, dead Retry | **PARTIAL — reported symptom OPEN** | Backend half landed: loud `UNSUPERVISED ENGINE` warning (`api/main.py:596-624`), `FICHERO_PARENT_PID` exported by `start_backend.sh`. **But the non-blind recovery UI (Stop it / Use it / Quit) exists only for TCP:8765 + `appManaged`** (`EmbeddedBackendService+Ports.swift:307-369`). The reported case was UDS + `debugExternal`/`externalLocal`, where `ConnectionPresentation.failureAction()` offers only `.resetSignIn`/`.forgetPairing`/`nil` — `.restartEngine` is unreachable. There is no UDS orphan sweep. Retrying against a live stale engine still cannot succeed. NO TEST on the Swift side. |
| #4380 / #4372 connection narration | **FIXED+TESTED** | One pure mapping `ConnectionPresentation.status(phase:ownership:accessError:authBroken:)`; `.starting` says only "Starting engine…"/"Connecting…", all fabricated stage strings gone. `ConnectionPresentationTests` sweeps the full phase matrix asserting no mapped string narrates an unobserved step. |
| #4384 / #4398 stale "still running" | **FIXED+TESTED (core); rest untouched** | `activity_store.recover_stale_runs()` (`:1222-1266`) is **age-based, not PID-liveness**, so it is correct across reboots; `settle_documents_for_dead_run()` flips stuck `processing` documents. Tested by `test_api_startup_recover_stale_runs.py` and `test_recovered_run_settles_documents.py` (10). **Caveat:** it fires on library-open, not periodically. **The UI half of both issues — duplicate rows, badge removal, actionable errors, column choice — has NO CODE and NO TEST.** |
| #4416 storage filename in titles | **FIXED+TESTED, low confidence** | One composer `DocumentTitle.displayName(for:parent:)`. Tonight's `3e1ceae5f` found 7 more *live* leaks — four in the delete-confirmation dialog, two in VoiceOver labels. `DocumentTitleTests` now sweeps 907 files with a `filesRead > 500` floor. **But this is the third hardening pass and the guardrail is regex-over-source; it has missed live leaks twice.** Treat as fixed, not as structurally closed. One known un-allowlisted leak remains: `SidebarItem(name: doc.pageThumbnailLabel ?? doc.name)`. |
| #4402 Stop does not stop | **FIXED+TESTED** | Root cause identified correctly — cancellation was checked only at fan-out and between graph events, so a 200-page node never saw the flag. Moved into `emit_tool_progress` (`builder.py:815-823`), the per-item callback every per-document loop calls. `test_cancel_inside_a_long_node.py` (8). **Pause/Resume share the same node-interior gap and are unverified.** |
| #4395 unembedded documents | **PARTIAL — and the repo says so** | `db/__init__.py:4048-4108` records `last_embed_outcome`, but `embed()` still returns a bare bool and the outcome is a side-channel attribute. `ingest.py:408` `db.embed(doc)` for the primary document is still a bare discarded call — silent exactly as before. `_create_pdf_page_children(auto_embed: bool = False)` still defaults to False. **The 656 existing documents are not backfilled** (deferred to #4302). Four tests that would prove the general contract are strict-XFAIL in `known_specification_failures.txt`. |
| #4392 KG inspector never updates | **FIXED+TESTED for the reported path** | `extractors.py:2777-2782` — the shared `_write_kg_rows` helper now emits whenever anything is written, closing the `kg_writer` default path. Swift plumbing was never broken. `test_kg_write_announces_itself.py` (7). **Defect class open as #4420:** `tools/cleanup.py:818,828,859` still `db.save()` entities and claims emitting only progress events. And `check_emit_change_coverage.py` is green via `KNOWN_GAPS` baselines, not structure — it cannot see through a two-hop helper. |

---

## #4421's three questions, answered

### 1. No data loss — **NO.**

Three live paths can destroy or duplicate Ann's work:

- **#4415** — a Catalogue re-run deletes prior artifacts and overwrites the folder
  narrative with no curation check. Her corrections are gone. **This is the single worst
  item on the gate**, because Catalogue is the thing she is being handed the app to run,
  and correcting entities is the thing she will do after running it.
- **#4499** — an edited claim does not survive re-extraction. `save_claim` dedups on
  text+SVO, so once she edits a claim it no longer matches what re-extraction produces
  and the pre-edit version returns as a duplicate row. Filed tonight, unfixed.
- **#4496 blast radius** — zero of 798 local artifacts stored commentary-as-transcription,
  but **4 Box libraries were never surveyed** (#4498). If Ann's material lives in one of
  those, some of her transcriptions are model chatter presented as text.

#4401 (duplicating drag) is **fixed and tested at the unit level**, and I would rate it
genuinely closed — the fix is at the classification layer that all three drop surfaces
now share. But note there is **no test anywhere that a drop actually delivers anything**:
every test in the family is a classifier or source-shape test, and the repo contains zero
XCUITest drags. That is the exact shape that let this ship green three times. It is not
a reason to reopen; it is a reason not to be surprised.

### 2. No "what on earth" moments — **MOSTLY, with named exceptions.**

Genuinely closed: the search count contradiction (#4403), connection narration
(#4380/#4372), Stop (#4402), stale run status (#4384 core), storage filenames in titles
(#4416, third pass).

Still live:

- **#4400** — on the UDS path, a stale engine still presents a `Retry` that cannot
  succeed. This is the specific "what on earth" the issue describes and it is not fixed
  for the transport Ann's build uses.
- **#4394** — the confidence number is still a fabricated 0.5 for anything the extractor
  did not record. The client would show absence honestly; the engine never lets absence
  through.
- **#4418** — text regions exist, work, and are **off by default**. Under the standing
  rule ("a half-working affordance is worse than an absent one" / "features ON or OFF"),
  a toggle defaulting to off for a shipped capability is the wrong shape. Decide: on, or
  hidden.
- **#4283/#4414 item 3** — an empty run still says `completed`, and the scope a run was
  resolved to is recorded in the database but absent from the OpenAPI contract and from
  every Swift file, so Activity cannot show it. Both are "the app tells her something
  happened when it did not", which is the sentence in #4421's own preamble.
- **#4406** — probably fixed, but the count is never measured. If it is still wrong, we
  will find out from Ann.

### 3. Core path end to end — **links 1, 4 and 5 evidenced; links 2 and 3 assumed.**

| Link | Status |
|---|---|
| **1 import** | **EVIDENCED** — `tests/integration/test_ingest_pipeline.py`, real `ingest_folder()`, real DuckDB, real filesystem walk and checksum. Caveat: file *bytes* are placeholders (`b"fake image data"`), so imported documents are never anything a transcribe node could OCR. |
| **2 transcribe** | **EVIDENCED as a function, ASSUMED as a stage.** `test_paleography_manuscript_fixture.py::test_apple_vision_cheap_tier_cer_on_the_gold_page` runs real Apple Vision on a real manuscript PDF against a gold transcription — that is where CER 0.398 comes from. But it is a bare call on `apple_vision_ocr`, not through a document or the graph. The one real pipeline test, `test_paleography_ensemble_real_providers`, is skipped by default (needs 5 env vars). **Trap worth knowing:** `test_paleography_ensemble_runs_real_manuscript_file`, despite its name, monkeypatches `TOOLS["transcribe"]` to hardcoded strings — no OCR or LLM runs at all. |
| **3 read** | **ASSUMED. No test at all, gated or otherwise.** Nothing connects a produced transcription to a reader-facing GET. The closest, `test_routes_documents.py::test_get_existing`, writes `page_content` from the test itself. This is the weakest link in the entire path — and it is the link #4421 calls "where the actual work happens". |
| **4 extract** | **EVIDENCED for mechanics, seam ASSUMED.** `test_default_workflow_e2e_harness.py` asserts a real `Artifact(transcription)`, real `Artifact(people)`, and a `KnowledgeClaim` carrying `source_document_id` of the page — genuine page-traceability through the real `extract_all` tool and KG writer. But the input text is hand-typed and `chat_structured_with_fallback` is stubbed. |
| **5 catalogue** | **BEST EVIDENCED.** `test_catalogue_scope_isolation_e2e.py` (7 tests, two sibling folders, entities/claims/artifacts land only on the selected folder) and `test_catalogue_real_preset_run_e2e.py` (5 tests driving `runner._run_workflow_in_background`, the real `POST /execute` path, all 12 preset nodes real, real DB writes). |

**On the "real preset" test (`be8bc893e`)** — since the manager asked specifically: it
covers the shipped preset JSON, all twelve nodes, the graph, `execution/runner.py`, every
DB read and write, the merge decisions, the port handoffs, and the run record. It **fakes
`chat_structured_with_fallback`** — no provider is ever called — and its input
transcriptions are hand-seeded `FIXTURE_TEXT` on text-type documents. Its own commit
message says so plainly: *"this proves the wiring and the scope, not transcription or
extraction quality."* That is an honest test and it should be trusted for exactly what it
claims.

**The seams, which is the real answer:**

| Seam | Spanned by a test? |
|---|---|
| import → transcribe | **NO** (one opt-in test, double-gated) |
| transcribe → read | **NO — nothing at all** |
| transcribe → extract | **NO** — every downstream test hand-types `page_content` |
| extract → catalogue | **YES** — three always-running real-graph tests |

There is exactly one genuine whole-path test —
`test_full_book_catalogue_e2e.py::test_tubb2020shift_catalogue_populates_kg`, all real, no
stubs — but it needs `FICHERO_RUN_FULL_BOOK_E2E=1` *and* a path to a personal book PDF
that is not in the repo. It cannot run on a fresh checkout, and it does not touch **read**.

**In one sentence:** the catalogue end of the path is well proven for wiring and scope
with a stubbed model, the transcribe end is proven as an isolated function against a gold
page, and **the middle is a hole** — no default-running test ever takes bytes off disk,
produces a transcription, and carries it forward, and nothing anywhere proves the reader
displays what transcribe wrote.

---

## Fixed but untested — the category most likely to be wrong

Listed deliberately, because tonight produced several and this is where a cheerful audit
would go wrong:

1. **#4406 reader Find** — fix real, test only regexes the JS source. Behaviour unmeasured.
2. **`applyOCRBoxes`** (#4418) — the cropBox-inset coordinate correction that already
   needed one bugfix has no test.
3. **#4400 Swift side** — no test for the dead-end Retry path or UDS orphan detection.
   Only the server-side watchdog warning is tested.
4. **#4401 delivery** — the classifier is heavily tested; that a drop *delivers* is not
   tested anywhere, in any form.
5. **#4416** — tested by a regex-over-source sweep that has missed live leaks twice.
6. **#4384/#4398 UI half** — no code and no test.
7. **Pause/Resume** — share #4402's node-interior gap; unverified.

---

## Also relevant to the handover decision

- **#4497** — Apple Vision's `language` argument does nothing and the call site hardcodes
  `en`. CER 0.398 on colonial Spanish is not improvable by configuration. Ann should be
  told what transcription quality to expect before she starts, not after.
- **#4472** — iPad has no runnable test target at all (`fichero-ipad.xctestplan` names
  `FicheroTests`, which does not support iPad). If Ann is given an iPad build, it is
  untested by construction. Decision for Daniel.

---

## What would move the gate

In priority order, and this is the shortest honest list:

1. Wire `curation_guard` into the Catalogue preset path — `catalogue.py`'s artifact
   delete and `page_content` overwrite (#4415).
2. Fix `save_claim` dedup so an edited claim survives re-extraction (#4499).
3. Survey the 4 remaining Box libraries for commentary-as-transcription (#4498).
4. Stop the engine substituting 0.5 for an absent confidence (#4394, `extractors.py`).
5. Make `.restartEngine` reachable on the UDS transport, or make the Retry honest (#4400).
6. Decide #4418's toggles: on by default, or hidden.
7. One test that carries real bytes from import through transcribe into read. Any one.
   The middle of the path currently has no evidence at all.
