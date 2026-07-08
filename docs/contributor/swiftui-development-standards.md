(AI generated. Not reviewed.)

# Frontend Development Standards

**⚠️ IMPORTANT**: Fichero is **SwiftUI-first**. See `swiftui-principles.md` for mandatory guidelines.

> **Updated 2026-06-06:** "100% SwiftUI / NO AppKit" is aspirational, not
> literal. The current codebase keeps ~8 *sanctioned* `NSViewRepresentable`
> bridges where SwiftUI genuinely can't reach: PDFKit rendering + zoom, the
> image magnifier / cursor tracking, scroll-wheel zoom, Quick Look, and
> rich/plain-text editors (~18 files `import AppKit`). The rule is **SwiftUI-first,
> AppKit only behind an isolated bridge** — see `docs/ai/CLAUDE.md` → "SwiftUI-first".
> The old `APPKIT_FINAL_AUDIT.md` referenced below has been retired.

## SwiftUI-Only Policy

**SwiftUI-first** — avoid AppKit except in the sanctioned bridge cases above:
- ❌ No NSView wrapping
- ❌ No AppKit controls
- ❌ No manual layout constraints
- ❌ No NotificationCenter for app logic

**Before using AppKit:**
1. Look in demo code: `fichero/sample_code` and `fichero/sample_code/FoodTruckBuildingASwiftUIMultiplatformApp`
2. Check `Sosumi MCP Tool` for SwiftUI equivalent
3. Search Ref MCP Tool for documentation
4. Verify there's no SwiftUI-native solution

## Best Practices

### SwiftUI Development (Mandatory)
- **100% SwiftUI**: No AppKit unless absolutely unavoidable
- **@FocusedValue for Menus**: Never use NotificationCenter (see swiftui-principles.md)
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
- **SwiftUI-first**: AppKit only behind sanctioned `NSViewRepresentable` bridges (see note at top)
- **MVVM Pattern**: Separate Views, ViewModels, and Models
  > **Updated 2026-06-06:** in practice the app uses `@MainActor ObservableObject`
  > services injected via `@EnvironmentObject` (per-library / per-window) rather
  > than per-view ViewModels — see `docs/ai/CLAUDE.md` → "Multi-Window & Multi-Library
  > Architecture". Treat "MVVM" loosely: state lives in stores/services, views stay thin.
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

## File Organization & Size Guidelines

### File Size Limits (Mandatory)
**CRITICAL**: Large files are unmaintainable and slow compilation.

- **Recommended Limit**: 400 lines per file
- **Hard Limit**: 1,000 lines (requires split)
- **Type Body Limit**: 250 lines per struct/class
- **Function Limit**: 50 lines per function

**Why**: Files > 400 lines:
- Slow compilation and Xcode performance
- Difficult code review
- Hard to navigate and understand
- Higher bug risk
- Merge conflict prone

### When to Split Files

**Split immediately if**:
- File > 400 lines
- Multiple responsibilities in one file
- Difficulty finding code
- Slow Xcode autocomplete

**How to split**:
1. **By Component**: Extract sub-views into separate files
2. **By Responsibility**: Separate data models, view logic, helpers
3. **By Feature**: Group related functionality

**Example**: `EditorView.swift` (1,981 lines) should split into:
- `EditorView.swift` - Main view (< 200 lines)
- `EditorToolbar.swift` - Toolbar components
- `EditorCanvas.swift` - Canvas view
- `EditorInspector.swift` - Inspector panel
- `EditorHelpers.swift` - Helper functions

### File Organization Patterns

**✅ DO**:
```
Views/
├── Library/
│   ├── LibraryView.swift          # Main view (< 300 lines)
│   ├── DocumentRow.swift           # Row component (< 100 lines)
│   ├── DocumentInspector.swift     # Inspector panel (< 250 lines)
│   └── QuickLookComponents.swift   # Preview components
```

**❌ DON'T**:
```
Views/
└── LibraryView.swift  # 2,000 lines - UNMAINTAINABLE!
```

### Naming Conventions

