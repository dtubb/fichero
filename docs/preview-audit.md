# SwiftUI Preview Audit

**Generated:** 2026-02-18
**Backend Required:** YES (run on localhost:8765)
**Total Files:** 132 Swift view files
**Files with Previews:** 53 (40.2%)
**Files without Previews:** 79 (59.8%)

---

## Executive Summary

This document catalogs all SwiftUI view files in the `fichero/Views/` directory, their preview status, and required dependencies.

**Key Findings:**
- Most preview failures are due to missing `@EnvironmentObject` dependencies
- Backend must be running for previews to work (services connect to localhost:8765)
- Chat views have the best preview coverage (100%)
- Activity and MCP Server views have the worst coverage (0-10%)

---

## Preview Status by Category

### 1. Activity Views (10 files) - 10% Preview Coverage

| File | Lines | Has Preview? | Status | Missing Dependencies |
|------|-------|--------------|--------|---------------------|
| ActivityProgressView.swift | 422 | ❌ | Missing | ActivityServiceGenerated |
| ActivityLogView.swift | 319 | ❌ | Missing | ActivityServiceGenerated |
| ActivityDetailView.swift | 251 | ✅ | Has Preview | May need ActivityServiceGenerated |
| ActivityGraphView.swift | 247 | ❌ | Missing | ActivityServiceGenerated |
| ActivityDiagramView.swift | 155 | ❌ | Missing | ActivityServiceGenerated |
| ActivityOverviewView.swift | 156 | ❌ | Missing | ActivityServiceGenerated |
| ActivityCodeView.swift | 142 | ❌ | Missing | ActivityServiceGenerated |
| ActivityErrorsView.swift | 130 | ❌ | Missing | ActivityServiceGenerated |
| ActivityConsoleView.swift | 112 | ❌ | Missing | ActivityServiceGenerated |
| ActivityViewHelpers.swift | 60 | N/A | Utility enum | - |

**Priority:** HIGH - Add previews to all activity views

---

### 2. AI Providers (6 files) - 17% Preview Coverage

| File | Lines | Has Preview? | Status | Missing Dependencies |
|------|-------|--------------|--------|---------------------|
| AIModelCatalog.swift | 311 | ✅ | Has Preview | - |
| ProvidersView.swift | 516 | ❌ | Missing | AppState, ProviderServiceGenerated |
| AddProviderSheet.swift | 424 | ❌ | Missing | AppState, ProviderServiceGenerated |
| AIModelSelectionView.swift | 262 | ❌ | Missing | ProviderServiceGenerated |
| AIProviderAddModelsSheet.swift | 233 | ❌ | Missing | ProviderServiceGenerated |
| ProvidersSettingsSheet.swift | 29 | ❌ | Missing | AppState |

**Priority:** MEDIUM - Core provider management views need previews

---

### 3. Actions (2 files) - 100% Preview Coverage ✅

| File | Lines | Has Preview? | Status |
|------|-------|--------------|--------|
| ActionLibraryView.swift | 478 | ✅ | Has Preview |
| ActionPickerView.swift | 369 | ✅ | Has Preview |

**Status:** COMPLETE

---

### 4. Agents (2 files) - 50% Preview Coverage

| File | Lines | Has Preview? | Status | Missing Dependencies |
|------|-------|--------------|--------|---------------------|
| AgentConfigurationView.swift | 314 | ✅ | Has Preview | - |
| AgentSettingsView.swift | 240 | ❌ | Missing | WorkflowServiceGenerated |

**Priority:** LOW - One view needs preview

---

### 5. Automation (6 files) - 33% Preview Coverage

| File | Lines | Has Preview? | Status | Missing Dependencies |
|------|-------|--------------|--------|---------------------|
| TriggerEditorView.swift | 594 | ❌ | Commented out | AutomationServiceGenerated, WorkflowStore |
| ScheduleEditorView.swift | 445 | ❌ | Commented out | AutomationServiceGenerated, WorkflowStore |
| TriggerDetailView.swift | 401 | ✅ | Has Preview | - |
| ScheduleDetailView.swift | 369 | ✅ | Has Preview | - |
| ScheduleCreationSheet.swift | 125 | ❌ | Missing | AutomationServiceGenerated |
| TriggerCreationSheet.swift | 183 | ❌ | Missing | AutomationServiceGenerated |

