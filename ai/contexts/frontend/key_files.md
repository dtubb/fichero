# Frontend Key Files

## Essential Files for Development

### Main Entry Points
- `Fichero/Fichero/FicheroApp.swift` - Application entry point
- `Fichero/Fichero/ContentView.swift` - Main content view

### Core Views
- `Fichero/Fichero/Views/Browser/` - Document browser components
- `Fichero/Fichero/Views/Chat/` - AI chat interface
- `Fichero/Fichero/Views/Workflow/` - Visual workflow editor
- `Fichero/Fichero/Views/Search/` - Search functionality
- `Fichero/Fichero/Views/Inspector/` - Document metadata inspection

### Services (Business Logic)
- `Fichero/Fichero/Services/APIClient.swift` - Backend API communication
- `Fichero/Fichero/Services/DocumentService.swift` - Document management
- `Fichero/Fichero/Services/ChatService.swift` - Chat functionality
- `Fichero/Fichero/Services/WorkflowService.swift` - Workflow processing
- `Fichero/Fichero/Services/SearchService.swift` - Search operations

### Models (Data & State)
- `Fichero/Fichero/Models/Document.swift` - Document data model
- `Fichero/Fichero/Models/DocumentStore.swift` - Document state management
- `Fichero/Fichero/Models/Workflow.swift` - Workflow data model
- `Fichero/Fichero/Models/WorkflowStore.swift` - Workflow state management
- `Fichero/Fichero/Models/Provider.swift` - Provider configurations

### State Management
- `Fichero/Fichero/Models/AppState.swift` - Global application state
- `Fichero/Fichero/Models/ViewSettings.swift` - View configuration

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