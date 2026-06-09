# STATE.md — Fichero

## 2026-06-08 (overnight) — autonomous Mac-assed run (Claude in charge)

**Mode:** Daniel out for the night; I run the loop — dispatch worker batches (claude=frontend, codex-style=backend), build/test-verify each, integrate, dispatch next. Workers in their own worktrees; I build via Xcode MCP + run heavy pytest (one heavy backend lane at a time).

**Landed tonight (each manager-verified — build/test/lint green — pushed to 0.0.2):**
- `071c9042` inspector tabs → native List + two-step attributes; `3c77cb9f` single-click-select/double-click-open + 2 review HIGHs
- `8bde477c` backend `list_entities` doc-scoped hot path 316→45ms (~7×, `query_in` parameterized IN)
- `5e5b708a` EntityDetailView modernize (native List, no emoji, hide raw hash, Liquid Glass, split) + in-place rename
- `1d3ac1ee` URLSession/print cleanup (DocumentPicker OSLog; LocalModels/WorkspaceItem already migrated)
- `f9e7a85a` entity dedup #1811 — accent-fold + normalized-key short-circuit (Pena/Peña, San Pablo/San Pabloo)
- Decisions in `appkit_interop.md`: List-vs-Table, no swipe, edit-via-navigation; `SWIFTUI_PRINCIPLES.md`: Observation-first + data-layer; audit doc `mac_assed_audit_2026.md`.
- **Closed:** #1811 #1849 #1853 #1860 #1864 #1865 #1877 #1879 #1880. **Filed:** audit #1875 (+29: #1877–1905), guardrails #1876, features #1867–1874, over-merge #1907, +EPICs.

**Hard design rules (in `appkit_interop.md` / `SWIFTUI_PRINCIPLES.md`):**
- Inspector items = `List` (multi-select, hierarchy, drag-reorder); `Table` only for the multi-column library browser. AppKit NSOutlineView only if List can't reach.
- **No swipe actions** (not Mac) → context menu + toolbar + keyboard.
- **Editing is navigation, not modal** — inline rename / push-detail-with-Back, never sheets.
- Single-click select, double-click open everywhere.
- Existing view-local `ObservableObject` → `@Observable` IS in scope; god-objects staged.
- Golden Gate only; no `if #available`.

**Workers running now:** frontend `ae40061f` (remove non-Mac `.swipeActions` from inspector lists #1885 + finish raw-URLSession #1893/#1891/#1902, verify-first); backend `a3e67f30` (embedding over-merge precision gate #1907). On completion: manager build/test-verifies → integrates → dispatches next. **Note:** jcodemunch index is stale — workers must verify-by-reading-disk (caught a false-positive on #1877/#1879).

**Next queued:** finish per-view Mac-assed fixes (#1882-1900); the foundational **observable data-layer** (migrate ~12 `@StateObject service` views to injected `@Observable` stores + backend change-stream #1863 — needs a design pass, it's the keystone); e5 prefixes #1795 (note: needs re-embed consistency); undo #1832; citations tab #1850; feature set #1867-1874.

**Source-of-truth EPICs:** #1859 (Mac-assed/2026 audit S1–S9), #1838 (Mac-assed), #1851 (observers-everywhere), #1863 (backend change-stream, multi-window), #1832 (undo). Audit doc: `docs/architecture/swiftui/mac_assed_audit_2026.md`.

**Next batches queued:** S1 local-path fixes (#1860/#1861), S2 NotificationCenter→@Observable (#1862), S3 @Observable migrations, citations tab (#1850), No-Selection chrome (#1854), horizontal layout (#1856), observers wiring (#1851/#1857), then undo (#1832).

---

## 2026-06-08 (PM) — Demo + multi-provider extraction session

**Branch:** `0.0.2` at `c29fa52f`, pushed.

### This Week's Focus
Marshall import QUALITY + multi-provider extraction + search/embedding quality. Demo to Andy **landed** today on the 20-page English `Marshall20Entities` library.

### Just Landed
- **Multi-provider extraction FIXED + merged** (`c29fa52f`, full unit suite green 3921 passed): OpenAI (function_calling, recommended default), OpenRouter (httpx hook strips `parallel_tool_calls`/`disable_parallel_tool_use` → both OpenAI + Bedrock-Claude routes), Apple (`include_schema_in_prompt` — no more empty `{}`). Closed #1802/#1821/#1822/#1823.
- Earlier today: `f607c7d6` extraction schema fixes (verb/object optional, strict=False, thin-kept), `#1799` fail-fast, demo UI fixes (tab order, sidebar, Delete, blank-image, timeline+map, entity-detail mentions).

### Blocked / Watch
- Search results unimpressive → e5 prefixes missing (#1795), whole-page embedding (#1833), no KG-fusion ranking (#1824).
- Entity dedup is the top visible KG-quality gap (#1811, Daniel raised 3×).

### Product target (decided 2026-06-08, post-WWDC26)
- **macOS 26 "Golden Gate" ONLY** (Apple-Silicon), no back-deployment. **Target release ≈ Sept 1, 2026.**
- **Adopt the 2026 Apple stack freely** as the Mac-assed foundation: SwiftUI 2026 (List/Grid/Section reordering, swipe-on-any-view, toolbar visibility-priority/auto-minimizing, AsyncImage caching, lazy `@State` Observable), "Use SwiftUI with AppKit" interop (NSHostingView+Observation+gestures) for the fidelity bridges, swift-collections (OrderedSet/Dict), Xcode 27 Instruments for profiling (#1815), Foundation Models 2026 + Core AI for on-device extraction (#1836). Decision: `docs/architecture/swiftui/appkit_interop.md` (2026 addendum). Memory: `golden-gate-only-target-sept-2026`.

### Operating model (changed 2026-06-08)
- **Dated releases, no versions.** No 0.0.3, no per-version branch/worktree, no two-ahead gate. Work the current branch; cut a dated release when ready.
- **One milestone at a time:** groom it (issues all there + complete) → work to done → next. Features are NOT release-gated; the active lane is whatever milestone is in focus.
- **Lean execution:** ONE heavy lane at a time; **workers WRITE tests, only the manager RUNS them** (15GB RAM spike lesson; one engine on :8765).

### Next Session — Start Here
1. **First milestone in focus: Mac-assed / Window Chrome & Toolbars** (EPIC #1838, decision doc `docs/architecture/swiftui/appkit_interop.md`). Groom it, then start with the document-inspector fidelity pass (#1839) — which is also where the merge-action gets wired correctly.
2. **Cross-cutting enabler — one audited action layer** (EPIC filed today): every app capability = a typed backend action exposed once, called by UI buttons + chat agent (#1847) + App Intents (#1837) + UI-action tests, and **audit-logged (who/when/how)**. This answers the "how do we know a UI element works" + "who changed what" threads together.
3. **Live bug:** entity merge does nothing in the UI (filed today). Prime suspects: `additionalProperties` footgun in the Swift merge request, or list-not-refreshing post-merge. Two endpoints (`kg_entity_curation` live, `entities.py` dead dup) + two UI surfaces — collapse to one.
4. **Reliability thread still matters** for GHG scale (60k/800 folders): #72 import bulletproofing + #1815 profiling; run Apple on Daniel's book to confirm the merged multi-provider fix.
5. Roadmap issues **#1774–#1847**. Handoff memory: `session-handoff-2026-06-08-providers-and-search`.

---
(Older session logs archived to HISTORY.md)