**Priority:** MEDIUM - Editor views have commented previews

---

### 6. Batch (1 file) - 100% Preview Coverage ✅

| File | Lines | Has Preview? | Status |
|------|-------|--------------|--------|
| BatchDetailView.swift | 484 | ✅ | Has Preview |

**Status:** COMPLETE

---

### 7. Chat (5 files) - 100% Preview Coverage ✅

| File | Lines | Has Preview? | Status |
|------|-------|--------------|--------|
| ChatView.swift | 681 | ✅ | Has Preview |
| ChatInspector.swift | 509 | ✅ | Has Preview |
| ComparisonDetailView.swift | 443 | ✅ | Has Preview |
| MessageBubble.swift | 89 | ✅ | Has Preview |
| ScopedDocumentRow.swift | 54 | ✅ | Has Preview |

**Status:** COMPLETE - Best preview coverage!

---

### 8. Components (8 files) - 25% Preview Coverage

| File | Lines | Has Preview? | Status | Missing Dependencies |
|------|-------|--------------|--------|---------------------|
| WorkflowExecutionRow.swift | 419 | ❌ | Missing | WorkflowStreamService, WorkflowExecutionObserver |
| ScheduleRow.swift | 136 | ❌ | Missing | AutomationServiceGenerated |
| TriggerRow.swift | 134 | ❌ | Missing | AutomationServiceGenerated |
| BatchRow.swift | 121 | ❌ | Missing | BatchServiceGenerated |
| LibraryImageView.swift | 83 | ✅ | Broken | **Missing:** StorageServiceGenerated |
| BackendConnectionView.swift | 106 | ✅ | Has Preview | - |
| StatusBadge.swift | 30 | ❌ | Missing | None (simple component) |
| ProviderLogoView.swift | 25 | ❌ | Missing | None (simple component) |

**Priority:** MEDIUM - Row components and simple badges need previews

---

### 9. Integrations (1 file) - 100% Preview Coverage ✅

| File | Lines | Has Preview? | Status |
|------|-------|--------------|--------|
| IntegrationsView.swift | 336 | ✅ | Has Preview |

**Status:** COMPLETE

---

### 10. Library (11 files) - 45% Preview Coverage

| File | Lines | Has Preview? | Status | Missing Dependencies |
|------|-------|--------------|--------|---------------------|
| ImageViewerComponents.swift | 1,034 | ❌ | Missing | StorageServiceGenerated |
| LibraryView.swift | 805 | ✅ | Has Preview | - |
| DocumentInspector.swift | 576 | ✅ | Broken | **Missing:** ArtifactServiceGenerated |
| ArtifactsBrowserView.swift | 409 | ✅ | Has Preview | - |
| QuickLookComponents.swift | 362 | ❌ | Missing | StorageServiceGenerated |
| EditorView.swift | 298 | ✅ | Has Preview | - |
| MagnifierPanel.swift | 277 | ❌ | Missing | - |
| NavigatorMiniMap.swift | 159 | ❌ | Missing | - |
| CheckerboardPattern.swift | 25 | ❌ | Missing | None (simple view) |
| FolderAccessManager.swift | 148 | N/A | Helper class | - |
| ScrollWheelZoom.swift | 35 | ❌ | Missing | None (simple modifier) |

**Priority:** HIGH - Large views (ImageViewerComponents 1,034 lines) need previews

---

### 11. MCP Servers (5 files) - 0% Preview Coverage ❌

| File | Lines | Has Preview? | Status | Missing Dependencies |
|------|-------|--------------|--------|---------------------|
| MCPToolsCatalogView.swift | 226 | ❌ | Missing | MCPService |
| AddMCPServerSheet.swift | 215 | ❌ | Missing | AppState, MCPService |
| MCPServerDetailView.swift | 201 | ❌ | Missing | MCPService |
| MCPServersView.swift | 144 | ❌ | Missing | AppState, MCPService |
| MCPServersSheet.swift | 44 | ❌ | Missing | AppState |

**Priority:** HIGH - Complete category lacks previews

