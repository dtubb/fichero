# Task: TODO-149: Implement v0.0.1 Feature Flagging
**Priority**: P0
**Milestone**: v0.0.1
**Status**: Planning

## 1. Problem Statement
Fichero has many advanced features (Workflows, MCP, Automation) that are currently in various states of completion. For the v0.0.1 release, we want a "hardened core" document manager experience. Showing incomplete features creates a poor user experience and increases the surface area for bugs.

## 2. Proposed Solution
Implement a centralized `FeatureManager` (or `FeatureFlags`) service in Swift that determines which modules are visible in the Sidebar and Menus.

- **Storage**: A simple hardcoded configuration for now.
- **Dynamic Override**: Add an environment variable (e.g., `FICHERO_ALL_FEATURES=1`) or a hidden "Debug" section in the app to allow us to turn them back on instantly for development without a recompile.
- **GUI Integration**:
    - **Sidebar**: Entire sections (e.g., "Workflows", "Automation") will be removed from the sidebar list if their flag is false.
    - **Menus**: Commands under "File" and "View" that pertain to disabled features will be removed using SwiftUI's conditional menu commands.
    - **Toolbar**: Any global toolbar items for disabled features will be hidden.

- **Scope**:
    - `isWorkflowsEnabled`
    - `isAgentsEnabled`
    - `isAutomationEnabled`
    - `isMCPEnabled`
    - `isChatEnabled` (maybe keep for 0.0.1 if stable)

## 3. Implementation Plan
- [x] Step 1: Create `FeatureManager.swift` in `Models/`.
- [x] Step 2: Integrate `FeatureManager` into UI components.
    - [x] Sidebar Mode Bar: Hide disabled modes.
    - [x] Sidebar Bottom Toolbar: Hide creation buttons.
    - [x] Add Item Menu: Hide sections/items.
    - [x] View Menu Bar: Hide mode buttons.
- [ ] Step 3: Add a "Debug" or "Features" section in Settings/Inspector to toggle flags.
- [ ] Step 4: Verify that switching a flag in code instantly updates the UI.

## 4. Verification Plan
- [ ] Automated Tests: Ensure `FeatureManager` returns correct defaults.
- [ ] Manual Check: Verify Sidebar only shows Library/Search/Chat (if enabled) in v0.0.1 mode.
- [ ] Linting: Zero `swiftlint` warnings in new files.

## 5. Progress Log
- [2026-02-27 15:42]: Task created and planning initiated.
