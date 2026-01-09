# TODO-075 Completion Summary: Update WorkflowInspector with MCP Tools Tab

**Date**: 2026-01-08
**Status**: ✅ Completed

## Overview

Added MCP Tools tab to the workflow inspector panel, enabling users to browse MCP server tools and load them into the workflow registry for use in visual workflows. The implementation uses a segmented control to switch between built-in tools and MCP tools.

## Changes Made

### Updated File

**WorkflowInspector.swift** (397 lines, +187 lines added)
**Location**: `Fichero/Fichero/Views/Workflow/WorkflowInspector.swift`

## Implementation Details

### 1. Tab-Based Interface

Added a segmented control at the top of the inspector to switch between two views:
- **Built-in**: Shows tools from the workflow registry (existing behavior)
- **MCP Tools**: Shows tools from configured MCP servers (new)

```swift
enum InspectorTab: String, CaseIterable {
    case builtin = "Built-in"
    case mcp = "MCP Tools"
}

@State private var selectedTab: InspectorTab = .builtin
```

### 2. MCP Tools Section

Created a dedicated section for MCP tools with:
- **Header with Load Button**: "Load into Registry" button to make MCP tools available for drag-and-drop
- **Loading State**: Progress indicator while fetching tools from servers
- **Empty State**: Helpful message when no MCP tools are configured, with button to open MCP Servers settings
- **Grouped Display**: Tools grouped by server name with tool counts

### 3. MCP Tool Loading

Added three new data loading methods:

**loadMCPTools()**
- Fetches tools from `mcpService.getAllTools()`
- Groups tools by server name
- Lazy loads only when user switches to MCP tab

**loadIntoRegistry()**
- Calls `mcpService.loadToolsIntoWorkflowRegistry()`
- Refreshes built-in tools list to show newly loaded tools
- Automatically switches to built-in tab to show results

**loadBuiltinTools()** (existing, enhanced)
- Renamed from "Tools" to "Registry Tools" for clarity
- Maintains existing behavior for workflow registry tools

### 4. MCP Tool Display

Created `MCPToolBlockView` for consistent MCP tool presentation:
- Server icon (cube.box) to distinguish from built-in tools
- Tool name display
- Hover effect for interaction feedback
- Tooltip showing tool description
- Consistent styling with ToolBlockView

### 5. Server-Grouped Layout

MCP tools are organized by server:
- Server header with icon and name
- Tool count badge per server
- Grid layout (2 columns) matching built-in tools
- Sorted alphabetically by server name

## User Workflow

1. **Browse Built-in Tools** (Default view)
   - User opens workflow editor
   - Inspector shows tools from workflow registry
   - User can drag tools onto canvas

2. **Browse MCP Tools** (New feature)
   - User switches to "MCP Tools" tab
   - Inspector loads and displays tools from all enabled MCP servers
   - Tools are grouped by server
   - User sees tool names and descriptions

3. **Load MCP Tools into Registry**
   - User clicks "Load into Registry" button
   - MCP tools are registered in workflow system
   - Inspector automatically switches to "Built-in" tab
   - Newly loaded tools now appear with full drag-and-drop support

4. **Use MCP Tools in Workflows**
   - After loading, MCP tools function identically to built-in tools
   - Full drag-and-drop support
   - Access to ports, parameters, and configuration
   - Can be connected in workflow graphs

## Features Implemented

### ✅ Segmented Control Navigation
- Clean tab switching between built-in and MCP tools
- Persists selection during session
- Lazy loads MCP tools on first switch

### ✅ MCP Tool Browsing
- Displays all tools from all enabled MCP servers
- Groups tools by server for easy organization
- Shows tool count per server
- Maintains consistent visual style

### ✅ Registry Integration
- One-click loading of MCP tools into workflow registry
- Automatic refresh of built-in tools after loading
- Auto-switches to show newly loaded tools
- Seamless integration with existing workflow system

### ✅ Empty State Handling
- Helpful message when no MCP tools configured
- Button to open MCP Servers settings (placeholder)
- Clear guidance for users new to MCP

### ✅ Loading States
- Progress indicators for async operations
- Graceful error handling
- No blocking UI during tool loading

## Architecture Decisions

### Separation of Concerns
- **Built-in Tab**: Tools from workflow registry (full ToolInfo with ports, icons, etc.)
- **MCP Tab**: Tools from MCP servers (basic MCPToolInfo for browsing)
- Clear distinction helps users understand tool sources

### Lazy Loading
- MCP tools only load when tab is first accessed
- Reduces initial load time
- Improves performance when MCP not needed

### Explicit Registry Loading
- MCP tools require explicit "Load into Registry" action
- Prevents automatic pollution of workflow registry
- Gives users control over which MCP tools are available
- Clear feedback when tools become usable

### Consistent Visual Language
- MCPToolBlockView matches ToolBlockView styling
- Hover effects and layout consistent across tabs
- Different icons distinguish tool sources (cube.box for MCP, tool-specific for built-in)

