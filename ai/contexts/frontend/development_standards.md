# Frontend Development Standards

## Best Practices

### SwiftUI Development
- **Declarative Syntax**: Use SwiftUI's declarative approach
- **View Composition**: Break complex views into smaller, reusable components
- **State Management**: Use @State for local state, @Observable for shared state
- **Accessibility**: Add accessibility modifiers and labels

### Code Quality
- **Naming Conventions**: Follow Swift API Design Guidelines
- **Type Safety**: Use strong typing and optionals appropriately
- **Error Handling**: Use Result type and proper error propagation
- **Documentation**: Use /// docstrings for public APIs

### Architecture
- **MVVM Pattern**: Separate Views, ViewModels, and Models
- **Dependency Injection**: Use @EnvironmentObject for service dependencies
- **Reactive Programming**: Use Combine for complex state management
- **Thread Safety**: Use @MainActor for UI updates

## Testing Standards

### Unit Testing
- **Isolation**: Test individual components and functions
- **Mocking**: Use protocol-based mocking for dependencies
- **XCTest**: Use Apple's testing framework
- **Coverage**: Aim for 70%+ test coverage on critical UI logic

### UI Testing
- **Preview Provider**: Use PreviewProvider for visual testing
- **Interactive Testing**: Test in Xcode preview canvas
- **Snapshot Testing**: Consider snapshot testing for complex views

### Test Organization
```
Fichero/FicheroTests/
├── ModelTests/          # Data model tests
│   ├── DocumentStoreTests.swift
│   └── WorkflowTests.swift
├── ServiceTests/        # Service layer tests
│   ├── APIClientTests.swift
│   └── DocumentServiceTests.swift
└── ViewTests/           # View component tests
    ├── DocumentListViewTests.swift
    └── WorkflowEditorTests.swift
```

### Running Tests
```bash
# Run tests in Xcode
# 1. Open Test Navigator (Cmd+6)
# 2. Select test cases
# 3. Click Run button or press Cmd+U

# Run specific test class
# Select test class in Test Navigator and run

# Code coverage
# Enable coverage in scheme settings
```

## Code Style
- **SwiftLint**: Run `swiftlint` for code style enforcement
- **Formatting**: Use Xcode's built-in formatting (Ctrl+I)
- **Imports**: Organize imports by framework (SwiftUI, Foundation, etc.)