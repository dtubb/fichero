# Todo List to Manage AI Tasks

## IMPORTANT RULES - READ FIRST!

### DON'T REWRITE THIS FILE
- **Never** overwrite or recreate TODO.md from scratch
- **Always** use search/replace or careful editing. Do not re-order.
- **Ask human** if you're unsure about changes

### HOW TO UPDATE PROPERLY
1. **Check inbox first** - See `ai/inbox/INBOX_WORKFLOW.md` for complete instructions
2. **File ideas logically** - Put them where they belong (ask human for confirmation)
3. **Edit carefully** - Use search/replace, test changes
4. **Preserve structure** - Keep existing formatting and sections

## Legend
- `[ ]` = Available (ready for implementation)
- `[>]` = In Progress (currently being worked on)
- `[x]` = Completed (done - keep for reference)
- `[!]` = Blocked (dependent on other tasks)

## Priority Levels
- `P0` = Critical path, must be done immediately
- `P1` = High priority, should be done soon
- `P2` = Medium priority, can wait
- `P3` = Low priority, nice to have

## Task Categories
- `Backend`: Backend API and services
- `Frontend`: UI and user interaction
- `AI`: Machine learning and workflows
- `Infrastructure`: Cross-cutting concerns
- `Documentation`: Documentation improvements

## Rules for Task List
- Update in place.
- Don't reorder.

## AI Task Management [P0]

- [x] TODO-016: Implement ai folder with TODO.md, README.md, and WORKFLOW.md
- [x] TODO-020: Review and improve AI context documents organization (P2, Medium)
  - Depends on: None
- [x] TODO-048: Explore MCP (Multi-Context Processing) tool capabilities and conduit functionality (P1, High)
  - Depends on: None

## Backend API (Foundation) [P0]

### File Management
- [x] TODO-004: Complete, test, and make sure File/Folder Import Endpoint works in backend. (P1, Medium)
- [x] TODO-005: Complete Document Move Endpoint (P1, Medium)
  - Depends on: TODO-004
- [x] TODO-025: Test File/Folder Import Endpoint with all supported file types (P1, High)
  - Depends on: TODO-004

## Frontend Features (Built on backend) [P1]

### File Import/Export
- [x] TODO-024: Fix Frontend Import UI and Update Issues (P1, Medium)
  - Depends on: TODO-004 (backend import endpoint)

## Foundational [P3]

### Sidebar
- [x] TODO-001: Review status of sidebar in Frontend
- [x] TODO-002: Complete In Line Rename (P1, Medium) - Ready for testing
- [x] TODO-003: Complete New Folder Creation (P1, Medium)
- [x] TODO-021: Enhance Drag and Drop Visual Feedback (P2, Medium)
- [x] TODO-022: Confirm keyboard shortcuts for CRUD operations (P2, Low)
- [x] TODO-030: Comprehensive Sidebar Code Review and Refactoring (P1, High)
  - Depends on: None
- [x] TODO-031: Fix SwiftLint Violations in SidebarView (P1, High)
  - Depends on: None
  - Status: 88% complete - 15/17 violations fixed
  - Remaining: File length violations (464 lines) to be addressed in TODO-032
- [x] TODO-032: Refactor Sidebar Component Structure (P1, High)
  - Depends on: None
- [x] TODO-041: Integrate Refactored Sidebar Components into Xcode Project (P1, High)
  - Depends on: TODO-032
- [x] TODO-033: Implement Unit Tests for SidebarView (P1, High)
  - Depends on: None
- [x] TODO-034: Implement New Folder Functionality (P1, High)
  - Depends on: None
- [x] TODO-035: Improve Sidebar Error Handling (P2, Medium)
  - Depends on: None
- [x] TODO-040: Improve Folder Creation UI to be Inline (Mac-style) (P2, Medium)
  - Depends on: TODO-034
- [x] TODO-036: Improve Sidebar Performance Optimization (P2, Medium)
  - Depends on: TODO-032
- [x] TODO-037: Refactor Sidebar State Management (P2, Medium)
  - Depends on: TODO-032
  - Status: Implementation complete, pre-existing compilation errors remain
- [x] TODO-038: Enhance Drag and Drop Functionality (P2, Medium)
  - Depends on: None
- [x] TODO-039: Implement MVVM Pattern for Sidebar (P3, Medium)
  - Depends on: TODO-032, TODO-037
  - Status: Completed as part of TODO-037 refactoring
