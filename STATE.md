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
1. **Run Apple Intelligence on Daniel's BOOK** (default-library Inbox doc "tubb2020shift - Preface") on the Marshall background — verify Apple now produces populated output (fix just merged).
2. **Daniel will request parallel codex workers** after a context compress. Dispatch **lean (ONE heavy lane at a time)**; **workers WRITE tests, only the manager RUNS them** (RAM — 15GB spike happened today; one engine on :8765).
3. Priority dispatches: entity dedup #1811 + claim dedup #1805 (import quality); e5 prefixes #1795 (quick search win); central LLM consolidation #1825 + Apple ChatModel #1826.
4. Full roadmap = issues **#1774–#1834** (all filed today). Handoff detail in memory: `session-handoff-2026-06-08-providers-and-search`.

---
(Older session logs archived to HISTORY.md)