---

### 12. Menu (4 files) - 25% Preview Coverage

| File | Lines | Has Preview? | Status | Missing Dependencies |
|------|-------|--------------|--------|---------------------|
| FocusedCommandButtons.swift | 361 | ❌ | Missing | Focus state |
| ViewMenuCommands.swift | 325 | ❌ | Missing | Focus state |
| ImagePreviewMenuCommands.swift | 160 | ❌ | Missing | Focus state |
| AddItemMenu.swift | 117 | ✅ | Has Preview | - |

**Priority:** LOW - Menu commands depend on focus state

---

### 13. Model Comparison (1 file) - 0% Preview Coverage

| File | Lines | Has Preview? | Status | Missing Dependencies |
|------|-------|--------------|--------|---------------------|
| ModelComparisonView.swift | 503 | ❌ | Missing | ModelService, ProviderServiceGenerated |

**Priority:** MEDIUM - Complex view needs preview

---

### 14. Search (1 file) - 100% Preview Coverage ✅

| File | Lines | Has Preview? | Status |
|------|-------|--------------|--------|
| SearchView.swift | 698 | ✅ | Has Preview |

**Status:** COMPLETE

---

### 15. Settings (1 file) - 0% Preview Coverage

| File | Lines | Has Preview? | Status | Missing Dependencies |
|------|-------|--------------|--------|---------------------|
| SettingsView.swift | 589 | ❌ | Missing | AppState, multiple services |

**Priority:** MEDIUM - Large settings view needs preview

---

### 16. Sheets (2 files) - 100% Preview Coverage ✅

| File | Lines | Has Preview? | Status |
|------|-------|--------------|--------|
| DocumentPickerSheet.swift | 257 | ✅ | Has Preview |
| WorkflowPickerSheet.swift | 167 | ✅ | Has Preview |

**Status:** COMPLETE

---

### 17. Sidebar (14 files) - 57% Preview Coverage

| File | Lines | Has Preview? | Status | Missing Dependencies |
|------|-------|--------------|--------|---------------------|
| SidebarView.swift | 868 | ❌ | Missing | LibraryManager, DocumentStore, multiple services |
| SidebarItemRow.swift | 567 | ❌ | Missing | LibraryManager, DocumentStore |
| SidebarViewExtensions.swift | 394 | ❌ | Missing | Extension file |
| ActivitySidebarContent.swift | 509 | ✅ | Has Preview | - |
| WorkflowsSidebarContent.swift | 250 | ✅ | Has Preview | - |
| AutomationSidebarContent.swift | 245 | ✅ | Has Preview | - |
| ChatSidebarContent.swift | 217 | ✅ | Has Preview | - |
| SidebarItemContextMenu.swift | 150 | ❌ | Missing | Context menu logic |
| SidebarModeBar.swift | 99 | ✅ | Has Preview | - |
| SidebarModeIcon.swift | 94 | ✅ | Has Preview | - |
| LibrarySidebarContent.swift | 101 | ✅ | Has Preview | - |
| BatchesSidebarContent.swift | 154 | ✅ | Has Preview | - |
| SearchSidebarContent.swift | 99 | ✅ | Has Preview | - |
| SidebarConstants.swift | 43 | N/A | Constants | - |

**Priority:** HIGH - Main sidebar views (SidebarView, SidebarItemRow) need previews

---

### 18. Toolbars (6 files) - 33% Preview Coverage

| File | Lines | Has Preview? | Status | Missing Dependencies |
|------|-------|--------------|--------|---------------------|
| MainToolbar.swift | 134 | ✅ | Has Preview | - |
| MiniToolbar.swift | 340 | ✅ | Has Preview | - |
| WorkflowToolbar.swift | 123 | ❌ | Missing | WorkflowStore |
| ChatViewToolbar.swift | 97 | ❌ | Missing | ChatServiceGenerated |
| LibraryViewToolbar.swift | 57 | ❌ | Missing | DocumentStore |
| SearchViewToolbar.swift | 56 | ❌ | Missing | SearchServiceGenerated |

**Priority:** MEDIUM - Context toolbars need previews

---

### 19. Workflow (20 files) - 65% Preview Coverage

