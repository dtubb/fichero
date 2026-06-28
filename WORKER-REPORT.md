# Docs lane worker report (lane/docs)

Worker: Claude, in worktree `~/code/fichero-worktrees/ms-docs`. All work committed
(authored as Claude, Co-Authored-By Daniel), nothing pushed. The manager merges.
`mkdocs build --strict` passes after every change.

## Commits (newest first)

| sha | summary |
|---|---|
| `43db49f6` | rewrite CONTRIBUTING for the current worktree agent workflow |
| `576e0b16` | encode docs-placement, commit-attribution, worker-orchestration in AGENTS + skills |
| `69ba68b3` | add unstable-API banner to API reference |
| `223dd940` | correct FAQ models, support channel, how-its-built |
| `5774ba0d` | fold CHANGELOG into RELEASE_NOTES, drop CHANGELOG.md |
| `8693e1d8` | platform language is iOS / iPadOS / macOS only |
| `e5374d18` | fix spelling typos in README intro |
| `97fdb596` | rename site/docs/developer to contributor |
| `ac7eee69` | move agent scratch out of docs/ into agent-work/from-docs/ |

---

## TASK 1 — docs/ vs site/docs/ organization

**Established rule** (now encoded in AGENTS.md → Docs Placement):

- `site/docs/` = the PUBLIC MkDocs site. Curated user manual, contributor docs, API
  reference, How It's Built. Public-worthy only.
- `docs/` = INTERNAL dev reference, never published: durable architecture/dev guides,
  runbooks, module references.
- `agent-work/` = agent scratch: session notes, handoffs, QA logs, reviews,
  validation reports, audits, triage, design explorations, proposals. Not published.
- delete = pure crud / superseded.

**Key constraint discovered:** the repo already declares (in `mkdocs.yml`) that
`docs/` "stays the agent working area and is never published," and several `docs/`
files are hard-wired into scripts/tests I may not edit (`.py`). So the public
curated architecture already lives in `site/docs/`; I did **not** promote raw
internal design docs into the public site (they carry issue numbers, draft statuses,
and "for Daniel" notes). TASK 1 therefore became a de-clutter of `docs/` into
`agent-work/`, not a publish.

### Decision table

Files moved to `agent-work/from-docs/` (MOVE-to-agent-work):

| entry | why |
|---|---|
| `MORNING-TEST.md` | point-in-time overnight-run checklist (agent scratch) |
| `orphan-triage-report.md` | triage report |
| `perf-library.md` | "what I checked" perf investigation notes |
| `architecture/search_audit.md` | dated audit |
| `architecture/api_consistency_audit.md` | dated audit |
| `architecture/api/notes_annotations_audit.md` | dated audit |
| `architecture/swiftui/ios_appkit_audit.md` | dated audit |
| `architecture/swiftui/mac_assed_audit_2026.md` | dated audit |
| `reviews/` (1 file) | read-only review report |
| `superpowers/` (3 files) | issue plans + design specs (agent working material) |
| `design/` (9 files inc. shell-mockups html) | design explorations / proposals |
| `archive/` (2 files) | archived / superseded design + QA checklist |

KEEP-internal (stayed in `docs/`):

| entry | why |
|---|---|
| `CLAUDE.md`, `README.md`, `ROADMAP.md` | durable, referenced by skills/root CLAUDE |
| `architecture/**` (remaining) | durable architecture + design reference |
| `architecture/api/**` (overview, key_files, dev standards, checklists, KG_ENDPOINTS, contracts) | backend dev reference |
| `architecture/swiftui/**` (remaining) | frontend dev reference + design keystones |
| `agent-workflow/**` | agent-process reference; wired into `scripts/cron_check.sh` and the published How It's Built page |
| `qa/**` | **load-bearing**: `scripts/check_verify_all_modes.py` asserts `docs/qa/CAPTURE_SMOKE_MATRIX.md` exists at that path |
| `remote-pairing-smoke-checklist.md` | **load-bearing**: same verify script + `docs/VERIFY.md` reference it |
| `VALIDATION.md`, `VERIFY.md` | verification-pipeline reference (not reports) |
| `BUNDLING_BACKEND.md`, `SETUP_BUNDLED_BACKEND.md` | dev setup reference |
| `ingest_*.md`, `supported_file_types.md` | module reference |
| `remote-backend-acenet.md`, `remote-backend-tailscale.md` | supported-connection reference |
| `release/**`, `release-notes-0.0.2.md` | release runbooks + notes |
| `developer/cli-test-harness.md`, `UI_MAP.md` | dev reference |

