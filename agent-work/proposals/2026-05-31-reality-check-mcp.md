# Reality Check: MCP Milestone — Open Issues

**Date:** 2026-05-31
**Branch:** main
**Scope:** All open issues in the "MCP" GitHub milestone

---

## Summary Counts

| Classification | Count | Issue numbers |
|---|---|---|
| DONE — safe to close | 2 | #277, #270 (partial: notes + CLI parity still open) |
| PARTIAL | 3 | #270, #1301, #509 |
| GENUINELY OPEN | 3 | #1269, #1327, #1338 |

**Revised safe-to-close list:** see below (conservative reading).

---

## Per-Issue Classification

### #509 — [Release Gate] 0.5.0 - Wire: MCP Servers
**PARTIAL**

Evidence:
- `fichero/fichero/Views/MCPServers/` exists with `MCPServersSheet.swift`, `MCPServersView.swift`, `MCPToolsCatalogView.swift`, `MCPServerDetailView.swift`, `AddMCPServerSheet.swift` — full Swift UI surface built.
- `fichero/fichero/Services/MCPService.swift` — full Swift service: list/get/create/update/delete servers, loadServerTools, getAllTools, loadToolsIntoWorkflowRegistry.
- `fichero/fichero/FicheroApp.swift:238` — "MCP Servers..." button exists in the app menu, gated behind `featureManager.isMCPEnabled`.
- `fichero/fichero/App/LibraryWindow.swift:81` — sheet wired.
- Backend routes `mcp_servers.py` (19 symbols) and `mcp_tools.py` (22 symbols) both exist and are registered in `api/main.py`.
- **Gap:** Issue is a release-gate for 0.5.0 which is far future. It has `status:ready-for-test` label but MCP is still feature-gated OFF by default. Daniel has not checked the test checklist.

Action: PARTIAL — UI and backend both exist. Gate is `isMCPEnabled` (default OFF). Human QA checklist must be signed off before close.

---

### #277 — Re-enable MCP menu entry after 0.0.1 hardening
**DONE — safe to close**

Evidence:
- `fichero/fichero/FicheroApp.swift:237-241` — `if featureManager.isMCPEnabled { Button("MCP Servers...") { appState.showMCPServers = true } }` is present and wired.
- `fichero/fichero/Models/FeatureManager.swift:118` — `var isMCPEnabled: Bool { allFeaturesEnabled || mcpEnabledInternal }` exists.
- The MCP menu entry is gated properly and functional when feature is enabled.

Action: CLOSE. The re-enabling logic is fully implemented and properly gated. This issue's acceptance criteria are met.

---

### #270 — Extend Fichero MCP server with semantic note, workspace, and spatial tools
**PARTIAL**

Evidence:
- `mcp_server.py` exports: `fichero_mp_create_note`, `fichero_mp_list_notes`, `fichero_mp_get_note`, `fichero_mp_update_note`, `fichero_mp_delete_note` (all five CRUD ops for Mind Palace notes) — DONE.
- `mcp_server.py` exports: `fichero_mp_list_rooms`, `fichero_mp_get_room`, `fichero_mp_create_room`, `fichero_mp_scene_summary`, `fichero_mp_list_nodes`, `fichero_mp_get_node`, `fichero_mp_place_node`, `fichero_mp_move_node`, `fichero_mp_remove_node`, `fichero_mp_list_connections`, `fichero_mp_create_connection`, `fichero_mp_remove_connection`, `fichero_mp_list_stacks`, `fichero_mp_get_stack`, `fichero_mp_create_stack`, `fichero_mp_add_to_stack`, `fichero_mp_remove_from_stack`, `fichero_mp_get_viewport`, `fichero_mp_save_viewport`, `fichero_mp_focus`, `fichero_mp_suggest_arrangement` — comprehensive spatial tools DONE.
- **Gap per issue checklist:** "compact scene summaries, viewport summaries, and delta responses" — `fichero_mp_scene_summary` exists, but delta responses / compact viewport summaries are not a named function. Likely implemented partially.
- **Gap:** "explicit on-demand capture hooks" — not found in mcp_server.py (no `capture` tool).
- **Gap:** Typer CLI parity (`fichero mind-palace ...` subcommands) — no mind-palace subcommand found in `__main__.py` or CLI commands folder.

Action: PARTIAL — core spatial + note tools done. Missing: on-demand capture hooks, delta responses, CLI parity. Issue #1301 also tracks the CLI parity gap.

