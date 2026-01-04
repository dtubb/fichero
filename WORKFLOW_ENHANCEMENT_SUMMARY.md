# Fichero Workflow System Enhancement - Executive Summary

**Date**: January 4, 2026
**Prepared by**: Claude Code
**Status**: Planning Complete - Ready for Review

---

## What I've Done

I've analyzed your comprehensive requirements and created a detailed implementation plan that addresses everything you've outlined. The plan breaks down the work into **5 phases with 26 discrete tasks** (TODO-063 through TODO-088).

---

## The Big Picture

Transform Fichero into a comprehensive AI workflow orchestration platform with:

1. **Workflow Persistence** - Save, load, import, export workflows
2. **Batch Execution** - Run workflows at scale (100s of files) with start/stop/resume
3. **MCP Integration** - Use external tools, expose Fichero as MCP server
4. **Workflow Chaining** - Connect workflows (transcribe → catalogue)
5. **Model Comparison** - Test prompts across multiple models
6. **Automation** - Schedule workflows, trigger on file system events
7. **Activity Monitor** - Real-time visibility into all operations

---

## Phase Breakdown

### Phase 0: Quick Win (1-2 days)
**TODO-063**: Increase default window size
- Fixes sidebar being cut off
- Immediate user value
- No backend changes required

### Phase 1: Workflow Persistence (2-3 weeks)
**5 tasks** - Database schema, API endpoints, UI for save/load/import/export
- Workflows persist in DuckDB
- JSON import/export
- Workflow library in UI

### Phase 2: Batch Execution Engine (3-4 weeks)
**7 tasks** - Job queue, activity tracking, WebSocket streaming, UI
- Execute workflows on 100+ files
- Start/stop/pause/resume
- Real-time progress tracking
- Activity monitor showing all operations

### Phase 3: MCP Tools & Agents (2-3 weeks)
**5 tasks** - MCP client/server, dynamic tool loading, UI
- Connect to external MCP servers
- Load external tools dynamically
- Expose Fichero as MCP server
- Other agents can trigger Fichero workflows

### Phase 4: Advanced Features (3-4 weeks)
**8 tasks** - Chaining, comparison, automation, action library
- Workflow chaining (SubWorkflow tool)
- Model comparison UI
- Scheduler (cron-like)
- File system triggers
- Reusable action library

---

## Technical Approach

### Backend First (As You Requested)
1. Design database schema
2. Implement Python backend with unit tests
3. Create API endpoints
4. Test thoroughly
5. Then build SwiftUI frontend
6. Integration tests

### New Backend Modules
```
src/fichero/
├── workflows/persistence.py     # CRUD operations
├── workflows/batch.py            # Batch execution engine
├── mcp/                          # MCP client & server
├── automation/                   # Scheduling & triggers
└── activities/                   # Activity tracking
```

### New Frontend Views
```
Fichero/Fichero/Views/
├── Workflow/WorkflowListView.swift   # Saved workflows
├── Sidebar/CompareMode.swift         # Model comparison
├── Activities/ActivityMonitor.swift  # Real-time activity
└── Automation/AutomationView.swift   # Schedules & triggers
```

### Database Extensions
New tables: `workflows`, `jobs`, `job_items`, `activities`, `schedules`, `triggers`

---

## Key Architectural Decisions

### 1. Workflow Persistence
- Store workflows as JSON in DuckDB `workflows` table
- Pydantic models for validation
- Import/export as JSON files
- Versioning for backwards compatibility

### 2. Batch Execution
- Async job queue using Python asyncio
- Job state machine: pending → running → paused/completed/failed
- Checkpoint system for resume
- Per-item status tracking

### 3. Activity Tracking
- Centralized activity log in database
- WebSocket streaming for real-time updates
- Hierarchical activities (parent/child relationships)
- Fallback to polling if WebSocket fails

### 4. MCP Integration
- MCP client connects to external servers
- Dynamic tool loading from MCP
- Fichero exposes own MCP server
- Tools appear in workflow editor

### 5. Automation
- APScheduler for cron-like scheduling
- Watchdog for file system monitoring
- Trigger configuration in database
- Integration with job queue

---

## Risk Mitigation

### High-Risk Areas
1. **Batch execution complexity** → Comprehensive unit tests, state machine diagram
2. **WebSocket stability** → Reconnection logic, fallback to polling
3. **MCP integration** → Test with multiple servers, graceful degradation
4. **Concurrency bugs** → Proper async/await, thorough testing

### Medium-Risk Areas
1. **Database migrations** → Migration tools, backup procedures
2. **Swift/Python coordination** → Shared data models, API versioning
3. **Performance at scale** → Performance testing, resource limits

---

## Timeline

**Total Duration**: 10-14 weeks
- Phase 0: 1-2 days (quick win)
- Phase 1: 2-3 weeks (persistence foundation)
- Phase 2: 3-4 weeks (batch execution)
- Phase 3: 2-3 weeks (MCP integration)
- Phase 4: 3-4 weeks (advanced features)

**Approach**: One phase at a time, fully tested before moving to next

---

## What's Next?

### Immediate Next Steps
1. **Review this plan** - Confirm scope and approach match your vision
2. **Start with TODO-063** - Window size fix (quick win, 1-2 hours)
3. **Then Phase 1** - Build workflow persistence layer
4. **Iterate** - Complete each phase, test thoroughly, move to next

### Questions for You
1. Does this breakdown match what you envisioned?
2. Are there any tasks missing or out of scope?
3. Should we adjust the priority of any phases?
4. Ready to start with the window size fix?

---

## Deliverables Created

1. **Master Plan**: `ai/docs/workflow-system-master-plan.md`
   - Full technical specification
   - Database schemas
   - API endpoint definitions
   - File organization
   - Testing strategy

2. **This Summary**: `WORKFLOW_ENHANCEMENT_SUMMARY.md`
   - Executive overview
   - Phase breakdown
   - Next steps

---

## Commitment to Principles

✅ **Backend first** with unit tests
✅ **Don't break things** - all existing features preserved
✅ **SwiftUI only** - no AppKit unless unavoidable
✅ **Small steps** - 26 discrete, testable tasks
✅ **Go slow** - one phase at a time
✅ **Test thoroughly** - unit + integration tests for each phase

---

## Ready to Proceed?

I recommend starting with **TODO-063 (window size fix)** as a quick win while we discuss the larger phases. This gives you immediate value while we refine the plan for the workflow system.

After the window size fix, we can tackle Phase 1 (workflow persistence) methodically, building a solid foundation for everything else.

**What would you like to do first?**

1. Start with TODO-063 (window size fix)?
2. Adjust the plan based on feedback?
3. Deep dive into a specific phase?
4. Something else?

---

**Contact**: Ready for your feedback and direction!
