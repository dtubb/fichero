# Milestone Audit: Researcher — 2026-05-30

**Auditor:** Claude agent (read-only; no GitHub state has been modified)
**Milestone:** Researcher (#53) — "Agentic research surface — AI-controlled browser, project tracking, autonomous workflow agents (configure, assign task, run loop, inspect decisions), RAG/graph-RAG chat agent."
**Total issues in milestone:** 4 (2 open, 2 closed)
**Issues outside milestone that belong here or are adjacent:** 5 flagged

---

## Summary Counts

| Category | Count |
|---|---|
| Keep as-is (closed, correct) | 1 |
| Keep open — correct milestone, label fixes only | 2 |
| Close not-planned (wrong milestone scope) | 1 |
| Add to Researcher milestone (currently unmilestoned) | 2 |
| Boundary call — leave in Chat milestone (NOT Researcher) | 1 (note only) |
| Label drift fixes | 4 issues need labels |

---

## Section 1 — Issues Currently IN Researcher Milestone

### #1256 — Researcher agent: autonomous multilingual archival research for any term (LangGraph + pi agent)
- **State:** CLOSED / COMPLETED
- **Labels:** `backend`, `type:feature`
- **Milestone correctness:** CORRECT — core Researcher capability (autonomous archival research agent)
- **Premature-close check:** Closed 2026-05-27, one day after creation. Very fast — but the body says "Generalize what maps_southern_colombia does… Backend: a LangGraph workflow… Needs design." This was filed as a design-plus-implementation epic on 2026-05-26 and closed COMPLETED next day. Given #1256 was likely the seed/parent for #1335 ("Researcher: next-phase agentic capabilities (parent)" filed later), and the work it describes is substantial (multilingual, multi-archive, evaluates sources, assembles findings), the close is likely premature OR it was superseded by #1335. However the HIGH BAR rule (bulk-sweep without review AND specific actionable detail not in open backlog) applies — #1335 is open in the backlog covering this space. **Leave closed.**
- **Label fixes needed:**
  - Missing `type:feature` ✓ (already has it)
  - Missing `priority:` → add `priority:P1`
  - Missing `tier:` → add `tier:frontier` (pi agent / opus-level)
  - Missing `needs-design` → add (body explicitly says "Needs design — see the planner proposal")

**Action:** label-only edit

---

### #514 — [Release Gate] 0.7.1 - Wire: Research Agents
- **State:** OPEN
- **Labels:** `status:ready-for-test`, `roadmap`
- **Milestone correctness:** CORRECT — release gate for Research Agents in the Researcher milestone
- **Label drift:**
  - `status:ready-for-test` is suspect for a far-future release gate (0.7.1) — this is a Daniel QA checklist issue, not something merged and awaiting test now. `roadmap` is appropriate.
  - Missing `type:` label — add `type:task` (it's a gate/checklist issue)
  - Missing `priority:` — add `priority:P3` (far-future roadmap)
  - Missing `needs:human` — this is explicitly a human QA checklist; add it
  - `status:ready-for-test` should be removed unless 0.7.1 is actually merged (it is not — far future)

**Action:** label edit

---

### #513 — [Release Gate] 0.7.0 - Wire: Agents
- **State:** OPEN
- **Labels:** `status:ready-for-test`, `roadmap`
- **Milestone correctness:** CORRECT — release gate for autonomous workflow agents, core Researcher scope
- **Label drift:** Same issues as #514:
  - Missing `type:task`
  - Missing `priority:P3`
  - Missing `needs:human`
  - `status:ready-for-test` is incorrect for a far-future gate; remove it

**Action:** label edit

---

### #426 — 0.1.0 — Human-in-the-Loop Orchestration Policy for Agent Writes
- **State:** CLOSED / COMPLETED
- **Labels:** `type:task`
- **Milestone correctness:** QUESTIONABLE — the issue body says "area:backend-api, area:orchestration" and is scoped to policy engine/approval workflow for AI agent writes. The "orchestration policy" is shared infrastructure used by agents generally (Workflows milestone territory) more than the Researcher-specific agentic surface. However, because the Researcher milestone explicitly includes "autonomous workflow agents (configure, assign task, run loop, inspect decisions)" and human-in-the-loop is integral to that, retaining in Researcher is defensible.

  Larger problem: **this issue is titled "0.1.0"** — that release version is long past. The issue was closed 2026-04-11, created 2026-04-10. It was filed at a time when Researcher was being planned and the policy work was a prerequisite. Keeping it closed/Researcher is fine — the work is done.

- **Premature-close check:** Closed day after creation (April 10 → 11). Same pattern as #1256. Body has concrete acceptance criteria with `/api/policies/orchestration`, `/api/agents/write/approve`, `/api/agents/write/audit`. Given no open issue covers these exact endpoints and the close is from April (not a bulk sweep), **leave closed.**

- **Label fixes:**
  - Missing `priority:` — add `priority:P2` (was infrastructure prerequisite)
  - Missing `backend` label — add it (all work is backend API)
  - `type:task` ✓ already correct

**Action:** label edit only

---

## Section 2 — Issues Outside Researcher That Should Be Added

### #1335 — Researcher: next-phase agentic capabilities (parent)
- **State:** OPEN
- **Milestone:** none (unmilestoned)
- **Labels:** none
- **Body:** "Parent issue for the next round of Researcher work. The existing browser+tasks+chat workspace exists (#A1–A10 done); next phase: agentic actions (browse → save → annotate → file under workspace), citation discovery, source verification, summarisation."
- **Assessment:** This is explicitly the Researcher milestone's next-phase parent. It has no milestone. **Add to Researcher.**
- **Label fixes needed:** Add `type:task`, `priority:P1`, `tier:frontier`, `needs-design`

**Action:** add to Researcher milestone + label edit

---

### #1157 — Research agents: project tracking + AI-controlled browser for source discovery
- **State:** OPEN
- **Milestone:** none (unmilestoned)
- **Labels:** `roadmap`, `needs-design`, `backend`
- **Body:** Full spec for research agent project tracking (milestones, tasks, steps, search terms, languages, archives) and AI-controlled in-app browser. References `~/code/maps_southern_colombia` as reference impl — same as #1256. This is the canonical Researcher scope per the milestone description ("AI-controlled browser, project tracking").
- **Assessment:** Perfect fit for Researcher milestone. Currently unmilestoned despite being a core Researcher deliverable. **Add to Researcher.**
- **Label fixes needed:** Add `type:feature`, `priority:P1`

**Action:** add to Researcher milestone + label edit

---

## Section 3 — Boundary Calls (Leave in Current Milestone)

### #1156 — Interactive RAG / graph-RAG chat agent
- **State:** OPEN
- **Milestone:** none (unmilestoned)
- **Labels:** `roadmap`, `needs-design`, `client:swiftui`
- **Assessment:** User chats with an AI agent doing RAG + graph-RAG over their **own library**. Per the audit instructions, "a graph-RAG feature in the CHAT window → milestone 'Chat', NOT Researcher." This is a library-chat feature, not autonomous external research. **Do NOT add to Researcher.** Add to Chat milestone (#22) instead.
- **Note for manager:** This issue has no milestone and belongs in Chat, not Researcher. Label it `type:feature`, `priority:P1`.

**Action (for manager to execute for Chat milestone):** move to Chat milestone (#22) + add `type:feature`, `priority:P1` labels

---

### #1153 — Roadmap: Fichero research-platform vision (RAG agent, research agents+browser, RealityKit mind palace, KG browse, VisionPro/iPad, editing tools)
- **State:** OPEN
- **Milestone:** none
- **Labels:** `needs-design`
- **Assessment:** A parent roadmap epic spanning many milestones (Mind Palace, Researcher, Chat, Image Editing, etc.). Too broad to assign to any single milestone. Leave unmilestoned as an umbrella roadmap issue. Add `roadmap`, `type:task`.

**Action:** label-only (`roadmap`, `type:task`) — no milestone assignment

---

## Section 4 — Out-of-Scope Issues Noted (No Action Needed)

- **#1338** (MCP milestone, CLOSED): "Full-featured MCP… Researcher agents" — correctly in MCP; the Researcher reference is a consumer note, not scope assignment.
- **#1269** (MCP milestone, OPEN): "MCP access to the app + agentic chatbot" — the chatbot described here drives Fichero via MCP tools; correctly in MCP.
- **#1103** (no milestone, CLOSED): "References as first-class entities… researcher-agent dispatch" — researcher-agent dispatch is one sub-feature of a broader References system; correctly not in Researcher milestone.
- **#426** closed work already audited above.

---

## Verbatim `gh issue edit` / `gh issue close` Checklist

Manager: execute each command block in order. All are idempotent.

---

### A. Label fixes on existing Researcher issues

```bash
# #1256 — add priority:P1, tier:frontier, needs-design
gh issue edit 1256 --repo dtubb/fichero \
  --add-label "priority:P1,tier:frontier,needs-design"

# #514 — remove status:ready-for-test, add type:task, priority:P3, needs:human
gh issue edit 514 --repo dtubb/fichero \
  --remove-label "status:ready-for-test" \
  --add-label "type:task,priority:P3,needs:human"

# #513 — remove status:ready-for-test, add type:task, priority:P3, needs:human
gh issue edit 513 --repo dtubb/fichero \
  --remove-label "status:ready-for-test" \
  --add-label "type:task,priority:P3,needs:human"

# #426 — add priority:P2, backend
gh issue edit 426 --repo dtubb/fichero \
  --add-label "priority:P2,backend"
```

---

### B. Add unmilestoned issues to Researcher + fix their labels

```bash
# #1335 — add to Researcher milestone + add labels
gh issue edit 1335 --repo dtubb/fichero \
  --milestone "Researcher" \
  --add-label "type:task,priority:P1,tier:frontier,needs-design"

# #1157 — add to Researcher milestone + add labels
gh issue edit 1157 --repo dtubb/fichero \
  --milestone "Researcher" \
  --add-label "type:feature,priority:P1"
```

---

### C. Boundary issue: #1156 belongs in Chat, not Researcher

```bash
# #1156 — move to Chat milestone + add labels
gh issue edit 1156 --repo dtubb/fichero \
  --milestone "Chat" \
  --add-label "type:feature,priority:P1"
```

---

### D. Roadmap parent: #1153 — labels only, no milestone

```bash
# #1153 — add roadmap + type:task labels (no milestone assignment)
gh issue edit 1153 --repo dtubb/fichero \
  --add-label "roadmap,type:task"
```

---

## Post-execution Researcher milestone state

After executing the above, Researcher (#53) will contain:

| # | Title | State | Labels |
|---|---|---|---|
| 1256 | Researcher agent: autonomous multilingual archival research | CLOSED/COMPLETED | `backend`, `type:feature`, `priority:P1`, `tier:frontier`, `needs-design` |
| 514 | [Release Gate] 0.7.1 - Wire: Research Agents | OPEN | `roadmap`, `type:task`, `priority:P3`, `needs:human` |
| 513 | [Release Gate] 0.7.0 - Wire: Agents | OPEN | `roadmap`, `type:task`, `priority:P3`, `needs:human` |
| 426 | 0.1.0 — Human-in-the-Loop Orchestration Policy for Agent Writes | CLOSED/COMPLETED | `type:task`, `priority:P2`, `backend` |
| 1335 | Researcher: next-phase agentic capabilities (parent) | OPEN | `type:task`, `priority:P1`, `tier:frontier`, `needs-design` |
| 1157 | Research agents: project tracking + AI-controlled browser | OPEN | `roadmap`, `needs-design`, `backend`, `type:feature`, `priority:P1` |

**Total after:** 6 issues (3 open, 3 closed)

---

## Tricky Cases

1. **#1256 fast-close**: Filed and closed in 24 hours as COMPLETED for a large LangGraph multi-archive multilingual agent. Most likely this was the seed issue that spawned #1335 (the explicit next-phase parent). Leave closed — #1335 carries the open work forward. No premature-close recovery warranted.

2. **#426 "0.1.0" title in Researcher**: The 0.1.0 version prefix is stale (Fichero is on 0.0.x). The human-in-the-loop approval policy is genuinely cross-cutting (Workflows could claim it too), but Researcher explicitly needs it for agentic write safety. Keeping it in Researcher is defensible; moving to Workflows is also defensible. Left as-is.

3. **#1157 vs #1256 overlap**: Both cover the autonomous archival research agent. #1157 is a detailed spec (AI-controlled browser, project tracking, archival adapters, approval flow); #1256 is the original request. They are not duplicates — #1256 is the problem statement, #1157 is the implementation spec. Both belong in Researcher.

4. **#1269 / #1338 (MCP milestone)**: Both mention Researcher as a consumer of MCP tools. Correct assignment — MCP tools are infrastructure; the Researcher milestone owns the agentic surface that uses them.
