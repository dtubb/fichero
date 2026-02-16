# Frontend Key Files

**Last Updated**: December 31, 2025

## Essential Files for Development

### Main Entry Points
- **App Layer** (`Fichero/Fichero/App/`)
  - `FicheroApp.swift` - Application entry point, menu bar, window management
  - `AppState.swift` - Global application state (100% SwiftUI `@Observable`)
  - `ViewSettings.swift` - View configuration and layout settings
- **Main View**
  - `Fichero/Fichero/Views/ContentView.swift` - Three-column layout (Sidebar | Content | Inspector)
  - `Fichero/Fichero/Views/DocumentTabView.swift` - Tab/window management for documents

### Core View Layers

#### Sidebar (`Views/Sidebar/`)
**Multi-mode navigation** (Navigate, Search, Chat, Workflows, Activity)
- `SidebarView.swift` - Main sidebar container (691 lines - needs split)
- `SidebarItemRow.swift` - Hierarchical item display (482 lines - needs split)
- `SidebarSectionHeader.swift` - Collapsible section headers
- `SidebarItemContextMenu.swift` - Right-click context menus
- `SidebarConstants.swift` - Shared constants and icons
- `SidebarTypes.swift` - Enums and type definitions
- **Note**: Sidebar supports hierarchical documents (folders) but NOT yet hierarchical searches/chats/workflows

#### Library (`Views/Library/`)
**Document management and preview**
- `LibraryView.swift` - Document grid/list view (664 lines - needs split)
- `EditorView.swift` - **CRITICAL: 1,981 lines - MUST SPLIT**
- `DocumentInspector.swift` - Metadata inspector panel
- `QuickLookComponents.swift` - Document preview with folder access management
- `FolderAccessManager.swift` - Security-scoped bookmark management (macOS sandbox)

#### Chat (`Views/Chat/`)
**AI conversation interface**
- `ChatView.swift` - Main chat interface (425 lines - needs split)
- `ChatInspector.swift` - Chat settings and document scope (497 lines - needs split)

#### Workflow (`Views/Workflow/`)
**Visual LangGraph workflow editor**
- `WorkflowCanvasView.swift` - Node-based canvas (764 lines - needs split)
- `WorkflowEditor.swift` - Workflow editor wrapper with toolbar
- `WorkflowInspector.swift` - Tool palette sidebar
- `WorkflowNodeView.swift` - Individual node rendering (complexity: 27 - CRITICAL)
- `WorkflowPortView.swift` - Input/output port rendering
- `WorkflowEdgeView.swift` - Connection lines between nodes
- `WorkflowOutputLog.swift` - Execution log panel

#### Search (`Views/Search/`)
**Full-text and semantic search**
- `SearchView.swift` - Search interface (473 lines - needs split)

#### AI Providers (`Views/AIProviders/`)
**LLM provider management**
- `ProvidersView.swift` - Provider list and configuration (489 lines - needs split)
- `AddProviderSheet.swift` - Add new provider sheet (413 lines - needs split)
- `AIModelSelectionView.swift` - Model browser and selector
- `AIModelCatalog.swift` - Hugging Face model discovery
- `AIProviderAddModelsSheet.swift` - Add models to provider

#### Menu & Toolbars (`Views/Menu/`, `Views/Toolbars/`)
**Menu commands and toolbar controls**
- `FocusedCommandButtons.swift` - @FocusedValue menu command handlers
- `ViewMenuCommands.swift` - View menu commands
- `ImagePreviewMenuCommands.swift` - Image preview commands
- `MiniToolbar.swift` - Floating mini toolbar
- `*Toolbar.swift` - Per-view toolbars (Library, Workflow, Chat, Search)

#### Components (`Views/Components/`)
**Reusable UI components**
- `BackendConnectionView.swift` - Backend status indicator
- `LibraryImageView.swift` - Image display component
- `ProviderLogoView.swift` - Provider logo display
- `StatusBadge.swift` - Status indicator badges

