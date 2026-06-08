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

### Next Session — Start Here
1. **ACTIVE LANE = reliability on Marshall import + profiling** (#72 IIIF Import Bulletproof, #1815 profiling). This is what makes Marshall→**GHG scale (60k docs / 800 folders)** viable. Stays on 0.0.2. Start: **run Apple Intelligence on Daniel's BOOK** (default-library Inbox doc "tubb2020shift - Preface") to verify the merged multi-provider fix populates output; then entity/claim dedup (#1811/#1805) + e5 prefixes (#1795).
2. **BUILDING LANE (0.0.3+, after import is reliable):** new direction filed today —
   - **Mac-assed app** EPIC #1838 (SwiftUI-first + sanctioned **AppKit fidelity bridges**; decision doc `docs/architecture/swiftui/appkit_interop.md`). First adoption = document inspector #1839. Children #1840-1843.
   - **Undo** front+back — extended on EPIC #1832 / #1831 (native UndoManager → backend undo stack).
   - **Multi-user / login / permissions** EPIC #1844 (DESIGN NEEDED; my default = engine-DB accounts + bearer tokens extending #742, role-based, library-scoped first — flag if Daniel disagrees).
   - **Apple platform** EPIC #1835 (App Intents/Spotlight #1837, Foundation Models 2026 #1836).
3. **Process:** dispatch **lean (ONE heavy lane at a time)**; **workers WRITE tests, only the manager RUNS them** (15GB RAM spike lesson; one engine on :8765). Codex workers were deferred to "after compress" — Daniel pivoted to giving the direction above instead.
4. Full roadmap = issues **#1774–#1844**. Handoff detail in memory: `session-handoff-2026-06-08-providers-and-search`.

---
(Older session logs archived to HISTORY.md)