## Integration Points

### Environment Objects Required

```swift
@EnvironmentObject var workflowService: WorkflowService  // Existing
@EnvironmentObject var mcpService: MCPService           // New requirement
```

The workflow editor must inject `mcpService` as an environment object for this feature to work.

### API Endpoints Used

- `GET /api/mcp-servers/tools/all` - Fetch all MCP tools
- `POST /api/mcp-servers/tools/load-into-workflow-registry` - Load tools into registry
- `GET /api/workflows/tools/grouped` - Fetch workflow registry tools (existing)

## Testing Approach

### Manual Testing Steps

1. **Prerequisites**:
   ```bash
   # Start backend
   PYTHONPATH=src .venv/bin/uvicorn fichero.api.main:app --port 8765

   # Ensure MCP servers configured (via TODO-074 UI)
   ```

2. **Test Tab Switching**:
   - Open workflow editor
   - Verify "Built-in" tab shows existing tools
   - Switch to "MCP Tools" tab
   - Verify segmented control updates
   - Verify tools load (progress indicator shows)

3. **Test MCP Tools Display**:
   - Verify tools grouped by server
   - Check tool counts are accurate
   - Hover over tools to verify tooltips show descriptions
   - Verify empty state if no servers configured

4. **Test Load into Registry**:
   - Click "Load into Registry" button
   - Verify loading indicator appears
   - Verify automatic switch to "Built-in" tab
   - Verify newly loaded MCP tools appear in built-in list
   - Verify MCP tools can now be dragged onto canvas

5. **Test Empty States**:
   - Remove all MCP servers (via MCP Servers UI)
   - Switch to "MCP Tools" tab
   - Verify empty state message appears
   - Verify "Open MCP Servers" button present (action TBD)

### Backend Verification

All backend functionality tested in TODO-073:
- ✅ `/api/mcp-servers/tools/all` returns tools from all servers
- ✅ `/api/mcp-servers/tools/load-into-workflow-registry` registers tools
- ✅ Tools appear in `/api/workflows/tools/grouped` after loading

## Known Limitations

1. **No Drag-and-Drop from MCP Tab**:
   - MCP tools must be loaded into registry first
   - Cannot drag MCPToolInfo directly onto canvas (lacks port definitions)
   - Future: Could support direct drag if backend provides port schema

2. **"Open MCP Servers" Button Placeholder**:
   - Button exists in empty state but action not implemented
   - TODO: Wire up to open MCP Servers sheet from AppState

3. **No Reload Button for MCP Tools**:
   - Must switch tabs to refresh MCP tools
   - Future: Add refresh button in MCP tab header

4. **No Search/Filter in MCP Tab**:
   - Large numbers of MCP tools may be hard to browse
   - Future: Add search bar like MCPToolsCatalogView

## Dependencies

- **TODO-073**: MCP Manager Backend (provides API endpoints)
- **TODO-074**: MCP Tools UI (provides MCPService)
- **WorkflowService**: Existing service for workflow registry tools
- **MCPService**: New service for MCP server tools

## Related Files

- **Backend**: `src/fichero/mcp_manager.py` (TODO-073)
- **Backend**: `src/fichero/api/routes/mcp_servers.py` (TODO-073)
- **Frontend**: `Fichero/Fichero/Services/MCPService.swift` (TODO-074)
- **Frontend**: `Fichero/Fichero/Models/WorkflowTypes.swift` (ToolInfo, CategoryTools)
- **Frontend**: `Fichero/Fichero/Views/Workflow/WorkflowEditor.swift` (parent view)

## Next Steps

1. **Wire "Open MCP Servers" Button**:
   - Add action to open MCP Servers sheet from AppState
   - Requires environment object injection or closure callback

2. **Add Refresh Button**:
   - Allow manual refresh of MCP tools without tab switching
   - Useful when MCP servers are added/modified during session

3. **Add Search/Filter**:
   - Search box in MCP tab header
   - Filter by tool name or server name
   - Match functionality from MCPToolsCatalogView

4. **Enable Direct Drag-and-Drop** (Optional):
   - Backend: Extend MCP tool schema with port definitions
   - Frontend: Allow dragging MCPToolInfo and convert to WorkflowNode
   - Would eliminate "Load into Registry" step

5. **TODO-076**: Integration Testing - MCP Workflows
   - Test end-to-end workflow creation with MCP tools
   - Verify execution with mixed built-in and MCP tools
   - Test error handling when MCP servers unavailable

## Conclusion

TODO-075 is complete. The workflow inspector now has a dedicated MCP Tools tab that allows users to browse tools from MCP servers and load them into the workflow registry. The implementation provides a clean separation between built-in and MCP tools while maintaining consistent visual design and user experience.

The two-step workflow (browse MCP tab → load into registry → use from built-in tab) is intentional, ensuring users explicitly opt-in to which MCP tools are available in their workflows and providing full tool functionality (ports, drag-and-drop) only for registered tools.
