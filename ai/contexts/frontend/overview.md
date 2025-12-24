# Frontend Overview

## What Fichero Frontend Does

Fichero's SwiftUI frontend provides:
- **Document Browser**: File navigation and organization
- **AI Chat Interface**: Conversational document analysis
- **Workflow Editor**: Visual AI workflow creation and management
- **Search**: Comprehensive document search with filtering
- **Metadata Inspection**: Document details and properties

## Architecture

```
SwiftUI Views → Observable State → API Client → Python FastAPI Backend
```

## Key Components

### Main Entry Point
- `Fichero/Fichero/FicheroApp.swift` - Application entry point
- Uses `AppState` and `ViewSettings` for global state management

### Core Modules
- **Views**: `Fichero/Fichero/Views/` - User interface components
  - `Browser/` - Document navigation
  - `Chat/` - AI chat interface
  - `Workflow/` - Visual workflow editor
  - `Search/` - Search functionality
  - `Inspector/` - Document metadata
- **Services**: `Fichero/Fichero/Services/` - Business logic and API integration
- **Models**: `Fichero/Fichero/Models/` - Data models and state management

### State Management
- **@Observable**: Reactive state management
- **EnvironmentObject**: Dependency injection
- **@State**: Local component state
- **@Binding**: Two-way data binding

## Development Workflow

### Running the Frontend
```bash
# Open Xcode project
open Fichero/Fichero.xcodeproj

# Build and run in Xcode
# Requires Python backend running on localhost
```

### Testing
- Unit tests: `Fichero/FicheroTests/` - Swift component tests
- UI tests: SwiftUI preview and interactive testing
- SwiftLint: Code style enforcement (`swiftlint`)

### Key Patterns
- **SwiftUI**: Declarative UI design
- **MVVM**: Model-View-ViewModel architecture
- **Combine**: Reactive programming
- **Async/Await**: Modern Swift concurrency
- **@MainActor**: Thread-safe UI updates