# Fichero — Roadmap (priority order)

> **READ THIS AT SESSION START** (and `/session-start-manager`). It is the
> source of truth for *what to work on next* and *in what order*.

**Worker model-selection policy (token economy):** default workers to the cheap
tier — **Claude Sonnet** (frontend) + **codex 5.4-mini** (backend). Escalate to
**Opus / codex 5.5** ONLY for keystone/cross-cutting work (new stores, the action
layer, anything high-blast-radius). All workers run in **external worktrees**
(`~/code/fichero-worktrees/`) via the codex/claude CLIs — **never** the Agent
tool's `.claude/worktrees/` (uvicorn `--reload` watches the repo).

Milestones are tackled in this **tiered order**, not arbitrarily. The rule that
makes the order work: **build the gates first**, so every later refactor that
breaks an architectural rule fails loudly instead of rotting. A continuous
**verify/gardener agent** runs across all tiers (see bottom).

> Operating model unchanged: dated releases, one milestone in focus at a time,
> features not release-gated. This just sets *which* milestone is in focus next.

## ▶ CURRENT WORK ORDER (2026-06-11) — authoritative

**Everything is filed into a milestone; we work milestones properly, in this
four-phase order** (Daniel, 2026-06-11). The tiers below are finer-grained
backing; this is the sequence. Work Phase 1 to a good stopping point before Phase 2, etc.

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
- **EPIC #2056 AI Infrastructure:** #2057 (LangChain `.abatch` — 1000s-of-images lever), #2055 (client reuse), #2062 (bounded concurrency/memory), #2058 (dynamic profiles), #2063 (local-only), #2066 (local MLX via mlx-lm-server), #2060 (Apple Vision OCR), #2061 (image-edit backend OpenCV vs Quartz), #2059 (Apple skills vs AI skills), #2065 (code review).
- Milestone: Workflows.

### Phase 4 — RESEARCHER / AI / AGENT (north-star, on phases 1–3)
- **EPIC #2067 in-app Agent** — Workspace ≡ RAG/Graph chat ≡ Agent; an **agent is a principal**: #2068 (Researcher→Agent), #2069 (manager-with-workers runtime), #2070 (tasks/milestones UI), #2071 (Pi harness on mlx-lm-server), #2072 (agent workspace + scratchpad), #2073 (visibility), #2074 (run-scoped undo). Agent acts across all surfaces (search / 2D library / edit-workflows / review-runs) via audited tools (#1848); **reuses accounts #2022 + attribution #2023 + ACL #2024 + undo #2015 — don't build a parallel agent system.**

---

## Tier 0 — Gates & Verify (continuous; bootstrap first)
The safety net. Everything below is verified against it.
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

## Tier 1 — Infrastructure
The plumbing the architecture stands on.
- Per-library change-stream + emit on entities/claims/documents — #1863 ✅
- `@Observable` store registry on `LibraryReference` — EntityStore ✅, ClaimStore ✅
- One audited action layer (UI = chat tools = App Intents = tests = audit) — #1848
- Remote & self-hosting (engine may be remote) — #74
- Milestones: **Observable Data Layer**, **Remote & Self-Hosting** (#74)

## Tier 2 — Right approaches / architecture  ◀ CURRENT FOCUS
Observable, reactive, declarative. **A view never hand-rolls an endpoint nor
accesses one directly — it observes an `@Observable` store; the store is the sole
endpoint + change-stream accessor.** Remote-save / no local paths / pure-display
frontend. Critical for Researcher, multi-user, and MCP-agent edits.
- Migrate the 17 remaining `@StateObject service` views to stores (#1882/1883/1889/1903/1904/1905)
- Retire NotificationCenter bus — #1862 ✅
- Milestone: **Observable Data Layer**

## Tier 3 — Important features
- Undo / redo (#1832), Users / permissions + audit log, Sharing (#75),
  Notifications & Watchlist (#76)

## Tier 3b — Domain features
Once the architecture + features above are solid, the domain milestones:
- **Importer** (#57, IIIF bulletproof #72), **LangGraph workflow node editor**
  (Workflows #54), **Apple Intelligence backend** (on-device extraction),
  **persistence correctness — "make sure things save"** (round-trip every edit
  through the store→backend→DB and back; a guardrail/test, not vibes),
  **Mind Palace** (#12), **Researcher** (#53), **Chat** (#22), **Search** (#17).

## Tier 4 — Mactastic
Native SwiftUI `List`/`Table`/`OutlineGroup` (no hand-rolled UI), system fonts,
**no emoji**, SF Symbols everywhere (esp. sidebar), window chrome & toolbars.
- Milestones: **Native SwiftUI Controls**, **Mac Polish — Fonts/SF Symbols/No Emoji**, **Window Chrome & Toolbars** (#71)

## Tier 5 — Testing
Frontend + backend coverage to target; new public API ships with a test.
- Milestone: **Test Coverage — Frontend & Backend**, **API Surface & Test Harness** (#70)

## Tier 6 — Profiling & preload
Time/memory hotspots (Instruments + py-spy/tracemalloc) → optimize; strategic
data preloading/prefetch policy at the store layer. — #1917, #1918

## Tier 7 — UI consistency
Final cohesion pass once the controls + polish + data layer are uniform.

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
2. Check GitHub issues/milestones; find the **highest-incomplete tier** with
   ready work.
3. **Choose next**: 1 big issue OR 3–10 small issues in the **same milestone**
   (so the worker uses its full context). — a `/choose-next` selector skill #1924
4. **Delegate** to an external-worktree worker (Sonnet/codex-mini default; Opus/
   codex-5.5 for keystones) running `/session-start-worker`.
5. Build/test-verify the result, cherry-pick to the branch, clean the worktree,
   update issues. Repeat.