DELETE: none executed. Nothing in `docs/` was unambiguously crud once history and
script/test wiring were accounted for.

**Flagged (did not guess):**
- `docs/release-notes-0.0.2.md` could fold into `RELEASE_NOTES.md` later, but TASK 4
  scoped only CHANGELOG/HISTORY, so I left it in place.
- `agent-work/from-docs/` is the holding folder I created so the moves are grouped
  and trivially reversible; rename/redistribute if you prefer a different layout.
- Stale inbound references to the moved paths remain only in historical logs
  (`HISTORY.md`, `STATE.md`, `MEMORY.md`) and old `agent-work/proposals/*` — left as
  historical record. One app-code comment (`_entity_writer.py:9`) points at
  `docs/superpowers/plans/2026-04-28-typed-entity-storage.md`, which did not exist
  before this change either; untouched per the no-.py rule.

---

## TASK 2 — rule encoded in AGENTS.md + skills

AGENTS.md gained three sections:
- **Worker Orchestration** — manager runs worktree-isolated workers in tmux, reviews
  (ponytail + `/code-review`), build-gates, runs `verify_all`, merges via PR, closes
  issues, re-dispatches, checks in ~15 min.
- **Commit Attribution** — each agent authors as itself (Claude / Codex), committer
  stays the human, credit Daniel via `Co-Authored-By`.
- **Docs Placement** — the four-home rule above.

Skills updated to point at these rules: `dispatch-worker`, `session-start-manager`,
`session-start-worker`.

---

## TASK 3 — README typos

Spelling only, wording/meaning preserved. ~22 fixes across the intro paragraphs:
secodnary, researchs, owrk/owkr, colletion, nad, plagerism, interpretion, arhcival,
ethngroaphic, amterials, allos, differnet, workflwos, hunreds, expali, peoplke,
wbeiste, aism, hwo, ti, plus its/a/and homophone fixes. No reframing.

---

## TASK 4 — one canonical RELEASE_NOTES.md

- Folded the two hand-written `CHANGELOG.md` entries (0.0.2 unreleased, 2026.04.29
  first public release) into `RELEASE_NOTES.md` under a new **Curated changelog**
  section (newest-first, headings demoted to nest). The generated **Dated changelog**
  below stays owned by `scripts/release-notes-gen.sh` (which only appends older-dated
  entries, so the curated section is safe).
- `git rm CHANGELOG.md`.
- **HISTORY.md NOT folded or deleted (flagged).** Despite the task wording, this
  repo's `HISTORY.md` is 2,605 lines of agent **session summaries**, not release
  history, and `agents/skills/session-end/SKILL.md` appends to it. Folding it would
  pollute release notes; deleting it would lose history and break session-end. Left
  in place for Daniel to decide. (It arguably belongs in `agent-work/`, but moving it
  would break the session-end append path, so I held.)

---

## TASK 5 — platform language

Removed from README: the "(with tvOS and visionOS planned)" aside and the
`Web client | future | Planned` surfaces-table row. `site/docs/**` already carried no
tvOS/visionOS/web-client language. macOS 26 Tahoe requirement left as-is. (The one
remaining "future" hit is inside generated `api-reference/openapi.json` endpoint
prose, left untouched.)

---

## TASK 6 — developer → contributor

`git mv site/docs/developer site/docs/contributor`. Updated `mkdocs.yml` nav (section
renamed Developer → Contributor; all paths repointed; Architecture Notes stay grouped
under it) and the README pointer. Relative `../architecture/...` links inside the
section are unchanged by the rename.

---

## TASK 7 — FAQ corrections

- **Models:** model-agnostic via LangChain provider integrations (LiteLLM for cost /
  discovery only, not routing). Local on-device: Apple Foundation Models, MLX,
  LM Studio, Ollama. Cloud: OpenAI, Anthropic, Google. User picks. Also corrected the
  "Does it work offline?" and "Is my data secure?" answers that named only Ollama.
- **Support:** GitHub Discussions for user questions/feedback; GitHub Issues is the
  AI-agent development backlog, not user support.
- **How is Fichero built:** honest plain description of Daniel directing a
  manager-with-workers loop with build/test gating; links the How It's Built page.
  Dropped the "vibe-coded" framing.