**Files**:
- `PascalCase` for Swift files
- Descriptive names (`DocumentRow`, not `Row`)
- Suffix with purpose if needed (`...View`, `...Model`, `...Service`)

**Variables**:
- **Descriptive names**: Never use `x, y, a, b, i, l, r, dx, dy`
- **CamelCase**: `selectedDocument`, not `selected_document`
- **Specific**: `documentCount`, not `count`

**Functions**:
- Verb-first: `loadDocument()`, `saveWorkflow()`, `updateProgress()`
- Clear purpose: `handleFileDropOnLibrary()` vs `handleDrop()`

### Code Organization in Files

**Standard file structure**:
```swift
import SwiftUI
import OSLog  // Other imports after SwiftUI

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "FileName")

/// Main view component
struct MyView: View {
    // MARK: - Properties
    @State private var ...
    @StateObject private var ...

    // MARK: - Body
    var body: some View {
        ...
    }

    // MARK: - Subviews (computed properties)
    private var toolbar: some View { ... }
    private var content: some View { ... }

    // MARK: - Actions
    private func handleAction() { ... }

    // MARK: - Helpers
    private func calculateSomething() -> T { ... }
}

// MARK: - Supporting Types
struct HelperType { ... }

// MARK: - Preview
#Preview {
    MyView()
}
```

## Swift 6 Concurrency Guidelines

### Main Actor Isolation

**Rule**: If a class is marked `@MainActor`, all access is already serialized. Don't use dispatch queues.

**✅ DO**:
```swift
@MainActor
class MyModel: ObservableObject {
    @Published var data: [Item] = []

    func updateData() {
        data.append(newItem)  // Already on main actor
    }
}
```

**❌ DON'T**:
```swift
@MainActor
class MyModel: ObservableObject {
    private let queue = DispatchQueue(...)  // ❌ Unnecessary!

    func updateData() {
        queue.async {  // ❌ Wrong! Already on main actor
            self.data.append(newItem)
        }
    }
}
```

### Calling Main Actor Methods from Background

**Pattern**: Use `Task { @MainActor in ... }` to hop to the main actor

```swift
// In a background closure
provider.loadItem(...) { data, error in
    Task { @MainActor in
        self.updateUI(with: data)  // Now on main actor
    }
}
```

### Sendable Conformance

**Use `@unchecked Sendable` for classes with internal thread safety**:

```swift
final class AtomicCounter: @unchecked Sendable {
    private var value: Int
    private let lock = NSLock()  // Provides thread safety

    func increment() -> Int {
        lock.lock()
        defer { lock.unlock() }
        value += 1
        return value
    }
}
```

### Task Cancellation

**Always check for cancellation in async work**:

```swift
.task {
    for item in items {
        if Task.isCancelled { return }
        await processItem(item)
    }
}
```

## SwiftLint Integration

### Required Before Commit
Run SwiftLint before every commit:

```bash
cd Fichero
swiftlint
```

### Common Violations to Avoid

1. **File Length**: Keep files < 400 lines
2. **Type Body Length**: Keep structs/classes < 250 lines
3. **Function Length**: Keep functions < 50 lines
4. **Cyclomatic Complexity**: Keep functions simple (< 10 branches)
5. **Identifier Names**: Use descriptive names (no `x`, `y`, `i`, etc.)
6. **Line Length**: Keep lines < 120 characters
7. **Trailing Whitespace**: Remove all trailing whitespace

### Auto-Fix Common Issues

```bash
# Fix trailing whitespace and newlines
swiftlint --fix --format
```

## Performance Guidelines

### View Updates
- **Cache expensive computations**: Use `@State private let` for computed data
- **Don't recreate objects in body**: Use `@StateObject`, not inline creation
- **Minimize view rebuilds**: Break into smaller, focused components

### Memory Management
- **Use weak self in closures**: Prevent retain cycles
- **Release resources in deinit**: Close connections, cancel tasks
- **Profile regularly**: Use Instruments to find leaks

### Build Performance
- **Keep files small**: Large files slow compilation
- **Minimize dependencies**: Only import what you need
- **Use concrete types**: Avoid excessive protocol composition