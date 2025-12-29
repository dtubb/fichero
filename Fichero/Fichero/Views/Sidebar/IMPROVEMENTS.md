# SwiftUI Best Practices Improvements

This document outlines recommended improvements to make the Sidebar more SwiftUI-idiomatic, following Apple's patterns from official samples like Food Truck.

## Current Issues

### 1. Parameter Explosion (Anti-pattern)
**Current**: SidebarItemRow has 9 parameters
```swift
SidebarItemRow(
    item: item,
    allCachedItems: allCachedItems,
    expandedItems: $expandedItems,
    renameState: renameState,
    deleteState: deleteState,
    documentStore: documentStore,
    savedSearchService: savedSearchService,
    conversationService: conversationService,
    workflowStore: workflowStore
)
```

**Apple's Pattern**: Use @EnvironmentObject
```swift
// From Food Truck sample
@EnvironmentObject private var model: Model

// Our equivalent
@EnvironmentObject private var services: SidebarServices
```

### 2. Magic Numbers
**Current**: Hard-coded values throughout
```swift
.padding(.leading, 4)
.opacity(0.3)
```

**Better**: Named constants (created in SidebarConstants.swift)
```swift
.padding(.leading, SidebarConstants.itemLeadingPadding)
.opacity(SidebarConstants.dropTargetOpacity)
```

### 3. ViewModifier Overuse
**Current**: Private struct modifiers
```swift
.modifier(SidebarStyleModifiers())
.modifier(SidebarToolbarModifiers(...))
```

**Apple's Pattern**: View extensions
```swift
extension View {
    func sidebarStyle() -> some View { ... }
    func sidebarToolbar(...) -> some View { ... }
}
```

### 4. Computed Properties in body
**Current**: Recalculated every render
```swift
var body: some View {
    let isFolder: Bool = {
        if case .document(let doc) = item.itemType {
            return doc.docType == .folder
        }
        return false
    }()
}
```

**Better**: Extract to property
```swift
private var isFolder: Bool {
    guard case .document(let doc) = item.itemType else { return false }
    return doc.docType == .folder
}
```

### 5. Logging
**Current**: NSLog (Objective-C era)
```swift
NSLog("[SidebarView] Moving item...")
```

**Apple's Pattern**: os.Logger (structured logging)
```swift
import OSLog

private let logger = Logger(subsystem: "com.fichero.app", category: "Sidebar")

logger.info("Moving item \(itemID)")
logger.debug("Drop completed")
```

### 6. Missing Documentation
**Current**: No /// comments

**Apple's Pattern**: Comprehensive documentation
```swift
/// Individual row for sidebar items.
///
/// Displays hierarchical content using `DisclosureGroup` and handles:
/// - Inline rename with `TextField`
/// - Drag & drop operations
/// - Context menus
///
/// - Note: This view recursively renders child items for folders.
struct SidebarItemRow: View {
```

## Recommended Changes

### Phase 1: Extract Constants ✅
- [x] Create SidebarConstants.swift
- [x] Define all layout constants
- [x] Define opacity values

### Phase 2: Create Environment ✅
- [x] Create SidebarEnvironment.swift
- [x] Define SidebarServices container
- [ ] Update SidebarView to use environment
- [ ] Update SidebarItemRow to use environment

### Phase 3: Replace ViewModifiers
- [ ] Convert SidebarStyleModifiers to extension
- [ ] Convert SidebarToolbarModifiers to extension
- [ ] Convert SidebarCacheModifiers to extension

### Phase 4: Documentation
- [ ] Add /// comments to all public types
- [ ] Add /// comments to all public methods
- [ ] Add code examples where helpful

### Phase 5: Modern Logging
- [ ] Replace NSLog with os.Logger
- [ ] Use structured logging categories
- [ ] Add appropriate log levels (debug, info, error)

### Phase 6: Optimize Computed Properties
- [ ] Move isFolder out of body
- [ ] Cache expensive computed values
- [ ] Use @State for memoization where needed

## Benefits

1. **Reduced Complexity**: 9 parameters → 2-3 parameters
2. **Better Testability**: Can mock SidebarServices
3. **Maintainability**: Constants in one place
4. **Performance**: Fewer recompilations, better caching
5. **Apple-like**: Follows official sample patterns
6. **Debuggable**: Structured logging with categories

## Implementation Order

1. Start with SidebarConstants (no breaking changes)
2. Add SidebarEnvironment (parallel to existing)
3. Gradually migrate views to use environment
4. Replace ViewModifiers with extensions
5. Add documentation throughout
6. Replace NSLog with Logger
7. Optimize computed properties

## References

- [Food Truck Sample](https://developer.apple.com/documentation/swiftui/food_truck_building_a_swiftui_multiplatform_app)
- [SwiftUI Best Practices](https://developer.apple.com/documentation/swiftui)
- [os.Logger Documentation](https://developer.apple.com/documentation/os/logger)
