# STATE.md — Fichero

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