---

### #1301 — MCP server follow-ups: notes tools, typed returns, CLI parity, tier (#1269)
**PARTIAL**

Evidence per checklist:
- **Native notes MCP tools** — `fichero_mp_create/list/get/update/delete_note` all in `mcp_server.py` — DONE.
- **Typed returns** — `mcp_server.py::fichero_mp_create_note` returns `NativeNote` (not `Any`); `fichero_mp_list_notes` returns `list[NativeNote]`; `fichero_mp_get_note` returns `NativeNote`; `fichero_mp_update_note` returns `NativeNote` — these are typed. However, room-level tools (`fichero_mp_list_rooms`, etc.) still return `Any`. PARTIAL.
- **Typer CLI parity** — no `fichero mind-palace ...` subcommand found in `__main__.py`. OPEN.
- **Feature-tier** — `mind_palace.router` is registered directly in `api/main.py:865` without a `_DEV` comment. Test `test_release_tier_promotes_mind_palace_and_research_agents` exists confirming it's promoted. DONE.

Action: PARTIAL — notes tools typed and done; feature tier resolved; CLI parity and full typed returns on room/node tools still open.

---

### #1269 — MCP access to the app + agentic chatbot that drives & queries Fichero
**GENUINELY OPEN**

Evidence:
- The MCP server half is largely built (`mcp_server.py` with 49 symbols, full CRUD + KG + MP surface).
- **The agentic chatbot half is NOT built:** no agent loop, no bidirectional chat↔structured-result UI, no "drive the app from chat" functionality. The `research_agents.py` route file has 0 symbols. Chat views exist (`fichero/fichero/Views/Chat/`) but are standard chat, not MCP-tool-driven.
- Issue explicitly says "This is an epic; expect to decompose into (a) MCP server, (b) chatbot agent loop, (c) bidirectional chat↔structured-result UI." Only (a) is built.

Action: OPEN — the MCP server portion is ~80% done, but the agentic chatbot / bidirectional UI has not been built.

---

### #1327 — Simplified MCP interface for outside agents
**GENUINELY OPEN**

Evidence:
- `mcp_server.py` has ~49 tools — far more than the "6-10 tools max" the issue specifies.
- No minimal/simplified tier exists. No separate entry point or config flag for a "simplified" surface.
- No documentation of schemas or example agent calls found.
- The full MCP server is built but this issue explicitly asks for a *minimal, stable, documented* surface for outside agents — a curation + docs task that hasn't happened.

Action: OPEN — the underlying tools exist but the simplification, schema docs, and example calls are not done.

---

### #1338 — Full-featured MCP: complete Fichero tool surface for outside + Researcher agents (vision-multimodal hook)
**GENUINELY OPEN**

Evidence:
- The issue specifically calls for: (1) `mcp_full.py` (or full-tier extension) — **no `mcp_full.py` exists** in the codebase; `mcp_document_tools.py`, `mcp_kg_tools.py`, `mcp_research_tools.py` each have 1 symbol (stub files).
- Vision-multimodal hook (render scene to PNG/MP4, expose as MCP resource) — no `mindpalace_render` MCP resource found; `mindpalace_render.router` registered in `api/main.py` is a backend route, not an MCP tool resource.
- Integration tests with a sample agent driving a library — not found.
- The full workflow execution + monitoring, artifact access, vision tools are absent from `mcp_server.py`'s tool list.

Action: OPEN — `mcp_full.py` does not exist. Vision-multimodal hook, agent integration tests, and the full CRUD surface for outside agents are not built.

---

## Safe to Close Now

| # | Issue | Reason |
|---|---|---|
| #277 | Re-enable MCP menu entry | Button, gate, and sheet are fully wired. Acceptance criteria met. |

## Needs Work (do not close)

| # | Issue | Key gap |
|---|---|---|
| #509 | Release Gate 0.5.0 Wire: MCP Servers | Human QA checklist not signed off; feature still dev-gated |
| #270 | Extend MCP with spatial + note tools | On-demand capture hooks + CLI parity missing |
| #1301 | MCP follow-ups: notes/typed/CLI/tier | CLI parity + partial typed returns on room/node tools |
| #1269 | MCP + agentic chatbot | Chatbot agent loop + bidirectional UI not built |
| #1327 | Simplified MCP for outside agents | No minimal tier, no schema docs, no example calls |
| #1338 | Full MCP + vision-multimodal hook | `mcp_full.py` does not exist; vision hook not built |
