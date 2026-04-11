# GitHub Issues Created — Fichero Backend Tasks

## Summary

Created **21 new GitHub issues** for backend work across milestones 0.0.3 through 0.1.0.

## Created Issues

### 0.0.3 — Migration + Operational Hardening (4 issues)
- **#419**: Knowledge Migration / Backfill Tooling with Dry-Run + Rollback
- **#420**: Reindex / Repair Jobs and Metrics Recomputation Workers
- **#421**: Multilingual Baseline for Claims / Entities and Cross-Language Retrieval
- **#422**: Thin MCP Adapters for Canonical Knowledge APIs

### 0.0.4 — Semantic UX + Trust Workflow (9 issues)
- **#423**: Interpretations Workspace v1 Linked to Claims (original #375 backend)
- **#424**: Search Explanation and Metrics Visibility Panel (original #374 backend)
- **#425**: Activity Stream Enhancements
- **#435**: Claim Review Queue (Backend)
- **#436**: Contradiction Triage Backend (Evidence API)
- **#437**: Contradiction Triage Backend (Issue #373)
- **#438**: Search Explanation Backend (Issue #374)
- **#439**: Interpretations Workspace Backend (Issue #375)
- **#440**: Claim Review Queue Backend (Issue #372)

### 0.1.0 — Epistemic Platform Expansion (7 issues)
- **#426**: Human-in-the-Loop Orchestration Policy for Agent Writes
- **#427**: Advanced Graph Exploration and Interpretation Views
- **#428**: Optional Embedded IFFY / IIIF Server Mode
- **#429**: Optional Latent Inference Track (PyKEEN)
- **#430**: NetworkX Derived Graph Reasoning Integration
- **#431**: Advanced Graph / Interpretation Exploration

### Legacy Re-enable Issues (3 issues)
- **#432**: Re-enable Library / Search Split Layouts after 0.0.2
- **#433**: Re-enable Workflow Editor Icon / List / Table Modes after 0.0.2
- **#434**: Re-enable Search Icon / Table / Map Views after 0.0.2

## Labels Applied

All issues have:
- `area:backend-api` — Backend API work
- `type:task` — Implementation task
- Milestone assignment (0.0.3, 0.0.4, 0.0.5, or 0.1.0)

## Total Count

- **0.0.3:** 4 issues
- **0.0.4:** 9 issues
- **0.1.0:** 7 issues
- **Legacy:** 3 issues
- **Total:** 21 issues (all open)

**Backend-only work:** 17 issues ready for backend AI agents  
**Backend+Swift work:** 4 issues requiring both stacks

## How to Find Issues

### By Milestone
```bash
gh issue list --limit 100 --milestone "0.0.3"
gh issue list --limit 100 --milestone "0.0.4"
gh issue list --limit 100 --milestone "0.1.0"
```

### By Area (Backend)
```bash
gh issue list --label "area:backend-api"
```

### All Created Issues (Batch)
```bash
gh issue list --limit 100 | grep "^4[0-9][0-9]"
```

## AI Agent Claiming Strategy

### For AI Agents:

1. **Look at milestones by priority:** 0.0.3 → 0.0.4 → 0.1.0
2. **Filter by labels:** `area:backend-api`, `type:task`
3. **Claim issues as needed:**
   ```bash
   gh issue view <number>
   gh issue assign @your-ai-agent --add <number>
   ```

### Backend Work Available

**Backend-only (no Swift needed):**
- Migration/backfill tooling (#419)
- Reindex/repair workers (#420)
- Multilingual baseline (#421)
- Thin MCP adapters (#422)
- Activity stream enhancements (#425)
- NetworkX integration (#430)
- PyKEEN inference track (#429)
- IIIF server mode (#428)
- Legacy re-enable issues (#432-434)
- Claim Review Queue Backend (#440)
- Contradiction Triage Backend (#437)
- Search Explanation Backend (#438)
- Interpretations Workspace Backend (#439)

**Backend + Swift UI (both stacks needed):**
- Interpretations workspace (#423)
- Search explanation panel (#424)
- Claim review queue (#435)
- Contradiction triage (#436)
- Orchestration policies (#426)
- Advanced graph exploration (#427)
- Graph / interpretation exploration (#431)

## Next Steps for AI Agent

1. Review issues #419-440
2. Select tasks based on skill stack:
   - **Backend only** → Claim #419, #420, #421, #422, #425, #428, #429, #430, #432-434, #440, #437, #438, #439
   - **Backend + Swift** → Claim #423, #424, #426, #427, #431, #435, #436
3. Claim issues using `/claim-task <number>` or GitHub UI
4. Work on implementation
5. Mark complete with `/complete-task <number>`

## Related Documentation

- Roadmap spec: `docs/0.0.2-planning/AUTHORITATIVE_ROADMAP_SPEC.md`
- Feature gate map: `docs/0.0.2-planning/GATE-MAP.md`
- Backend API: `fichero-api/src/fichero/api/routes/`
- Models: `fichero-api/src/fichero/knowledge_models.py`

All issues are properly labeled, milestone-assigned, and ready for AI agents to claim and implement.
