# Frontend Development Standards

**⚠️ IMPORTANT**: Fichero is **100% SwiftUI**. See `SWIFTUI_PRINCIPLES.md` for mandatory guidelines.

## SwiftUI-Only Policy

**NO AppKit** - We use pure SwiftUI except in absolutely unavoidable cases:
- ❌ No NSView wrapping
- ❌ No AppKit controls
- ❌ No manual layout constraints
- ❌ No NotificationCenter for app logic

**Before using AppKit:**
1. Look in demo code: `/Users/dtubb/code/fichero_main/fichero/sample_code` and `/Users/dtubb/code/fichero_main/fichero/sample_code/FoodTruckBuildingASwiftUIMultiplatformApp`
2. Check `Sosumi MCP Tool` for SwiftUI equivalent
3. Search Ref MCP Tool for documentation
4. Verify there's no SwiftUI-native solution

## Best Practices

### SwiftUI Development (Mandatory)
- **100% SwiftUI**: No AppKit unless absolutely unavoidable
- **@FocusedValue for Menus**: Never use NotificationCenter (see SWIFTUI_PRINCIPLES.md)
- **Cache Computations**: Don't rebuild hierarchies on every view update
- **Handle Cancellation**: All .task {} blocks must check Task.isCancelled
- **View Composition**: Break complex views into < 300 line files
- **@ViewBuilder**: Use on all computed view properties
- **OSLog**: Use structured logging, not NSLog or print
- **State Management**: @StateObject, @ObservedObject, @EnvironmentObject, @State
- **Accessibility**: Add labels and modifiers to all interactive elements

### MCP Tools for SwiftUI
- **Sosumi (`sosumi.ai/mcp`)**: Official Apple SwiftUI documentation
  - `searchAppleDocumentation("swiftui drag drop")`
  - `fetchAppleDocumentation("path/to/doc")`
- **Ref (`ref`)**: Swift language and library docs
  - `searchDocumentation("Swift @Observable")`
  - `readUrl("url/from/search")`

Use these BEFORE implementing custom solutions!

### Code Quality
- **SwiftLint**: Required before committing (catches AppKit usage)
- **Naming Conventions**: Follow Swift API Design Guidelines
- **Type Safety**: Use strong typing and optionals appropriately
- **Error Handling**: Use Result type and proper error propagation
- **Documentation**: Use /// docstrings for public APIs

### Architecture
- **Pure SwiftUI**: No AppKit view hierarchy
- **MVVM Pattern**: Separate Views, ViewModels, and Models
- **Dependency Injection**: Use @EnvironmentObject for services (never create in views)
- **Reactive Programming**: Use @Observable (iOS 17+) or Combine
- **Thread Safety**: Use @MainActor for UI updates (not DispatchQueue.main)

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