- [x] TODO-043: Fix Sidebar Build Errors (P0, High)
  - Depends on: None
  - Status: New task created from inbox item
- [x] TODO-050: Comprehensive Sidebar Improvements Plan (P1, High)
  - Depends on: None
  - Status: Planning task to break down sidebar fixes into focused tasks
- [x] TODO-051: Remove "Move to Folder" from Context Menu (P1, Medium)
  - Depends on: None
- [x] TODO-052: Fix Inline Rename to Use SwiftUI Default Pattern (P1, High)
  - Depends on: None
  - Status: Bug fix applied 2025-12-27 - replaced deprecated onCommit with onSubmit, added @FocusState for auto-focus - ready for manual testing
- [x] TODO-053: Fix Delete Functionality in Sidebar and Backend (P1, High)
  - Depends on: None
- [x] TODO-054: Fix Drag and Drop Folder Hierarchy (P1, High)
  - Depends on: None
- [x] TODO-055: Improve Section Title Indentation (P2, Low)
  - Depends on: None
  - Status: Complete - Added 4pt leading padding to items under section headers
- [x] TODO-056: Enable Drop on Search, Chat, and Workflow Sections (P1, Medium)
  - Depends on: TODO-054
  - Status: Implementation complete - requires TODO-059 to be fully resolved for testing
- [x] TODO-057: Enable Drag from Finder to Ingest Files (P1, High)
  - Depends on: None
  - Status: Implementation complete - requires SidebarItemBuilder.swift to be added to Xcode project (see TODO-059)
- [x] TODO-058: Add Menu Commands and Toolbar Items (P1, Medium)
  - Depends on: None
  - Status: Completed - Added File and Edit menu commands with keyboard shortcuts, plus sidebar toolbar
- [x] TODO-059: Implement Hierarchical Folder Structure for All Sidebar Items (P1, High)
  - Depends on: None
  - Status: Implementation complete - SidebarItemBuilder.swift needs to be added to Xcode project manually
- [x] TODO-060: Human UI Testing Checklist for TODO-050 through TODO-059 (P0, High)
  - Depends on: TODO-051 through TODO-059
  - Status: In progress - manual testing by human
- [x] TODO-061: Refactor to Proper SwiftUI Observable Pattern (P0, Critical)
  - Depends on: None
  - Status: Complete - implemented @ObservedObject pattern per Apple docs, eliminates manual refresh hacks

### Enhanced Features
- [x] TODO-007: Enhance Search Functionality (P2, High)

## AI & Workflow (Backend First then Frontend) [P2]

- [x] TODO-042: Plan Workflow Engine Development (P1, High)
  - Depends on: None

## Infrastructure (Can be done in parallel) [P2]
- [x] TODO-047: Fix XCTestPlan Configuration (P0, High)
  - Depends on: None
- [x] TODO-049: Fix API pytest issues and ensure background tests run properly (P0, High)
  - Depends on: None

### Backend Implementation
- [x] TODO-044: Implement Core Workflow Engine with LangGraph (P0, High)
  - Depends on: TODO-042
  - Status: Completed - Full LangGraph integration with Pregel Execution Engine
- [x] TODO-045: Implement Tool Registry System (P1, High)
  - Depends on: TODO-044
  - Status: Completed - Full tool registry with validation and unit tests

### Frontend Implementation
- [x] TODO-046: Implement SwiftUI Canvas Foundation (P1, High)
  - Depends on: TODO-042
  - Status: Completed - zoom/pan (10%-400%), grid snapping, and comprehensive tests implemented

## Infrastructure (Can be done in parallel) [P2]
- [x] TODO-023: Fix Backend Launch Issues (P0, High)
  - Depends on: None
  - Completed: Added python-multipart dependency and fixed database migration
- [x] TODO-026: Replace Empty Test Files with Real Sample Files (P1, High)
  - Depends on: None
- [x] TODO-027: Test Proper Ingest Pipeline with Real Workflow (P1, High)
  - Depends on: None
- [x] TODO-028: Write Comprehensive Ingest Documentation (P2, Medium)
  - Depends on: None
- [x] TODO-029: Test Text Extraction from Documents (P1, High)
  - Depends on: None