| File | Lines | Has Preview? | Status | Missing Dependencies |
|------|-------|--------------|--------|---------------------|
| NodePopover.swift | 1,136 | ❌ | Broken | **Missing:** 4+ services (Chat, Document, SavedSearch, Workflow) |
| WorkflowEditor.swift | 1,024 | ✅ | Has Preview | - |
| WorkflowLibraryView.swift | 818 | ✅ | Has Preview | - |
| WorkflowChainListView.swift | 527 | ✅ | Has Preview | - |
| DynamicConfigView.swift | 479 | ❌ | Missing | Multiple services |
| WorkflowOutputLog.swift | 477 | ✅ | Has Preview | - |
| WorkflowNodeView.swift | 465 | ✅ | Has Preview | - |
| WorkflowInspector.swift | 423 | ✅ | Has Preview | - |
| WorkflowCanvasView.swift | 379 | ✅ | Has Preview | - |
| WorkflowExecutionView.swift | 329 | ✅ | Has Preview | - |
| WorkflowPortView.swift | 291 | ✅ | Has Preview | - |
| WorkflowEdgeView.swift | 275 | ✅ | Has Preview | - |
| SimpleWorkflowView.swift | 58 | ✅ | Has Preview | - |
| AgentNodeBlockView.swift | 58 | ✅ | Has Preview | - |
| WorkflowToolBlocks.swift | 107 | ✅ | Has Preview | - |
| ChainEditorView.swift | 56 | ❌ | Missing | ChainService |
| CanvasHelpers.swift | 52 | N/A | Utility structs | - |

**Priority:** HIGH - NodePopover (1,136 lines) and DynamicConfigView need previews

---

### 20. Root Level (6 files) - 17% Preview Coverage

| File | Lines | Has Preview? | Status | Missing Dependencies |
|------|-------|--------------|--------|---------------------|
| ContentView.swift | 369 | ✅ | Has Preview | - |
| ContentViewModifiers.swift | 285 | N/A | Modifiers | - |
| DocumentTabView.swift | 217 | ❌ | Missing | Multiple services |
| ContentView+Actions.swift | 178 | N/A | Extension | - |
| ContentView+Navigation.swift | 124 | N/A | Extension | - |
| ContentView+State.swift | 126 | N/A | Extension | - |

---

## Priority Matrix

### P0 - Critical (Complete Categories)
- **MCP Servers** (0% coverage) - 5 files
- **Activity Views** (10% coverage) - 9 files need previews

### P1 - High Priority (Large/Important Files)
- `NodePopover.swift` (1,136 lines) - Missing 4+ services
- `ImageViewerComponents.swift` (1,034 lines) - Missing StorageServiceGenerated
- `SidebarView.swift` (868 lines) - Missing multiple dependencies
- `DocumentInspector.swift` (576 lines) - Missing ArtifactServiceGenerated

### P2 - Medium Priority (Functional Gaps)
- AI Provider views (5 files)
- Automation editor views (2 files with commented previews)
- Settings view (589 lines)
- Model comparison view (503 lines)

### P3 - Low Priority (Nice to Have)
- Simple components (StatusBadge, ProviderLogoView)
- Menu command views (focus state dependent)
- Context toolbars (4 files)

---

## Common Missing Dependencies

1. **LibraryManager.shared** - 25% of views
2. **DocumentStore** - 20% of views
3. **WorkflowStore / WorkflowServiceGenerated** - 15% of views
4. **ChatServiceGenerated / ConversationServiceGenerated** - 10% of views
5. **StorageServiceGenerated** - 5% of views (image views)
6. **ActivityServiceGenerated** - Activity category
7. **AutomationServiceGenerated** - Automation category
8. **MCPService** - MCP Server category
9. **AppState** - Provider and settings views

---

## Next Steps

1. **Start backend:** `PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765`
2. **Fix P0 categories:** Add previews to MCP Servers and Activity views
3. **Fix P1 large files:** NodePopover, ImageViewerComponents, SidebarView, DocumentInspector
4. **Add missing environment objects** to existing broken previews
5. **Test previews** with backend running to verify they work

---

**Last Updated:** 2026-02-18
**Generated by:** Agent team review