### Services Layer (`Services/`)
**Business logic and API communication**

#### Core Services
- **APIClient.swift** - HTTP client for backend communication (406 lines)
- **DocumentService.swift** - Document CRUD operations
- **ChatService.swift** - Chat/conversation management
- **WorkflowService.swift** - Workflow execution and management
- **SearchService.swift** - Search operations
- **ProviderService.swift** - AI provider configuration (431 lines - needs split)
- **ModelService.swift** - Model management
- **StorageService.swift** - File storage operations
- **ImportService.swift** - File ingestion (LINK/COPY modes)

#### Specialized Services
- **DragDropService.swift** - Drag and drop handling (Swift 6 compliant)
- **ErrorService.swift** - Error reporting and handling
- **PerformanceService.swift** - Performance monitoring
- **ConversationService.swift** - Conversation management
- **SavedSearchService.swift** - Saved search management

### Models Layer (`Models/`)
**Data structures and state management**

#### Document Models
- **Document.swift** - Core document data model
- **DocumentStore.swift** - Document state management (516 lines - needs split)
- **FicheroDocument.swift** - Document wrapper for tabs/windows
- **LibraryManager.swift** - Library hierarchy management (415 lines)

#### Workflow Models
- **Workflow.swift** - Local workflow model for UI operations
- **WorkflowTypes.swift** - Manual type definitions (TO BE SIMPLIFIED - see TODO-126)
- **WorkflowStore.swift** - Workflow state management
- **WorkflowExporter.swift** - Workflow export functionality
- **GeneratedTypeExtensions.swift** - Extensions for generated OpenAPI types

#### Generated API Client (`FicheroAPIClient/`)
- **Package.swift** - Local Swift package for generated client
- **.build/.../Types.swift** - Generated types from OpenAPI spec
- Uses Swift OpenAPI Generator plugin
- See `docs/architecture/swiftui/api_migration_guide.md` for patterns

#### Provider Models
- **Provider.swift** - Provider configuration model
- **CacheModel.swift** - Response caching model

#### UI State Models
- **ViewContexts.swift** - View mode contexts (Library, Chat, Workflow, Search)
- **SidebarState.swift** - Sidebar state management
- **SidebarItem.swift` - Sidebar item data model
- **WindowState.swift** - Window state management
- **DragDropModel.swift** - Drag and drop state (Swift 6 compliant)
- **ErrorModel.swift** - Error representation

### Critical Files Requiring Action

**IMMEDIATE (Production Blockers)**:
1. **EditorView.swift** (1,981 lines) - Split into 5 files
2. **WorkflowNodeView.swift** (Complexity: 27) - Refactor to < 10

**HIGH PRIORITY (Maintainability)**:
3. **WorkflowCanvasView.swift** (764 lines) - Split into 2-3 files
4. **SidebarView.swift** (691 lines) - Split into 2 files
5. **LibraryView.swift** (664 lines) - Split into 2 files
6. **DocumentStore.swift** (516 lines) - Split by responsibility
7. **ChatInspector.swift** (497 lines) - Extract scoped documents panel
8. **ProvidersView.swift** (489 lines) - Extract provider settings
9. **SidebarItemRow.swift** (482 lines) - Extract rendering logic

## Development Tips

### Finding Files in Xcode
```bash
# Open Xcode project
open Fichero/Fichero.xcodeproj

# Use Xcode's file navigator to browse
# Use Cmd+Shift+O for quick file search
# Use Cmd+Click to jump to definitions
```

### Code Navigation
```bash
# List all Swift files
find Fichero/Fichero -name "*.swift"

# Search for specific functionality
grep -r "DocumentList" Fichero/Fichero/Views/
```

### Understanding Structure
- Views are organized by feature in `Views/` directory
- Services handle API communication and business logic
- Models contain data structures and state management
- Use `@Observable` for reactive state updates