# Milestone Audit: Chat — 2026-05-30

**Auditor:** agent (claude-sonnet-4-6)  
**Milestone:** Chat (#22)  
**Milestone description:** "Document-scoped chat (select doc → send message → response), conversation history, multi-model side-by-side comparison, extract text from chat, ComparisonDetailView."  
**Audit scope:** all issues currently in the Chat milestone + related orphan issues surfaced during audit.

---

## Summary

| Category | Count |
|---|---|
| Issues audited (in milestone) | 6 (2 closed, 4 open) |
| Keep as-is (closed) | 1 (#1262) |
| Reopen — premature close | 1 (#1268) |
| Keep open, label fixes | 4 (#244, #245, #246, #247) |
| Out-of-milestone issues to add to Chat | 2 (#486, #487) |
| Out-of-milestone issues — no change needed | 3 (#734, #1156, #740) |
| **Label drift fixes (open issues)** | **all 4 open issues** |

**Tricky case:** #1268 was closed as COMPLETED on 2026-05-27 but its own closing comment explicitly states "Frontend comparison UI is the remaining piece." The Chat milestone description calls out `ComparisonDetailView` as in-scope. No open issue tracks that remaining work. This is a clear premature close.

**Boundary note:** #1156 (Interactive RAG / graph-RAG chat agent) is borderline Chat vs Researcher. Its body describes in-chat KG retrieval (not autonomous browsing), which maps to the Chat milestone's "graph-RAG chat in the chat window" scope — but it's labeled `roadmap` + `needs-design` with no milestone assigned. Recommend leaving unmilestoned (roadmap-parked) until design is ready, then assigning to Chat. Not actioned here.

---

## Action Checklist

### 1. REOPEN — Premature close

```bash
gh issue reopen 1268 --repo dtubb/fichero --comment "Reopening: closed as COMPLETED on 2026-05-27 but the closing comment explicitly notes 'Frontend comparison UI is the remaining piece.' The Chat milestone description lists ComparisonDetailView as in-scope and no open issue tracks the abstract comparison panel or per-node 'Compare models...' affordance in the node editor. Backend work (reusing #1262 routes) is merged; this issue should stay open until the frontend work ships."
```

**Rationale:** #1268's own closing comment acknowledges unfinished frontend work (abstract comparison panel + per-node model comparison in the node editor). The Chat milestone description explicitly lists `ComparisonDetailView`. No open issue exists for this remaining work. High-bar premature-close criterion is met: specific actionable scope is identified, not present in open backlog.

---

### 2. LABEL FIXES — Open issues in Chat milestone

#### #244 — Promote Chat from off to beta
Missing: `priority:`, `client:swiftui`, `tier:`  
Has: `type:feature`, `backend`

```bash
gh issue edit 244 --repo dtubb/fichero --add-label "priority:P1,client:swiftui,tier:frontier"
```

**Rationale:** Promoting Chat to beta requires both backend enablement and SwiftUI surface; P1 (required for milestone completion, not blocking other features); tier:frontier because it gates LLM-backed chat going live.

#### #245 — Gate Chat cleanly when off
Missing: `priority:`, `client:swiftui`, `tier:`  
Has: `type:bug`, `backend`  
Note: `type:bug` is correct — this is about preventing visible/broken state when the feature flag is off.

```bash
gh issue edit 245 --repo dtubb/fichero --add-label "priority:P1,client:swiftui,tier:mini"
```

**Rationale:** Feature-flag gating affects both backend routes and SwiftUI visibility. P1: must ship before beta to avoid broken UX. tier:mini — purely structural, no LLM inference needed.

#### #246 — Add Chat stability and QA coverage
Missing: `type:`, `priority:`, `tier:`  
Has: `status:ready-for-test`, `backend`

```bash
gh issue edit 246 --repo dtubb/fichero --add-label "type:task,priority:P1,tier:frontier"
```

**Rationale:** QA gate for Chat beta; `type:task` (test/stability work); P1 (must pass before beta); tier:frontier (covers LLM chat path end-to-end).

#### #247 — Promote Chat to release if ready
Missing: `priority:`, `client:swiftui`, `tier:`  
Has: `type:feature`, `backend`

```bash
gh issue edit 247 --repo dtubb/fichero --add-label "priority:P2,client:swiftui,tier:frontier"
```

**Rationale:** Release promotion follows beta; P2 (depends on beta work being done first); needs SwiftUI surface label alongside backend.

---

### 3. ADD TO CHAT MILESTONE — Orphan release-gate issues

#### #486 — [Release Gate] 0.0.8 — Wire: Chat v1
Currently: no milestone, labeled `status:ready-for-test` + `roadmap`  
Action: add to Chat milestone

```bash
gh issue edit 486 --repo dtubb/fichero --milestone "Chat"
```

**Rationale:** This is the acceptance checklist and QA gate for Chat v1 (document-scoped chat, conversation persistence). It belongs in the Chat milestone alongside #246 (QA coverage) and #247 (promote to release). The `status:ready-for-test` label confirms it is waiting on human verification of Chat v1 work. No version-specific milestone exists for 0.0.8.

#### #487 — [Release Gate] 0.0.9 — Wire: Chat v2 (Model Comparison)
Currently: no milestone, labeled `status:ready-for-test` + `roadmap`  
Action: add to Chat milestone

```bash
gh issue edit 487 --repo dtubb/fichero --milestone "Chat"
```

**Rationale:** This is the acceptance checklist and QA gate for Chat v2 (multi-model comparison, conversation history search, extract text from chat). Directly covers Chat milestone scope. No version-specific milestone exists for 0.0.9.

---

## Issues Reviewed — No Action

| # | Title | Decision | Reason |
|---|---|---|---|
| #1262 | Re-enable + wire to KG: chat-with-sources, model comparison, GraphRAG chat | Keep closed COMPLETED | Two substantive owner comments confirm merged to 0.0.2 with build gate. Backend work complete; correct milestone. Missing labels on a closed issue — not worth reopening. |
| #734 | Surface ModelComparisonService — 'Compare models' workflow run UI | Keep in Search milestone | Covers workflow-run comparison UI (not the chat comparison panel). Correctly in Search milestone. Overlaps with #1268's remaining frontend work only tangentially. |
| #1156 | Interactive RAG / graph-RAG chat agent | Leave unmilestoned | Labeled roadmap + needs-design. Borders Chat/Researcher boundary (in-chat KG retrieval vs agentic). Leave parked until designed; assign to Chat at that point. |
| #740 | GraphRAG (parked): evaluate nano-graphrag at corpus scale | Leave unmilestoned | Labeled roadmap. Infrastructure/evaluation research, not a Chat UI feature. Correct to stay unassigned. |

---

## Label Drift Notes (Closed Issues)

| # | Issue | Label Gap | Recommendation |
|---|---|---|---|
| #1262 | Re-enable + wire to KG | Missing `client:swiftui`, `priority:` | Low priority — closed. Not actioned. |
| #1268 | Model-comparison interface | No labels at all | Will be addressed when reopened (see action 1). Add `type:feature`, `backend`, `client:swiftui`, `priority:P1` after reopening. |

**Suggested labels to add after reopening #1268:**
```bash
gh issue edit 1268 --repo dtubb/fichero --add-label "type:feature,backend,client:swiftui,priority:P1"
```

---

## No Illegal/Legacy Labels Found

All labels on Chat milestone issues belong to the canonical 23-label set. No `owner:*`, `agent:*`, or legacy labels detected.