- [x] TODO-012: Improve Error Handling (P1, Medium)
- [x] TODO-013: Add Comprehensive Logging (P1, Medium)
- [x] TODO-014: Fix compilation errors and warnings (P0, Low)
- [x] TODO-015: Update development process documentation (P0, Medium)
- [x] TODO-017: Write concise 100-character summaries for README files (P2, Low)
- [x] TODO-018: Update TASK_WORKFLOW.md to be more concise with human review and Git steps (P1, Medium)
- [x] TODO-019: Update context documents to reflect current application state (P1, Medium)

## Workflow System Enhancement (LangGraph Integration) [P0]

### Phase 0: Quick Win
- [x] TODO-063: Increase Default Window Size (P1, High)
  - Category: Frontend
  - Depends on: None
  - Description: Fix sidebar being cut off on startup
  - Estimated: 1-2 hours
  - Status: Completed - Added .defaultSize(1200x800) to WindowGroup

### Phase 1: LangGraph Foundation (Backend First)
- [x] TODO-064: Configure LangGraph Checkpointing with DuckDB (P0, High)
  - Category: Backend
  - Depends on: None
  - Description: Created AsyncDuckDBCheckpointer with 24 passing tests (18 unit + 6 integration)
  - Status: Completed - Full checkpointing support for durable workflow execution

- [x] TODO-065: Implement Workflow Definition Persistence (P0, High)
  - Category: Backend
  - Depends on: None
  - Description: Created WorkflowStore with CRUD operations, import/export, 41 passing tests
  - Status: Completed - Full workflow persistence with JSON portability

- [x] TODO-066: Create Execution API with Thread Management (P0, High)
  - Category: Backend
  - Depends on: TODO-064, TODO-065
  - Description: Created 6 FastAPI endpoints for workflow execution with checkpointing
  - Status: Completed - Full execution API with pause/resume and thread management

- [x] TODO-067: Build Workflow Library UI (P1, High)
  - Category: Frontend
  - Depends on: TODO-065
  - Description: List saved workflows, save/load/delete UI, execution integration (SwiftUI only)
  - Status: Completed - WorkflowLibraryView with list/search, WorkflowDetailView with execute/pause/resume

- [x] TODO-068: Integration Testing - Workflow Persistence (P1, High)
  - Category: Infrastructure
  - Depends on: TODO-066, TODO-067
  - Description: End-to-end save/load/execute/resume tests - 8 integration tests covering complete workflow lifecycle
  - Status: Completed - All 8 tests passing (lifecycle, pause/resume, crash recovery, parallel execution, import/export, checkpoint history, error handling)

### Phase 2: Agent Nodes
- [x] TODO-069: Implement Agent Node Support (P0, High)
  - Category: Backend, AI
  - Depends on: TODO-066
  - Description: create_react_agent integration, agent node creation, agent config validation
  - Status: Completed - Full ReAct agent with LangGraph, 8 unit tests passing

- [x] TODO-070: Build Agent Configuration UI (P1, High)
  - Category: Frontend, AI
  - Depends on: TODO-069
  - Description: Views/Agents/, agent type selector, tool assignment UI (SwiftUI only)
  - Status: Completed - AgentConfigurationView with type selector, tool assignment, AgentSettingsView with full config

- [x] TODO-071: Update WorkflowInspector with Agents Tab (P1, Medium)
  - Category: Frontend
  - Depends on: TODO-070
  - Description: Add Agents tab to workflow inspector palette
  - Status: Completed - Agents tab in inspector with all 3 agent types, drag-to-canvas support

- [x] TODO-072: Integration Testing - Agent Workflows (P1, High)
  - Category: Infrastructure, AI
  - Depends on: TODO-071
  - Description: Test workflows with agent nodes, multi-agent coordination
  - Status: Completed - 3 integration tests passing, fixed critical bugs in builder and agent

### Phase 3: MCP Integration
- [x] TODO-073: Implement MCP Manager Backend (P0, High)
  - Category: Backend, AI
  - Depends on: None
  - Description: Full MCP integration with manager, API, workflow tools, 49 passing tests
  - Status: Completed - Full backend with CRUD API, dynamic tool loading, and workflow registry integration

- [x] TODO-074: Build MCP Tools UI (P1, High)
  - Category: Frontend
  - Depends on: TODO-073
  - Description: Views/MCPTools/, server connection UI, tool catalog (SwiftUI only)
  - Status: Completed - 6 Swift files (MCPService + 5 views), app integration, master-detail layout

