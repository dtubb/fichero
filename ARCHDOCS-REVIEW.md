# Architecture Docs Review — `docs/architecture/swiftui/` + `docs/architecture/api/`

**Lane:** `lane/archdocs` · **Date:** 2026-06-27 · **Author:** Claude (opus worker)
**Scope:** accuracy-vs-code, audit-incorporation, consolidation, placement for the
SwiftUI + API architecture docs (plus the two sibling top-level audits).
**Verification:** jcodemunch against `local/fichero-29aa4eed` + `gh issue`/milestone state.

---

## TL;DR for Daniel

- **The audits and design proposals have largely been ACTED ON.** The keystone shell
  work (#2031/#2032/#2033), the change-stream (#1863), observers-everywhere (#1851),
  notes/annotations parity (#1759), and the whole api-consistency cleanup
  (#1412–#1417, #1710) are all **CLOSED and in code**. EntityStore / ClaimStore /
  LibraryChangeStream / `change_stream.py` / `emit_change` all exist.
- **Almost every remaining finding is already tracked** by an open EPIC
  (#1455 mind-palace fold, #1848 action layer, #2096/#2101 iOS, #1443 endpoint
  coverage, #1859 mac-assed, #1824 unified search). I filed **one** net-new issue
  (**#2709**) for the one concrete gap that no open issue captured.
- **Placement:** the durable *principles/standards* docs (SWIFTUI_PRINCIPLES,
  development_standards, appkit_interop) are the only ones worth promoting to the
  public site so agents and people read the same doc. I did **not** move them —
  `site/docs/` is `lane/docs`' active territory (mid `developer→contributor` rename)
  and a cross-lane write there would collide. **Flagged below for Daniel/lane/docs.**
- **I executed 3 safe in-lane archive moves** (fully-historical audits, zero inbound
  links) into the existing `docs/archive/`. Everything else stays put.

---

## Per-doc table

Legend — **Type:** P=principles/standard · D=design proposal · A=audit/findings · R=reference/nav · ADR=decision record.
**Impl:** done / partial / not-done / n-a (reference). **Action:** what I did or recommend.

### `docs/architecture/swiftui/`

| Doc | Type | Accuracy vs code | Impl status | Placement / action |
|---|---|---|---|---|
| `SWIFTUI_PRINCIPLES.md` | P | Accurate & current. §1–9 deliberately show legacy `ObservableObject`; the 2026 header section is the live rule (Observation-first, Golden Gate). **One stale line:** §"macOS 26 only / no `if #available`" is contradicted by the cross-platform direction (reform_masterplan §4 + open #2096) — should read "macOS 26 + iOS floor". | n-a (living standard) | **KEEP.** Recommend **promote to public site** (`site/docs/contributor`) — durable, mandatory, agent+human. **FLAG (cross-lane).** Fix the macOS-only line when promoted. |
| `appkit_interop.md` | P (directive) | Accurate. The two-reason bridge rule + addenda match the ~8 sanctioned bridges in code and CLAUDE.md. | n-a | **KEEP** beside PRINCIPLES; promote together if PRINCIPLES goes public. |
| `development_standards.md` | P | Accurate; already self-corrects the "100% SwiftUI" line (2026-06-06 note). | n-a | **KEEP**; candidate for public site with PRINCIPLES. |
| `overview.md` | R | Accurate frontend map (2026-05-24). | n-a | **KEEP** (already mirrored as `site/docs/architecture/swiftui/overview.md`). |
| `key_files.md` | R | Navigation map; spot-accurate. | n-a | **KEEP** internal. |
| `api_client.md` | R | Accurate OpenAPI-generator description. | n-a | **KEEP** internal. |
| `workflow_checklist.md` | R/process | Mostly accurate; carries its own 2026-06-06 stale-process corrections. | n-a | **KEEP**; could fold its corrections inline (minor). |
| `kg_renderer_decision.md` | ADR | Decision record (Cytoscape.js in WebKit, #1354). Durable rationale. | done (decision stands) | **KEEP** — ADRs are durable. |
| `document_canvas.md` | D | Design/wireframe (2026-05-31, #1402/#1383/#1420), "approved". | partial (not separately verified this pass) | **KEEP** for now; re-confirm against the unified viewer when #1402 closes. |
| `observable_data_layer.md` | D (spec) | **Largely IMPLEMENTED** — `EntityStore.swift`, `ClaimStore.swift`, `LibraryChangeStream.swift`, backend `change_stream.py` + `emit_change` + `check_emit_change_coverage.py` guardrail + `test_changes_stream_endpoint.py` all exist. | **done** (#1863, #1851 CLOSED); residual ties to #1848 (open). | **KEEP** — now reads as the *reference for shipped architecture*, not a proposal. Worth a one-line "IMPLEMENTED" status header (deferred — not my lane to edit the doc body per read-only brief). |
| `reform_masterplan_2026-06.md` | D | **Live master plan.** Spot-checks hold: `_DEV_ROUTE_SPECS == []` confirmed (`api/main.py:1370`); `.inspector()` adopted in `ContentView`; #2031/#2032/#2033 done. Mind-palace retirement (§B) still pending (#1455 OPEN). | partial — keystone done, representations/annotation/iOS phases open. | **KEEP** — actively driving 4+ milestones. Do **not** archive. |
| `mac_shell_design_proposal.md` | D | Keystone (#2031) shipped; the doc itself says it's superseded-in-part by reform_masterplan ("mindPalace-as-lens now stale"). Still cited as the live design doc in `docs/ROADMAP.md:41`. | partial (superseded) | **KEEP + FLAG** — archiving needs ROADMAP edits (cross-lane w/ lane/review). Recommend lane/review fold its unique IA-banding (§3) into reform_masterplan, then archive. |
| `mac_assed_audit_2026.md` | A | Dated whole-app audit (2026-06-08). S1 fixed (#1877). Findings S2–S9 tracked under EPIC #1859 + #1840–1858. Self-labels "already tracked, don't duplicate". | partial; feeds OPEN #1859 | **KEEP** — still the reference for the open mac-assed sweep. Archive when #1859 closes. |
| `ios_appkit_audit.md` | A | Per-file AppKit/UIKit audit (#2101). Accurate bucket model; the working plan for the iOS port. | not-done (buckets A–D unstarted; #2101/#2096 OPEN) | **KEEP** — live reference for an unstarted epic. |

### `docs/architecture/api/`

| Doc | Type | Accuracy vs code | Impl status | Placement / action |
|---|---|---|---|---|
| `overview.md` | R | Accurate backend map. | n-a | **KEEP** (mirrored to site). |
| `key_files.md` | R | Accurate. | n-a | **KEEP** internal. |
| `development_standards.md` | P | Accurate backend standards. | n-a | **KEEP**; candidate for public site (pairs with frontend standards). |
| `workflow_checklist.md` | R/process | Accurate. | n-a | **KEEP** internal. |
| `extensibility_guarantee.md` | P (contract) | Backed by a contract test (#1652). Durable. | done | **KEEP** — durable guarantee; good public-site candidate. |
| `mcp_simple_interface.md` | R | Accurate (#1327, 10-tool surface). | n-a | **KEEP** internal. |
| `KG_ENDPOINTS.md` | R | Endpoint reference "generated 2026-05-12". Risk of drift; says dev-tier-only but `_DEV_ROUTE_SPECS == []` means everything is core now. | partial-stale | **KEEP**, but **note**: the "requires `FICHERO_FEATURE_TIER=dev`" preamble is stale (all routers promoted to core). Minor doc fix. |
| `capture_sessions_resumable_upload_contract.md` | D (contract) | Contract slice for #2352 (OPEN). | not-done (in-progress) | **KEEP** — active contract doc. |
| `notes_annotations_audit.md` | A | Completed-work log for #1759 (CLOSED). | **done** | **ARCHIVED →** `docs/archive/notes_annotations_audit_1759.md`. |

### Sibling top-level audits (`docs/architecture/`) — "anything similar"

| Doc | Type | Accuracy vs code | Impl status | Placement / action |
|---|---|---|---|---|
| `api_consistency_audit.md` | A | Point-in-time (2026-06-07). All its issues (#1412–#1417, #1710) now CLOSED; recommendations done. | **done** | **ARCHIVED →** `docs/archive/api_consistency_audit_2026-06-07.md`. |
| `search_audit.md` | A | Point-in-time (2026-06-07) live verification. Bounded fix landed; vision tracked #1824/#1833; concrete index data-debt → **filed #2709**. | partial (snapshot) | **ARCHIVED →** `docs/archive/search_audit_2026-06-07.md`. |

---

## Issues filed (unimplemented findings not already tracked)

| # | Title | Milestone | Source finding |
|---|---|---|---|
| **#2709** | [Search] Canonicalize entity/claim semantic indexes: one vector table + auto/rebuild trigger | Search | search_audit §3/§6/§7 — dual `kg_entities` vs `kg_entity_embeddings`, manual-only claim embeddings, no entity/claim rebuild endpoint. Verified still present in code 2026-06-27. The vision EPIC #1824 does not capture this concrete prerequisite. |

**No other issues filed** — every remaining audit/proposal finding maps to an existing
open issue:

- mac_assed_audit S2–S9 → EPIC **#1859** + #1840–1858 (S1 done via #1877).
- ios_appkit_audit buckets → **#2101** / **#2096**.
- reform_masterplan open phases → **#1455** (mind palace), representations/inspector
  milestones, **#2096** (iOS).
- observable_data_layer residual → **#1848** (action layer, partial).
- api_consistency_audit → all CLOSED (no action).
- search_audit vision → **#1824** / **#1833** (+ #2709 for the concrete debt).

> Filing-discipline note (per "verify-net-new before dispatch"): I cross-checked each
> finding against open issues/milestones *before* filing, to avoid duplicate noise.
> Only #2709 was genuinely uncovered.

---

## Moves executed (this lane, this commit)

Into the existing `docs/archive/` (precedent: `swiftui-inspector_redesign.md` already
lives there). All three are fully-historical, have **zero inbound links**, and are in
this lane's `docs/architecture/` territory:

```
docs/architecture/api_consistency_audit.md       → docs/archive/api_consistency_audit_2026-06-07.md
docs/architecture/search_audit.md                → docs/archive/search_audit_2026-06-07.md
docs/architecture/api/notes_annotations_audit.md → docs/archive/notes_annotations_audit_1759.md
```

Each got a one-line `> **ARCHIVED …**` provenance banner so future agents don't treat
its dated code line-refs as current.

**Did not touch `site/docs/`** → no `mkdocs build` needed.

---

## Flagged for Daniel (genuinely ambiguous / cross-lane — did NOT execute)

1. **Promote the durable principles/standards to the public site.**
   `SWIFTUI_PRINCIPLES.md`, `appkit_interop.md`, `development_standards.md` (both
   frontend + `api/development_standards.md`), and `extensibility_guarantee.md` are
   durable, mandatory, and equally useful to people. The brief says promote durable
   principles to `site/docs/contributor` — **but `lane/docs` owns `site/docs/**` and is
   mid `developer→contributor` rename.** Me writing there (new files + `mkdocs.yml` nav)
   would collide. **Recommend: lane/docs places these under `contributor/` as part of
   that rename** (they can `git mv` from `docs/architecture/swiftui/` or copy + leave a
   stub). Decide whether the public copy is the canonical one or a mirror.

2. **`mac_shell_design_proposal.md` consolidation.** Superseded-in-part by
   `reform_masterplan_2026-06.md`, but still cited as the live design doc in
   `docs/ROADMAP.md:41` + `node_model_fold_staging.md:85`. Archiving requires editing
   `ROADMAP.md` — likely **lane/review's** governance/structure territory. **Recommend:
   lane/review fold its still-unique IA-banding (§3) into reform_masterplan, repoint the
   ROADMAP link, then archive.** I left it in place to avoid a cross-lane ROADMAP edit.

3. **One canonical `docs/architecture/` vs site mirror.** Today `site/docs/architecture/`
   carries only 4 hand-picked `overview.md`/`release-process.md` mirrors; the real depth
   lives in internal `docs/architecture/`. That two-tree split is the root
   "docs-vs-site/docs" question — best answered by lane/docs + lane/review together, not
   piecemeal here.

---

## Overall recommendation on docs/ vs site/docs

**Keep the two-tier split, but make the dividing line by _document type_, not by accident:**

- **Public site (`site/docs/contributor`, agent+human):** durable principles, standards,
  contracts, and stable overviews — `SWIFTUI_PRINCIPLES`, `appkit_interop`, both
  `development_standards`, `extensibility_guarantee`, the `overview.md` pair. These don't
  go stale on a sprint cadence and benefit from being the single shared source.
- **Internal `docs/architecture/` (agent working area, unpublished):** live design
  proposals + working audits that churn with the milestones (`reform_masterplan`,
  `mac_shell_design_proposal`, `mac_assed_audit`, `ios_appkit_audit`,
  `capture_sessions…`, `observable_data_layer`, key_files/nav maps).
- **`docs/archive/` (historical):** dated, fully-superseded audits + completed-work logs.
  Three landed there this pass; `mac_assed_audit` and `mac_shell_design_proposal` follow
  once their epics/ROADMAP links resolve.

The promotion in (1) is the highest-value single change — but it's `lane/docs`' to make.
