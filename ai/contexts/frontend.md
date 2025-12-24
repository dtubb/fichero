# Frontend Development Context

## Overview

SwiftUI frontend development patterns and best practices for Fichero's macOS document management application.

## Key Components

- **Main Application**: `Fichero/Fichero/FicheroApp.swift` - Application entry point
- **Views**: `Fichero/Fichero/Views/` - User interface components
  - `Browser/` - Document browser and navigation
  - `Chat/` - AI chat interface
  - `Inspector/` - Document inspection and metadata
  - `Search/` - Search functionality
  - `Sidebar/` - Navigation sidebar with rename and new folder dialogs
  - `Workflow/` - AI workflow canvas and management
  - `ModelBrowserView.swift` - Model browsing interface
- **Services**: `Fichero/Fichero/Services/` - Business logic and API integration
  - `APIClient.swift` - Backend API communication
  - `ChatService.swift` - Chat functionality
  - `DocumentService.swift` - Document management
  - `ModelService.swift` - Model management
  - `ProviderService.swift` - Provider configuration
  - `SearchService.swift` - Search operations
  - `SavedSearchService.swift` - Saved search management
  - `WorkflowService.swift` - Workflow processing
- **Models**: `Fichero/Fichero/Models/` - Data models and state management
  - `Document.swift`, `DocumentStore.swift` - Document data and state
  - `Provider.swift` - Provider configuration
  - `SidebarItem.swift` - Sidebar navigation items
  - `Workflow.swift`, `WorkflowStore.swift` - Workflow data and state
  - `WorkflowTypes.swift`, `WorkflowExporter.swift` - Workflow type definitions

## Development Patterns

### SwiftUI View Structure

```swift
struct DocumentListView: View {
    @State private var documents: [Document] = []
    @State private var isLoading = false
    @State private var error: Error?
    
    @EnvironmentObject var documentStore: DocumentStore
    
    var body: some View {
        List(documents, id: \.id) { document in
            DocumentRow(document: document)
        }
        .overlay {
            if isLoading { ProgressView() }
        }
        .alert("Error", isPresented: .constant(error != nil)) {
            Button("OK") { error = nil }
        } message: {
            Text(error?.localizedDescription ?? "Unknown error")
        }
        .onAppear {
            loadDocuments()
        }
    }
    
    private func loadDocuments() {
        isLoading = true
        Task {
            do {
                documents = try await documentStore.fetchDocuments()
                isLoading = false
            } catch {
                self.error = error
                isLoading = false
            }
        }
    }
}
```

### State Management

```swift
@Observable
class DocumentStore {
    var documents: [Document] = []
    var isLoading = false
    var error: Error?
    
    private let apiClient: APIClient
    
    func fetchDocuments() async throws {
        isLoading = true
        defer { isLoading = false }
        
        do {
            documents = try await apiClient.getDocuments()
        } catch {
            self.error = error
            throw error
        }
    }
}
```

### API Integration

```swift
class APIClient {
    func getDocuments() async throws -> [Document] {
        let url = baseURL.appendingPathComponent("/api/v1/documents/")
        
        let (data, response) = try await urlSession.data(from: url)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        
        return try JSONDecoder().decode([Document].self, from: data)
    }
}
```

## Testing

### Unit Testing
```swift
class DocumentStoreTests: XCTestCase {
    func testFetchDocumentsSuccess() async {
        let mockAPIClient = MockAPIClient()
        mockAPIClient.mockDocuments = [Document(id: "1", name: "Test")]
        
        let documentStore = DocumentStore(apiClient: mockAPIClient)
        
        try await documentStore.fetchDocuments()
        
        XCTAssertEqual(documentStore.documents.count, 1)
        XCTAssertNil(documentStore.error)
    }
}
```

### UI Testing
```swift
class DocumentListViewTests: XCTestCase {
    func testDocumentListView() {
        let documentStore = DocumentStore(apiClient: MockAPIClient())
        documentStore.documents = [
            Document(id: "1", name: "Document 1"),
            Document(id: "2", name: "Document 2")
        ]
        
        let view = DocumentListView()
            .environmentObject(documentStore)
        
        // Test view rendering and interactions
    }
}
```

## Best Practices

- Use SwiftUI's declarative syntax
- Implement proper state management with @Observable
- Follow MVVM architecture patterns
- Add accessibility support
- Use proper error handling
- Write comprehensive tests
- Follow Swift API Design Guidelines
- Use @MainActor for UI updates
- Implement proper thread safety

## Style Guide

### Code Organization
- **File Structure**: One file per component, organized by feature
- **Naming**: Use descriptive, concise names following Swift naming conventions
- **Imports**: Group imports by framework (SwiftUI, Foundation, etc.)

### SwiftUI Patterns
- **View Composition**: Break complex views into smaller, reusable components
- **State Management**: Use @State for local state, @Observable for shared state
- **Bindings**: Use @Binding for two-way data flow between components
- **Environment**: Use @EnvironmentObject for dependency injection

### Code Formatting
- **Indentation**: 4 spaces (Swift standard)
- **Line Length**: Keep lines under 120 characters when possible
- **Spacing**: Use consistent spacing around operators and after commas
- **Braces**: Opening braces on same line, closing braces on new line

### Documentation
- **Comments**: Use // for single-line, /* */ for multi-line comments
- **Docstrings**: Use /// for public API documentation
- **Markdown**: Use markdown formatting in docstrings for better readability

## Feature Planning Context

### Current Focus Areas
- **Core UI Functionality**: Complete inline rename, new folder creation, and drag-and-drop operations
- **AI Workflows**: Enhance workflow canvas and visual editing capabilities
- **Search**: Implement comprehensive search interface with filtering and saved searches
- **Batch Operations**: Add support for bulk document operations

### Architecture Evolution
- **Component Organization**: Maintain clear separation between views, services, and models
- **State Management**: Use @Observable for reactive state updates
- **Error Handling**: Improve user feedback and error recovery
- **Performance**: Optimize view rendering and data loading

### Future Considerations
- **Accessibility**: Ensure full accessibility compliance
- **Internationalization**: Support for multiple languages
- **Theming**: Dark mode and customizable UI themes
- **Keyboard Shortcuts**: Comprehensive keyboard navigation
- **Responsive Design**: Adapt to different window sizes and orientations