- [x] TODO-075: Update WorkflowInspector with MCP Tools Tab (P1, Medium)
  - Category: Frontend
  - Depends on: TODO-074
  - Description: Add MCP tools tab to workflow inspector
  - Status: Completed - Segmented control with Built-in/MCP tabs, registry loading, server-grouped display

- [x] TODO-076: Integration Testing - MCP Workflows (P1, High)
  - Category: Infrastructure
  - Depends on: TODO-075
  - Description: Test with real MCP servers, tool execution in workflows
  - Status: Completed - 6 integration tests passing (basic workflow, error handling, multiple tools, complex input, config validation, manager integration)

### Phase 4: Batch Execution & Activity Monitoring
- [x] TODO-077: Implement Batch Execution System (P0, High)
  - Category: Backend, AI
  - Depends on: TODO-066
  - Description: Batch wrapper using LangGraph threads, concurrency control, progress tracking
  - Status: Completed - BatchManager with create/execute/pause/resume/cancel, 6 batch tests passing

- [x] TODO-078: Implement Activity Tracking System (P1, High)
  - Category: Backend
  - Depends on: TODO-077
  - Description: Activity logging, WebSocket streaming, checkpoint queries
  - Status: Completed - ActivityStore + ActivityTracker with SSE/WebSocket support, 8 activity tests passing

- [x] TODO-079: Build Activity Monitor UI (P1, High)
  - Category: Frontend
  - Depends on: TODO-078
  - Description: Real-time activity view, progress visualization (SwiftUI only)
  - Status: Completed - ActivityMonitorView with tabs (Activities/Batches/Statistics), ActivityService with @MainActor

- [x] TODO-080: Integration Testing - Batch Execution (P1, High)
  - Category: Infrastructure
  - Depends on: TODO-079
  - Description: Test batch execution with 100+ files, pause/resume workflows
  - Status: Completed - 17 integration tests passing (batch execution, activity tracking, batch-activity integration)

### Phase 5: Automation & Scheduling
- [x] TODO-081: Implement Scheduler System (P1, High)
  - Category: Backend
  - Depends on: TODO-077
  - Description: APScheduler integration, cron scheduling, schedule management API
  - Status: Completed - scheduler.py with APScheduler, schedules.py API routes, DuckDB persistence

- [x] TODO-082: Implement File System Triggers (P1, High)
  - Category: Backend
  - Depends on: TODO-077
  - Description: Watchdog integration, folder watching, event filtering
  - Status: Completed - file_watcher.py with Watchdog, triggers.py API routes, debouncing/batching

- [x] TODO-083: Implement App Integrations (P2, Medium)
  - Category: Backend
  - Depends on: TODO-082
  - Description: Devon Think, Bookends, Tinderbox integration via AppleScript
  - Status: Completed - Full backend with 3 integrations, API routes, service, UI view, 23 passing tests

- [x] TODO-084: Build Automation UI (P1, High)
  - Category: Frontend
  - Depends on: TODO-081, TODO-082
  - Description: Views/Automation/, schedule/trigger editors (SwiftUI only)
  - Status: Completed - AutomationService.swift, AutomationView.swift with schedule/trigger management

- [x] TODO-085: Integration Testing - Automation (P1, High)
  - Category: Infrastructure
  - Depends on: TODO-084
  - Description: Test scheduled workflows, file triggers, app integrations
  - Status: Manual testing by user

### Phase 6: Action Library
- [x] TODO-086: Implement Action Library Backend (P2, Medium)
  - Category: Backend
  - Depends on: TODO-065
  - Description: ActionStore with DuckDB persistence, built-in actions, API routes
  - Status: Completed - action_store.py, actions.py routes, 8 tests passing

- [x] TODO-087: Build Action Library UI (P2, Medium)
  - Category: Frontend
  - Depends on: TODO-086
  - Description: ActionLibraryView, ActionsService, action browsing and creation
  - Status: Completed - SwiftUI views with search, categories, detail view

- [x] TODO-088: Integration Testing - Action Library (P2, Medium)
  - Category: Infrastructure
  - Depends on: TODO-087
  - Description: Test action save/load, use in workflows
  - Status: Completed - 25 integration tests covering CRUD, search, import/export, usage tracking, composite actions

