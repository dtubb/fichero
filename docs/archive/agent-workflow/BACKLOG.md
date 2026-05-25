# BACKLOG.md -- Fichero Development Tasks

## Phase 0: Constitution & Planning (CURRENT)

No coding until this phase is complete and approved.

### Dev Environment Setup

- [ ] P0 Create Python venv and install dependencies @fichero-lead
  - Context: .venv does not exist. Need: `cd ~/code/fichero && python3 -m venv fichero-engine/.venv && fichero-engine/.venv/bin/pip install -e fichero-engine/`
  - Blocker for: all backend tests, pylint, API contract validation
- [ ] P0 Install swiftlint @fichero-lead
  - Context: `brew install swiftlint`. Blocker for: all frontend lint checks.
  - Note: brew may not be installed either -- check first.

### Constitution

- [x] P0 Review and improve all constitution files for consistency @constitution-auditor
  - Completed: ralph-loop pass 1 (2026-02-26)
  - Context: First pass -- check SOUL, USER, AGENTS, TOOLS, MEMORY for contradictions and gaps
- [ ] P0 Validate constitution against actual codebase state @plan-reviewer
  - Context: Are file counts, feature descriptions, commands accurate? Run builds, check paths.
- [ ] P1 Validate team roles against actual project needs @plan-reviewer
  - Context: Confirm each team role maps to real work, remove unnecessary roles
- [ ] P1 Create shared context files for team agents @fichero-lead
  - Context: _shared/ directory with architecture summary, key paths, conventions

### Feature Audit

- [ ] P0 Audit frontend features: what works, what's broken, what's untested @swift-dev
  - Context: Walk through every sidebar mode (Library, Search, Chat, Workflows, Activity, Automation, Batches). Document status of each.
- [ ] P0 Audit backend features: what works, what's broken, what's untested @python-dev
  - Context: Test each API endpoint group. Document which return correct data, which error, which are stubs.
- [ ] P0 Audit test coverage: what's tested, what's missing @plan-reviewer
  - Context: Run pytest with coverage. Run xcodebuild tests. Map coverage gaps.

### Feature Flag System Design

- [ ] P0 Design feature flag system for Swift frontend @plan-reviewer
  - Context: Compile-time flags (#if DEBUG), runtime toggles, or build scheme configs? Need to easily enable/disable features for dev vs release.
- [ ] P0 Design feature flag system for Python backend @plan-reviewer
  - Context: Environment variables, config file, or feature registry? Must match frontend approach.
- [ ] P1 Document which features get flagged and their current status @plan-reviewer
  - Context: Feature matrix: name, frontend status, backend status, test status, flag default (on/off)

### Milestone Plan

- [ ] P0 Create milestone plan with achievable targets @plan-reviewer
  - Context: Break the path to v1.0 into milestones. Each milestone = a shippable state with a defined feature set. Earlier milestones have fewer features but everything works.
  - Output: tasks/PLAN.md with milestones, feature sets, dependencies, and criteria
- [ ] P1 Define Milestone 1 (MVP): core features only, fully working and tested @plan-reviewer
  - Context: What's the smallest useful Fichero? Probably: library management, basic ingest, document viewing.
- [ ] P1 Define Milestone 2: add AI features (search, chat, workflows) @plan-reviewer
  - Context: Layer AI on top of working base. Each AI feature behind a flag.

### Skills & Tooling

- [ ] P1 Skill: feature-audit -- structured audit of a feature area @fichero-lead
  - Context: Reusable skill to test a feature, document its status, and file issues
- [ ] P1 Skill: create-milestone -- template for defining a new milestone @fichero-lead
- [ ] P2 Skill: toggle-feature -- enable/disable a feature flag @fichero-lead

## Phase 1: Stabilization (after plan approval)

- [ ] P1 Complete OpenAPI client migration (20 files using manual APIClient) @swift-dev
- [ ] P1 Refactor EditorView.swift (1,981 lines) @swift-dev
- [ ] P1 API contract alignment audit @python-dev
- [ ] P2 SwiftLint full compliance (69 violations remaining) @swift-dev

## Phase 2: Documentation

- [ ] P1 Create frontend user manual structure @frontend-docs
- [ ] P1 Create backend user manual structure @backend-docs
- [ ] P2 Start development blog @blog-scribe

## Phase 3: New Capabilities

- [ ] P2 MCP server integration plan @mcp-dev
- [ ] P2 AppleScript support design @mcp-dev
- [ ] P2 Backend CLI mode design @cli-dev
- [ ] P2 Backend web UI mode design @web-dev
