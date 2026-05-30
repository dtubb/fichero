# Milestone Audit — MCP
**Date:** 2026-05-30
**Scope:** All 7 issues in milestone "MCP" (4 open, 3 closed) + stray MCP-related issues elsewhere.

## Summary

| Action | Count |
|---|---|
| Keep as-is | 0 |
| Re-milestone (into MCP) | 2 |
| Re-milestone (out of MCP) | 1 |
| Reopen (closed-but-not-done) | 2 |
| Label fix (existing issues) | 7 |
| New milestone proposed | 0 |

**Reopen candidates:** #1301 (4 deferred items explicitly unchecked), #1327 (distinct from #1108, genuinely open work).

---

## Per-Issue Analysis

### Closed issues

---

**#1338** — Full-featured MCP: complete Fichero tool surface for outside + Researcher agents (includes vision-multimodal hook for spatial library)
- State: CLOSED / COMPLETED — no labels at all
- Assessment: Body describes vision-multimodal hook, `mcp_full.py` tier, integration tests. The **simplified** MCP (#1108, #1327) shipped; the **full** surface and vision hook are NOT tracked by any open issue. This is a large, genuinely unfinished idea closed in a bulk sweep.
- Action: **REOPEN** + label. The vision-multimodal scene-render hook ("model thinks about the catalogue visually") is a core piece of the MCP milestone scope and is not covered elsewhere.

---

**#1301** — MCP server follow-ups: notes tools, typed returns, CLI parity, tier (#1269)
- State: CLOSED / COMPLETED — no labels
- Assessment: Body lists 4 explicitly unchecked items (native notes MCP tools, typed returns, Typer CLI parity, feature-tier promotion). Closed as COMPLETED despite all checkboxes still open. Classic premature bulk-close.
- Action: **REOPEN** + label.

---

**#1108** — MCP server: expose the engine to MCP-aware agents (same client.py, same Pydantic models)
- State: CLOSED / COMPLETED — labels: `type:feature`, `priority:P1`
- Assessment: This one genuinely shipped (the initial mcp_server module). Correctly closed. Missing `mcp` surface label only.
- Action: **Label fix** only (add `mcp`).

---

### Open issues

---

**#1269** — MCP access to the app + agentic chatbot that drives & queries Fichero
- State: OPEN — no labels
- Assessment: This is the MCP epic (correct milestone). The body describes two coupled pieces: (1) MCP server (substantially shipped via #1108/#1301); (2) agentic chatbot with bidirectional chat↔structured-result UI. The chatbot piece is genuinely unstarted. The issue is correctly open and in the right milestone. Needs labels.
- Action: **Label fix** (add `type:feature`, `priority:P1`, `mcp`, `backend`, `client:swiftui`).

---

**#821** — Foundation toolkit: Tool protocol — let Apple Intelligence call back into the KG
- State: OPEN — labels: `backend`, `type:feature`
- Assessment: This is the Apple Foundation Models `Tool` protocol — a KG grounding hook for the fm-bridge, not an MCP server issue. It's a SwiftUI/fm-bridge concern (bidirectional IPC). The MCP milestone is about the outward-facing MCP server for external agents. This issue fits better in **Mind Palace** (where fm-bridge + spatial grounding live) or a dedicated Apple Intelligence milestone. It is currently mis-milestoned.
- Action: **Re-milestone to Mind Palace** + label fix (add `priority:P2`, `mcp` label is NOT appropriate here — remove from MCP milestone).

---

**#509** — [Release Gate] 0.5.0 - Wire: MCP Servers
- State: OPEN — labels: `status:ready-for-test`, `roadmap`
- Assessment: Correctly in MCP milestone as the QA gate. Has `status:ready-for-test` but no `type:` or `priority:` label. Release gates should be `type:task` + `needs:human` + `priority:P1`.
- Action: **Label fix** (add `type:task`, `priority:P1`, `needs:human`, `mcp`).

---

**#277** — Re-enable MCP menu entry after 0.0.1 hardening
- State: OPEN — labels: `type:task`, `client:swiftui`
- Assessment: Correctly scoped and milestoned. Missing `priority:` and `mcp` label. Low complexity — `priority:P3`.
- Action: **Label fix** (add `priority:P3`, `mcp`).

---

### Stray MCP-related issues (not in MCP milestone)

---

**#270** — Extend Fichero MCP server with semantic note, workspace, and spatial tools
- State: OPEN — milestone: Mind Palace — labels: `type:task`, `backend`, `type:feature`
- Assessment: Body describes extending `fichero.mcp_server` with notes CRUD, semantic spatial tools, scene summaries, capture hooks. This directly overlaps with the unclosed #1301 follow-ups (notes MCP tools) and #1338 (full tool surface). It belongs in the **MCP** milestone, not Mind Palace.
- Action: **Re-milestone to MCP** + add `mcp`, `priority:P2`.

---

**#1327** — Simplified MCP interface for outside agents
- State: CLOSED / COMPLETED — no milestone, no labels
- Assessment: "Distinct from #1301 follow-ups: small, stable, well-documented MCP tool surface for outside agents, 6-10 tools, typed inputs/outputs, example agent calls." This is distinct from #1108 (which was the initial engine-level wrapper) — #1327 is about the *documented public surface*. Body is short but the idea (schema docs + example agent calls) is NOT tracked by any open issue. Closed with no milestone, probably lost in a bulk sweep.
- Action: **REOPEN** + add to MCP milestone + add labels `type:feature`, `priority:P2`, `mcp`, `backend`. (If on review Daniel decides #1108 covered this sufficiently, close as duplicate of #1108.)

---

## Executable Commands

### REOPEN

```sh
# #1301 — 4 explicitly unchecked follow-up items (notes tools, typed returns, CLI parity, tier)
gh issue reopen 1301 --repo dtubb/fichero --comment "Reopening: all 4 deferred checklist items (notes MCP tools, typed returns, Typer CLI parity, feature-tier promotion) remain unchecked. Closed prematurely."

# #1338 — Full MCP surface + vision-multimodal hook not tracked anywhere else
gh issue reopen 1338 --repo dtubb/fichero --comment "Reopening: the full tool surface (mcp_full.py tier) and vision-multimodal scene-render hook are not covered by any open issue. The simplified MCP shipped; this full-surface work did not."

# #1327 — Documented outside-agent surface (schema docs + example calls) distinct from #1108
gh issue reopen 1327 --repo dtubb/fichero --comment "Reopening: the documented public schema surface (typed inputs/outputs + example agent calls) is distinct from the initial mcp_server module in #1108 and is not tracked elsewhere. If covered, close as duplicate of #1108."
```

### RE-MILESTONE (into MCP)

```sh
# #270 — MCP server extension: notes/workspace/spatial tools — belongs in MCP not Mind Palace
gh issue edit 270 --repo dtubb/fichero --milestone "MCP"
```

### RE-MILESTONE (out of MCP)

```sh
# #821 — Apple Foundation Models Tool protocol (fm-bridge/KG grounding) — belongs in Mind Palace
gh issue edit 821 --repo dtubb/fichero --milestone "Mind Palace"
```

### LABEL FIXES

```sh
# #1338 (after reopen) — add type/priority/mcp labels
gh issue edit 1338 --repo dtubb/fichero --add-label "type:feature,priority:P2,mcp,backend"

# #1301 (after reopen) — add type/priority/mcp labels
gh issue edit 1301 --repo dtubb/fichero --add-label "type:task,priority:P2,mcp,backend"

# #1327 (after reopen) — add milestone + type/priority/mcp labels
gh issue edit 1327 --repo dtubb/fichero --milestone "MCP" --add-label "type:feature,priority:P2,mcp,backend"

# #1269 — MCP epic: add all missing labels
gh issue edit 1269 --repo dtubb/fichero --add-label "type:feature,priority:P1,mcp,backend,client:swiftui"

# #1108 — add missing mcp surface label
gh issue edit 1108 --repo dtubb/fichero --add-label "mcp"

# #821 — add priority (after re-milestone to Mind Palace); mcp label NOT appropriate
gh issue edit 821 --repo dtubb/fichero --add-label "priority:P2"

# #509 — Release Gate: add type:task, priority:P1, needs:human, mcp
gh issue edit 509 --repo dtubb/fichero --add-label "type:task,priority:P1,needs:human,mcp"

# #277 — add priority:P3 and mcp
gh issue edit 277 --repo dtubb/fichero --add-label "priority:P3,mcp"

# #270 (after re-milestone to MCP) — add mcp label and priority
gh issue edit 270 --repo dtubb/fichero --add-label "mcp,priority:P2"
```

---

## Notes on Milestone Scope Coherence

The MCP milestone description says: "MCP server surface for outside agents (Claude, MCP clients): configure server from in-app, browse tool catalog, run tools. Full Fichero tool surface including vision-multimodal scene-render hook for qwenvl-style spatial agents."

Against that scope:
- **#821** (Apple Foundation Models Tool protocol) is an *inward* tool call from Apple Intelligence *into* the KG — it's not about the outward-facing MCP server for external agents. Wrong milestone.
- **#270** (extend MCP server with notes/spatial tools) is squarely within scope but wrongly filed in Mind Palace.
- **#1338** (vision-multimodal hook) is explicitly named in the milestone description and should be open.

No new milestone is proposed — all issues map cleanly to existing milestones.