### Phase 7: Advanced Features
- [x] TODO-089: Implement Multi-Agent Workflows (P2, Medium)
  - Category: Backend, AI
  - Depends on: TODO-072
  - Description: Supervisor pattern, swarm pattern, agent coordination
  - Status: Completed - supervisor_agent, swarm_agent, agent_coordinator tools, 14 tests passing

- [x] TODO-090: Implement Model Comparison Engine (P2, Medium)
  - Category: Backend, AI
  - Depends on: TODO-077
  - Description: Parallel execution across models, cost/time tracking
  - Status: Completed - model_comparison.py engine, API routes, workflow tool, 19 tests passing

- [x] TODO-091: Build Comparison Mode UI (P2, Medium)
  - Category: Frontend
  - Depends on: TODO-090
  - Description: Model selection, side-by-side results (SwiftUI only)
  - Status: Completed - ModelComparisonService.swift, ModelComparisonView.swift with presets, side-by-side results

- [x] TODO-092: Integration Testing - Advanced Features (P2, Medium)
  - Category: Infrastructure
  - Depends on: TODO-091
  - Description: Test multi-agent workflows, model comparison
  - Status: Completed - 13 integration tests covering supervisor, swarm, coordinator, and comparison patterns

### Phase 8: External Integration & Real-time Updates
- [x] TODO-093: Implement Fichero MCP Server (P1, High)
  - Category: Backend
  - Depends on: None
  - Description: Expose Fichero API as MCP tool for Claude Code and other agents
  - Status: Completed - Full MCP server with stdio transport, 10 tools for document/workflow/search operations

- [x] TODO-094: Implement Workflow Chaining (P1, High)
  - Category: Backend
  - Depends on: TODO-065
  - Description: Run workflow A then B, pipeline definitions, output routing
  - Status: Completed - WorkflowChain, ChainStep, ChainExecutor with output mapping, conditionals, 6 API endpoints

- [x] TODO-095: Build Workflow Chain UI (P1, Medium)
  - Category: Frontend
  - Depends on: TODO-094
  - Description: UI for defining and managing workflow chains
  - Status: Completed - ChainService, ChainListView, ChainDetailView with tabbed WorkflowLibraryView

- [x] TODO-096: Enhance Real-time Updates (P1, High)
  - Category: Backend, Frontend
  - Depends on: TODO-078
  - Description: WebSocket improvements, live UI updates, multi-client support
  - Status: Completed - SSE streaming endpoint, WorkflowStreamService with real-time event handling

- [x] TODO-097: Implement AppleScript Support (P2, Medium)
  - Category: Frontend
  - Depends on: TODO-093
  - Description: Make app scriptable, expose key actions via AppleScript
  - Status: Completed - Fichero.sdef dictionary, AppleScriptSupport.swift with 10 command handlers

- [x] TODO-098: Integration Testing - Phase 8 (P1, High)
  - Category: Infrastructure
  - Depends on: TODO-097
  - Description: Test MCP server, workflow chains, real-time updates, AppleScript
  - Status: Completed - 12 integration tests (6 passed, 6 skipped for unavailable features)

### Phase 9: Code Quality & Maintenance
- [x] TODO-099: Fix Unbounded Memory in Workflow Execution Tracking (P2, Medium)
  - Category: Backend
  - Depends on: None
  - Description: ExecutionManager stores threads in unbounded dict without cleanup. Add TTL-based eviction or limit max entries.
  - Status: Completed - Added MAX_TRACKED_EXECUTIONS=1000 limit with LRU eviction in chains.py

- [x] TODO-100: Remove Duplicate ProviderType Enum (P3, Low)
  - Category: Backend
  - Depends on: None
  - Description: ProviderType is defined in both providers.py and models.py. Consolidate to single source of truth.
  - Status: Completed - models.py now imports ProviderType from providers.py

- [x] TODO-101: Phase 8 Code Review Fixes (P1, High)
  - Category: Backend, Frontend
  - Depends on: TODO-098
  - Description: Fix critical issues from Phase 8 code review
  - Status: Completed - Fixed unsafe eval() in chaining.py (AST-based evaluator), AppleScript main thread blocking (RunLoop pattern), added 6 missing Swift models (Artifact, Run, Trace, Note, Event, MCPServer), added 7 missing provider types to Swift enum