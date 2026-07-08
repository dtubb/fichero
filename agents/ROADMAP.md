(AI generated. Not reviewed.)

# Fichero — Roadmap (priority order)

> **READ THIS AT SESSION START** (and `/session-start-manager`). It is the
> source of truth for *what to work on next* and *in what order*.
>
> **Selector order:** `scripts/choose_next.py` reads the **`## Tier` PRIORITY
> SPINE at the bottom of this file** — milestone order = ascending milestone
> due-date (kept in sync on the GitHub board). The 4-phase narrative below is the
> *why*; the spine is the *what-next*. Re-sorted 2026-07-03 by the board organizer.

**Worker model-selection policy (token economy):** default workers to the cheap
tier — **Claude Sonnet** (frontend) + **codex 5.4-mini** (backend). Escalate to
**Opus / codex 5.5** ONLY for keystone/cross-cutting work (new stores, the action
layer, anything high-blast-radius). All workers run in **external worktrees**
(`~/code/fichero-worktrees/`) via the codex/claude CLIs — **never** the Agent
tool's `.claude/worktrees/` (uvicorn `--reload` watches the repo).

**The sequence is the 4-phase work order below.** The rule that makes it work:
the **continuous gates** (Tier 0) run across every phase, so a refactor that
breaks an architectural rule fails loudly instead of rotting. A **verify/gardener
agent** runs the gates continuously (see bottom).

> Operating model unchanged: dated releases, one milestone in focus at a time,
> features not release-gated. This sets *which* phase/milestone is in focus next.
> (The old Tier 1–7 ordering is **superseded** by the 4 phases; its specifics are
> folded in, with a cross-reference map near the bottom.)

## ▶ CURRENT WORK ORDER (2026-06-11) — authoritative

**Everything is filed into a milestone; we work milestones properly, in this
four-phase order** (Daniel, 2026-06-11). The tiers below are finer-grained
backing; this is the sequence. Work Phase 1 to a good stopping point before Phase 2, etc.

### ▶▶ REFINED ORDER (2026-06-11 PM design session) — authoritative over the 4 phases below
A long design session reshaped the plan. Order is now:

**1. INFRASTRUCTURE (doing NOW — finish before Mac):**
- Remaining backend: **#2045** SSE hardening · **#2026** Tailscale · **#2028** infra code-review · **#2076** audit-chain ordering.
- **Embeddings done right** (Daniel: re-embed, don't pin — #2049 resolved): **#2095** pluggable embedding provider (local bge-m3/Qwen3-0.6B + OpenAI + Apple; correct per-model formatting; 1024-dim so no store change; re-embed all).

**2. MAC-ASSED APP (#2030) — the big UI reform, built on a NEW data foundation:**
- **#2081 — Library node model (FOUNDATION, do early):** library = ONE tree of nodes; each node has a structural kind + a **prototype (class)**; **folder ≈ workspace ≈ room** are container prototypes; **entities + aliases** are node kinds; tasks/milestones/notes are prototype attributes; **views** (list/table/icons/map/graph/3D) render any container; **chat scopes to any container**. *(Tinderbox-for-archives.)* Gaps: prototype system, alias kind, entities-as-nodes, tasks-on-any-container.
- **#2031 — persistent shell** (route every mode's detail through ONE shared inspector; modes→views). Design approved; brief staged. *(Search/KG/Mind-Palace collapse into VIEWS, not modes.)*
- Reading surface: **#2090** multi-page (1/2-up native + 3/4-up custom grid + continuous; PDFs+images) · **#2093** first-class translation view · ✅ #2052 PDF thumbnail · #2053/#2080 page labels.
- Library/legibility: **#2020** entity provenance Table · **#2091** references-as-nodes + 'who references this' · **#2088** BibTeX export UI · **#2092** language policy (global/per-doc) · **#2089** editor consolidation (no Word-clone).
- Design doc: `docs/contributor/architecture/swiftui/mac_shell_design_proposal.md`.

**3. MAKE-VISIBLE + AI-INFRA BACKEND (after Mac UI):**
- **#2082** surface the shipped security backend (Accounts/Users #2083, multi-user toggle #2084, audit 'who-changed-what' #2085, sharing/roles #2086, backups #2087) + Trash UI #2077.
- **#2094** all models in Settings → Models (central storage, select/delete, local+API+Apple providers).
- **AI-infra #2056**: batching #2057, profiles #2058, bounded concurrency #2062, local-MLX #2066, Apple Vision #2060, local-only #2063.

**4. RESEARCHER / AGENT (#2067):** Workspace ≡ RAG/Graph chat ≡ Agent; agent is a principal that edits nodes (reuses #2081 + #2024 + #2015 + undo). Pi harness on MLX.

> The 4 phases below remain the frame; this refined order supersedes their internals.

### Cross-cutting GUARANTEE — Privacy: nothing goes online without consent
**No information is sent to any online/cloud service unless the user explicitly
allows it.** Default-private posture; a global **local-only / no-cloud** setting
(#2063) that *refuses* cloud providers; a clear **indicator** whenever a path
would send data online; local engines (MLX / Apple on-device, #2066) are
first-class so the app is fully usable with zero cloud. Enforced at the
LLM/vision/API dispatch layer, surfaced in the UI. This is a product principle.

### Foundations already shipped (what the phases stand on)
- **Audited action layer** #1848 ✅ — every mutation = typed, attributed, undoable action.
- **Observable substrate** ✅ — per-library stores + emit_change + SSE.
- **Undo** #2015 ✅ (single-action; run-scoped grouped undo = #2074, queued).
- **Multi-user accounts BACKEND** #2022 ✅ — scrypt + sessions, behind `FICHERO_MULTIUSER` OFF, security-reviewed.
- **AI-infra hygiene:** model-cache #2050 ✅, engine `workers=1` #2044 ✅, Settings-crash #2051 ✅.

### Phase 1 — INFRASTRUCTURE  ◀ doing now
Multi-user/remote + observable + AI-infra hygiene.
- **EPIC #2021 multi-user/permissions/remote** → #2023 (actor from session, NEXT) → #2043 (tamper-evident audit log) → #2025 (kill ambient authority) → #2024 (per-library ACL + private-by-default sharing) → #2048 (bind host) → #2026 (Tailscale).
- Audit-derived (#2027/#2028): #2045 (SSE network hardening), #2046 (scheduled/offsite backups).
- **Observable Data Layer:** #1935 (one code path per endpoint/store + shared renderer), #2001/#2008/#2009.
- **AI-infra hygiene:** #2055 (API-client/Apple-bridge reuse), #2049 (embedding pooling — **DANIEL: pin vs re-embed decision**).
- Data safety: **Trash** #2075 (soft-delete + restore), backups #2046.

### Phase 2 — MAC-ASSED APP
The native structure + polish.
- **EPIC #2030 window structure** → #2031 (persistent shell, keystone) → #2032 (zoned toolbar) → styling #2033–#2040 + Liquid Glass #2041.
- Bugs/features: #2020 (entity-provenance table), #2052 (PDF thumbnail), #2053 (page labels), #2042 (File ▸ New library).
- Milestones: Window Chrome & Toolbars, Mac App Shell, Mac Polish, Library & Reading Surface (structural), Finder-style selection EPIC #1962, semantic-fonts EPIC #1969.

### Phase 3 — WORKFLOW & AI INFERENCE (efficiency)
Make inference fast, batched, scalable, private.
- **EPIC #2056 AI Infrastructure:** #2057 (LangChain `.abatch` — 1000s-of-images lever), #2055 (client reuse), #2062 (bounded concurrency/memory), #2058 (dynamic profiles), #2063 (local-only), #2066 (local MLX via mlx-lm-server), #2060 (Apple Vision OCR), #2061 (image-edit backend OpenCV vs Quartz; see `docs/contributor/architecture/image_editing_backend_strategy.md`), #2059 (Apple skills vs AI skills), #2065 (code review).
- Milestone: **Workflows & Catalogue Hardening**

### Phase 4 — RESEARCHER / AI / AGENT (north-star, on phases 1–3)
- **EPIC #2067 in-app Agent** — Workspace ≡ RAG/Graph chat ≡ Agent; an **agent is a principal**: #2068 (Researcher→Agent), #2069 (manager-with-workers runtime), #2070 (tasks/milestones UI), #2071 (Pi harness on mlx-lm-server), #2072 (agent workspace + scratchpad), #2073 (visibility), #2074 (run-scoped undo). Agent acts across all surfaces (search / 2D library / edit-workflows / review-runs) via audited tools (#1848); **reuses accounts #2022 + attribution #2023 + ACL #2024 + undo #2015 — don't build a parallel agent system.**

---

## Continuous gates & verify (cross-cutting — runs across ALL phases)
The safety net, always on. Every phase's work is verified against it (this is
"Tier 0" — not a phase, a backstop).
- Multi-level `verify_all` (fast / standard / full / profile) — #1910
- Guardrails (each enforces a tier below, ratcheting KNOWN_VIOLATIONS → 0):
  view→store (#1911), native-controls (#1912), no-emoji/SF-Symbols/fonts (#1913),
  swiftlint-zero (#1915), comment-hygiene (#1916), db-access (#1876 ✅), coverage (#1916)
  - **endpoint-usage** — every backend endpoint is actually used (no dead routes) — #1920 (extends #1874)
  - **CLI ↔ frontend ↔ OpenAPI parity** — both clients consume the same contract; no drift — #1921 (extends #1147)
  - **feature-flag hygiene** — flags that must ship OFF are OFF (no half-built feature on by default) — #1922
  - **OpenAPI contract sync** — openapi.json matches models; CLI + Swift client generate from it — in verify_all ✅
  - **version ↔ date consistency** — app version string matches today's dated-release scheme — #1923
- **Completeness matrices** (EPIC #1925) — generate a matrix from `openapi.json`
  and assert every endpoint is fully wired, programmatically:
  - every endpoint is **used** (no dead routes) AND reachable via an **@Observable store** AND by the **CLI** AND by **SwiftUI** (no surface left out)
  - every library auto-gets its store/observable component (no per-library gaps)
  - every mutating op is **undoable** (undo coverage is consistent) and has consistent **CRUD**
  - every user action appears in **menu + context menu + toolbar + keyboard shortcut** (the Mac-assed completeness matrix)
- Milestone: **Developer Experience** (#64)

## How the earlier tiers fold into the 4 phases (cross-reference)
The previous Tier 1–7 plan is **superseded** by the 4 phases above; its still-live
specifics map as follows (so nothing is lost):

- **old Tier 1–2 (Infrastructure / Observable architecture)** → **Phase 1**.
  Observable substrate ✅ (#1863, EntityStore/ClaimStore, NotificationCenter
  retired #1862); remaining `@StateObject service`→store migration
  (#1882/1883/1889 …) + one-code-path #1935; remote & self-hosting #74 → #2026/#2048.
- **old Tier 3 (undo / users / permissions / sharing / notifications)** → **Phase 1**
  (#2015 ✅/#2074, #2022/#2023/#2024, Sharing #75, Notifications #76).
- **old Tier 3b domain (importer #57/IIIF #72, workflow editor #54, Apple-Intel
  backend, persistence-correctness, Mind Palace #12, Researcher #53, Chat #22,
  Search #17)** → split: workflow/inference → **Phase 3** (#2056); Researcher/Chat
  → **Phase 4** (#2067, which subsumes Researcher+RAG-chat+Agent); importer/
  Mind-Palace/Search → their milestones, scheduled within the relevant phase.
- **old Tier 4 (Mactastic — native controls, fonts/SF-Symbols/no-emoji, window
  chrome #71)** → **Phase 2** (EPIC #2030 + Finder-selection #1962 + semantic-fonts #1969).
- **old Tier 5 (Testing)** → continuous (Test Coverage milestone) + the gates above.
- **old Tier 6 (Profiling & preload #1917/#1918)** → **Phase 3** (efficiency) + gates.
- **old Tier 7 (UI consistency)** → final pass after Phase 2.

---

## The verify/gardener agent (continuous)
A recurring agent (cron or on-demand) that:
1. Runs `verify_all --standard` + every guardrail.
2. Reads each guardrail's KNOWN_VIOLATIONS / coverage gaps and **writes milestone
   progress** (e.g. "Observable Data Layer: 5/17 views migrated").
3. Surfaces the **next issue to pick** from the highest-incomplete tier.
4. Files new issues for any fresh violation/coverage gap.

So the milestones are *driven by the gates*: as guardrails ratchet to zero, the
tier is done and the next tier is chosen automatically. — gardener agent #1919

## The manager loop (every manager session)
1. **Read this ROADMAP** + `STATE.md` + `MEMORY.md`.
2. Check GitHub issues/milestones; pick ready work from the **current phase**
   (the 4-phase work order above) — Phase 1 until it's at a good stopping point.
3. **Choose next**: 1 big issue OR 3–10 small issues in the **same milestone**
   (so the worker uses its full context). — a `/choose-next` selector skill #1924
4. **Delegate** to an external-worktree worker (Sonnet/codex-mini default; Opus/
   codex-5.5 for keystones) running `/session-start-worker`.
5. Build/test-verify the result, cherry-pick to the branch, clean the worktree,
   update issues. Repeat.

---

# ▶▶ PRIORITY SPINE — machine-read by `scripts/choose_next.py`

> Milestone order = ascending milestone due-date on the GitHub board (priority
> order). The selector walks these tiers top-down and returns the highest-priority
> ready, unclaimed work. Milestone names **must match GitHub exactly**. Keep this
> list and the board's `due_on` in sync — single source of truth for "what next".
> Re-sorted 2026-07-03 (dependency-driven: foundations first, security early, app
> structure before UI reform, UX before chrome).

## Tier 1 — Foundation — build · dev · contract · guardrails · hygiene
- Milestone: **Dev & Build Harness**  (due 2026-07-05)
- Milestone: **Developer Experience**  (due 2026-07-09)
- Milestone: **API Surface & Test Harness**  (due 2026-07-13)
- Milestone: **Programmatic Guardrails**  (due 2026-07-17)
- Milestone: **Repo Hygiene & Structure**  (due 2026-07-21)

## Tier 2 — Security, backend & connection hardening — contract bulletproof before UX
- Milestone: **Security**  (due 2026-07-23)
- Milestone: **Connection & Startup Bulletproofing**  (due 2026-07-25)
- Milestone: **Multi-user & Shared Libraries**  (due 2026-07-29)
- Milestone: **Device Pairing & Discovery**  (due 2026-08-02)
- Milestone: **Remote & Self-Hosting**  (due 2026-08-06)
- Milestone: **Workflows & Catalogue Hardening**  (due 2026-08-10)
- Milestone: **AI Backend Hardening**  (due 2026-08-14)
- Milestone: **Import & Index Modes**  (due 2026-08-18)

## Tier 3 — App-structure foundations — reorganize + substrate BEFORE UI reform
- Milestone: **SwiftUI App Structure & Naming**  (due 2026-08-22)
- Milestone: **Observable Data Layer**  (due 2026-08-26)
- Milestone: **Node Model & Endpoint Unification**  (due 2026-08-30)

## Tier 4 — Reach — embedding + multiplatform
- Milestone: **iOS/iPad Embedding & Multi-Library**  (due 2026-09-03)
- Milestone: **Multiplatform — iOS / iPadOS / Mac**  (due 2026-09-07)

## Tier 5 — Cross-platform interaction model
- Milestone: **iOS/iPad/Mac UX**  (due 2026-09-11)

## Tier 6 — Mac native shell · chrome · polish (the reform cluster)
- Milestone: **Mac App Shell**  (due 2026-09-15)
- Milestone: **Window Chrome & Toolbars**  (due 2026-09-19)
- Milestone: **Mac Polish — Fonts, SF Symbols, No Emoji**  (due 2026-09-23)
- Milestone: **UI Reform — Representations**  (due 2026-09-27)
- Milestone: **UI Reform — Inspector & Annotation**  (due 2026-10-01)

## Tier 7 — Content surfaces — reading / knowledge / library features
- Milestone: **Library & Reading Surface**  (due 2026-10-05)
- Milestone: **KG & Hermeneutics**  (due 2026-10-09)
- Milestone: **Search**  (due 2026-10-13)
- Milestone: **Importers**  (due 2026-10-17)
- Milestone: **Settings & Providers**  (due 2026-10-21)
- Milestone: **Bibliography & Citations**  (due 2026-10-25)
- Milestone: **Curation**  (due 2026-10-29)
- Milestone: **Image Editing**  (due 2026-11-02)
- Milestone: **Activity & Automation**  (due 2026-11-06)
- Milestone: **Exporter**  (due 2026-11-10)
- Milestone: **Mind Palace**  (due 2026-11-14)

## Tier 8 — AI / agent / chat north-star
- Milestone: **Chat**  (due 2026-11-18)
- Milestone: **Workflows**  (due 2026-11-22)
- Milestone: **Chat & Agent**  (due 2026-11-26)
- Milestone: **Researcher**  (due 2026-11-30)
- Milestone: **MCP**  (due 2026-12-04)
- Milestone: **Watched-Entity Research Agents**  (due 2026-12-08)
- Milestone: **Clip Service — Web & Document Capture**  (due 2026-12-12)

## Tier 9 — Capture pipelines
- Milestone: **Archive Capture — Mobile & Camera Intake**  (due 2026-12-16)
- Milestone: **Archive Capture — Automation & Provenance**  (due 2026-12-20)

## Tier 10 — Sharing & notifications
- Milestone: **Sharing & Collaboration**  (due 2026-12-24)
- Milestone: **Notifications & Watchlist**  (due 2026-12-28)

## Tier 11 — Ship — release / web / docs
- Milestone: **Release & Distribution**  (due 2027-01-01)
- Milestone: **Website**  (due 2027-01-05)
- Milestone: **Documentation**  (due 2027-01-09)

## Tier 12 — Source archives — ongoing corpora / demo-test datasets
- Milestone: **Source Archives**  (due 2027-01-13)

<!-- One umbrella (#65) owns every corpus as issues; per-corpus milestones
     #84/#85/#86/#87/#88/#89 were over-split + closed too soon (demo data
     isn't done) and folded in 2026-07-03. Do NOT re-create per-corpus
     milestones — file corpus issues here. -->

## Tier 13 — Far future
- Milestone: **tvOS — Apple TV port**  (due 2027-01-29)
- Milestone: **visionOS — Apple Vision Pro port**  (due 2027-02-02)
