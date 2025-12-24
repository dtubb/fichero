# Frontend Development Context

## Overview

SwiftUI frontend development patterns and best practices for Fichero macOS application.

## Key Components

- **Main Application**: `Fichero/Fichero/FicheroApp.swift`
- **Views**: `Fichero/Fichero/Views/`
- **Services**: `Fichero/Fichero/Services/`
- **Models**: `Fichero/Fichero/Models/`

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