---

## TASK 8 — API reference banner

Added a `!!! warning "Work in progress, unstable"` admonition at the top of
`site/docs/api-reference/index.md`: endpoints/shapes will change before 1.0, not yet
a stable contract, API version tracks the dated release.

---

## Extra — CONTRIBUTING.md

Rewrote the stale claim-the-issue text to describe the real workflow (AI agents
directed by Daniel; manager runs worktree-isolated workers in tmux, committing as
themselves; manager review + build-gate + verify_all + PR merge). Pointed "more
detail" at the renamed `site/docs/contributor/setup-and-contributing.md`.

---

## Extra — component docs as thin pointers (single source of truth)

`fichero/` and `fichero-engine/` per-component docs now point to the canonical docs
and keep only component-specific essentials:

- `fichero/AGENTS.md`, `fichero-engine/AGENTS.md` → rewritten as thin pointers to root
  `AGENTS.md` + `site/docs/contributor/` + `site/docs/user/`, plus a 2-3 line
  "component essentials" block (start the engine; lint; `PYTHONPATH`; scripts entry
  points).
- `fichero/README.md` → kept the app-specific layout, key concepts, and build/run;
  replaced the duplicated Notes (add-swift-file, OpenAPI sync) with a pointer to root
  AGENTS.md.
- `fichero-engine/README.md` → kept layout, the HTTPS-launcher run section, how-it-works,
  MCP, and OCR/HTR guidance; collapsed the duplicated test/lint into a pointer; fixed
  the `developer/` links; corrected the provider note (LangChain integrations; LiteLLM
  for cost/discovery only, not routing) to match the canonical README/FAQ.

Also fixed stray `site/docs/developer/` links the TASK 6 rename had missed in `USER.md`
and `docs/README.md` (my first-pass grep was scoped too narrowly). Verified none remain.

Note: `docs/CLAUDE.md` still describes LLM calls "via LiteLLM" in a couple of places;
left untouched here since it is the large internal architecture guide and out of scope
for this lane. Flagged for a follow-up pass if you want it aligned with the
LangChain-integrations / LiteLLM-cost-only framing.

## Extra — user manual buildout (#1796) + accuracy polish

- **New `site/docs/user/interface-tour.md`** — an element-by-element tour of the
  window for end users: the four regions, the sidebar modes
  (Library/Search/Chat/Workflows/Chains/Activity/Automation/Batches/Model Comparison),
  the library layouts (icon/list/table/map), the reading area and its reading layouts
  (None/Standard/Widescreen), the full inspector tab set
  (Content/Outline/Annotations/Notes/Entities/Knowledge Graph/Citations/Edits/Info),
  plus workflows, chat, search, import, and settings. Plain language, app-not-backend,
  with `[Screenshot: …]` placeholders marking where art goes. Added to nav. Names
  grounded against `InspectorTab.swift`, `LayoutMode.swift`, `SidebarViewTypes.swift`.
- **Accuracy sweep across the published site** (fix-then-sweep):
  - Dropped the stale `Artifacts` inspector tab from `reading-and-editing.md` and the
    user index; added the real Entities / Knowledge Graph / Citations tabs.
  - Replaced the "vibe-coded" framing on the home page (`index.md`) with the honest
    manager-with-workers description, matching FAQ + How It's Built.
  - Corrected the LiteLLM-routing framing everywhere it appeared in published docs
    (`ai-and-privacy.md`, `architecture/api/overview.md`,
    `architecture/swiftui/overview.md`, `contributor/README.md`): calls go through
    LangChain provider integrations; LiteLLM is for model discovery + cost only.
- **Flagged:** the user index links `Tailscale Private Transport` at
  `../remote-backend-tailscale.md`, which lives in the unpublished internal `docs/`
  tree, so it 404s for public-site visitors. Pre-existing; left in place rather than
  remove Daniel's link. Decide whether to publish a user-facing remote-access page or
  drop the link.

## Voice + verification

- No em dashes and no "not-X-but-Y" in authored prose. Folded `CHANGELOG`/`RELEASE_NOTES`
  content keeps its original em-dash style (verbatim fold, and the existing release
  notes already use that style throughout); flagged here rather than mass-rewritten.
- No `.swift` or `.py` files touched.
- `mkdocs build --strict` passes.
