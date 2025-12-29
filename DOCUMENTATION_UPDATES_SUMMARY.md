# Documentation Updates Summary: SwiftUI-Only Mandate

**Date:** 2025-12-28
**Status:** ✅ Complete

---

## Overview

Updated all frontend documentation to enforce **100% SwiftUI** development with NO AppKit unless absolutely unavoidable. Added comprehensive guidance on using MCP tools (Sosumi, Ref) for looking up proper SwiftUI APIs before implementing custom solutions.

---

## Files Updated

### 1. ✅ CLAUDE.md (Root Project Guide)

**Location:** `/Users/dtubb/code/fichero_main/fichero/CLAUDE.md`

**Changes:**
- Added **⚠️ CRITICAL: 100% SwiftUI - NO AppKit** section to Swift Code Quality
- Mandated checking Sosumi MCP before using AppKit
- Added MCP tool usage examples for SwiftUI development
- Referenced `SWIFTUI_PRINCIPLES.md` as required reading
- Expanded Sosumi MCP section with practical examples
- Added Ref MCP documentation search guidance
- Specified OSLog over NSLog, @MainActor over DispatchQueue.main
- Added view file size limits (< 300 lines)

**Key Additions:**
```markdown
**⚠️ CRITICAL: 100% SwiftUI - NO AppKit**

- **Pure SwiftUI Only**: Do NOT use AppKit views, NSView wrapping, or AppKit controls
- **Before using AppKit**: Check Sosumi MCP for SwiftUI equivalent
- **Use MCP Tools for Documentation**:
  - `sosumi.searchAppleDocumentation()` - Official Apple SwiftUI docs
  - `ref.searchDocumentation()` - Swift language reference
- **No NotificationCenter**: Use `@FocusedValue` for menu commands
```

---

### 2. ✅ development_standards.md (Frontend Standards)

**Location:** `/Users/dtubb/code/fichero_main/fichero/ai/contexts/frontend/development_standards.md`

**Changes:**
- Added **⚠️ IMPORTANT** banner linking to SWIFTUI_PRINCIPLES.md
- Created new "SwiftUI-Only Policy" section
- Added explicit AppKit prohibitions (NSView, controls, layout constraints)
- Added "Before using AppKit" checklist
- Expanded "SwiftUI Development (Mandatory)" section with all P0 fixes
- Added comprehensive MCP Tools section with examples
- Updated Architecture section to emphasize "Pure SwiftUI"
- Changed threading guidance from Combine to @MainActor

**Key Additions:**
```markdown
**⚠️ IMPORTANT**: Fichero is **100% SwiftUI**. See `SWIFTUI_PRINCIPLES.md` for mandatory guidelines.

## SwiftUI-Only Policy

**NO AppKit** - We use pure SwiftUI except in absolutely unavoidable cases:
- ❌ No NSView wrapping
- ❌ No AppKit controls
- ❌ No manual layout constraints
- ❌ No NotificationCenter for app logic

**Before using AppKit:**
1. Check Sosumi MCP for SwiftUI equivalent
2. Search Ref MCP for documentation
3. Verify there's no SwiftUI-native solution
```

---

### 3. ✅ SWIFTUI_PRINCIPLES.md (NEW - Comprehensive Guide)

**Location:** `/Users/dtubb/code/fichero_main/fichero/ai/contexts/frontend/SWIFTUI_PRINCIPLES.md`

**Status:** Newly created - 350+ line comprehensive guide

**Sections:**
1. **Core Philosophy** - SwiftUI-only mandate, what NOT to use
2. **SwiftUI Best Practices (Mandatory)** - 8 detailed patterns:
   - Proper State Management
   - @FocusedValue for Menu Commands
   - Cache Expensive Computations
   - Handle Task Cancellation
   - Use @ViewBuilder
   - Split Large Views
   - Proper Logging (OSLog)
   - Avoid AppKit
3. **MCP Tools for SwiftUI Development** - Detailed Sosumi & Ref usage
4. **Anti-Patterns to Avoid** - 5 common mistakes with examples
5. **SwiftUI Patterns to Follow** - Observable, DI, Navigation
6. **Code Review Checklist** - 10-point verification list
7. **Resources** - Links to other documentation

**Key Features:**
- ✅ / ❌ examples for every pattern
- Before/After code comparisons
- MCP tool usage decision matrix
- Comprehensive anti-pattern catalog
- Mandatory code review checklist

**Example Content:**
```swift
### 1. Use Proper State Management

**✅ DO:**
@StateObject private var documentStore = DocumentStore()
@ObservedObject var documentStore: DocumentStore
@EnvironmentObject var appState: AppState

**❌ DON'T:**
var body: some View {
    let service = DocumentService()  // ❌ Wrong!
}
```

---

## MCP Tools Documentation

### Sosumi (Apple Documentation)

**Added to:** CLAUDE.md, development_standards.md, SWIFTUI_PRINCIPLES.md

**Purpose:** Official Apple SwiftUI, Swift, and HIG documentation

**Usage Examples:**
```swift
// Finding SwiftUI APIs
sosumi.searchAppleDocumentation("swiftui drag drop")
sosumi.searchAppleDocumentation("NavigationSplitView")
sosumi.searchAppleDocumentation("human interface guidelines color")

// Fetching full documentation
sosumi.fetchAppleDocumentation("path/from/search/result")
```

**Use Cases:**
- Finding SwiftUI view modifiers
- Learning proper SwiftUI patterns
- Checking Human Interface Guidelines
- Verifying SwiftUI equivalents before using AppKit

---

### Ref (General Documentation)

**Added to:** CLAUDE.md, SWIFTUI_PRINCIPLES.md

**Purpose:** Swift language, libraries, and general programming docs

**Usage Examples:**
```swift
// Swift language features
ref.searchDocumentation("Swift @Observable macro")
ref.searchDocumentation("Swift TaskGroup")

// SwiftUI patterns
ref.searchDocumentation("SwiftUI MVVM pattern")

// Third-party libraries
ref.searchDocumentation("Swift Combine framework")

// Reading documentation
ref.readUrl("url/from/search")
```

**Use Cases:**
- Swift language features
- SwiftUI API reference
- Third-party Swift libraries
- General programming patterns

---

### MCP Tool Decision Matrix

**Added to:** SWIFTUI_PRINCIPLES.md

| Question | Tool |
|----------|------|
| "How do I do X in SwiftUI?" | Sosumi |
| "What's the SwiftUI equivalent of Y?" | Sosumi |
| "How does Swift feature Z work?" | Ref |
| "What are the HIG guidelines for...?" | Sosumi |
| "How do I use library X?" | Ref |

---

## SwiftUI Patterns Documented

### 1. State Management ✅

**Documented in:** All files

- `@StateObject` - Owning state
- `@ObservedObject` - Passed-in state
- `@EnvironmentObject` - Dependency injection
- `@State` - Local view state
- `@Binding` - Two-way bindings
- `@Observable` - New iOS 17+ pattern

**Anti-pattern:** Creating service instances in views

---

### 2. Menu Commands via @FocusedValue ✅

**Documented in:** CLAUDE.md, SWIFTUI_PRINCIPLES.md

**Replaces:** NotificationCenter (anti-pattern)

**Pattern:**
```swift
// Define
extension FocusedValues {
    var sidebarActions: SidebarActions? { ... }
}

// Provide
.focusedValue(\.sidebarActions, actions)

// Consume
@FocusedValue(\.sidebarActions) private var actions
```

---

### 3. Caching Expensive Computations ✅

**Documented in:** CLAUDE.md, development_standards.md, SWIFTUI_PRINCIPLES.md

**Pattern:**
```swift
@State private var cachedItems: [Item] = []

.onChange(of: sourceData) { _, _ in
    cachedItems = buildHierarchy(from: sourceData)
}
```

**Avoids:** Rebuilding hierarchies on every view update

---

### 4. Task Cancellation ✅

**Documented in:** All files

**Pattern:**
```swift
.task {
    await withTaskGroup(of: Void.self) { group in
        group.addTask {
            guard !Task.isCancelled else { return }
            await loadData()
        }
    }
}
```

**Avoids:** Memory leaks from orphaned tasks

---

### 5. View Composition ✅

**Documented in:** All files

**Guidelines:**
- View files < 300 lines
- Use `@ViewBuilder` on computed views
- Extract to separate files or computed properties
- Split large modifier chains into ViewModifier structs

---

### 6. Logging ✅

**Documented in:** All files

**Pattern:**
```swift
import OSLog

extension Logger {
    static let ui = Logger(subsystem: "ca.tubb.Fichero", category: "ui")
}

Logger.ui.info("Event occurred")
```

**Replaces:** NSLog, print

---

### 7. Thread Safety ✅

**Documented in:** All files

**Pattern:**
```swift
@MainActor
func updateUI() {
    // Swift ensures main thread
}
```

**Replaces:** Manual `DispatchQueue.main.async`

---

### 8. Dependency Injection ✅

**Documented in:** All files

**Pattern:**
```swift
// App level
@StateObject private var documentStore = DocumentStore()

// Child views
@EnvironmentObject var documentStore: DocumentStore
```

**Anti-pattern:** Creating services in views

---

## Code Review Checklist

**Added to:** SWIFTUI_PRINCIPLES.md

Before committing Swift code, verify:

- [ ] ✅ No AppKit usage (except where absolutely necessary)
- [ ] ✅ Using @FocusedValue instead of NotificationCenter
- [ ] ✅ Expensive computations are cached
- [ ] ✅ Tasks handle cancellation
- [ ] ✅ Using @ViewBuilder on computed view properties
- [ ] ✅ View files < 300 lines
- [ ] ✅ Using OSLog instead of NSLog/print
- [ ] ✅ Services injected via @EnvironmentObject
- [ ] ✅ Using @MainActor for UI updates
- [ ] ✅ No memory leaks from uncancelled tasks

---

## Anti-Patterns Documented

**Documented in:** SWIFTUI_PRINCIPLES.md

### 1. ❌ NotificationCenter for App Logic
- **Problem:** Breaks declarative data flow
- **Solution:** Use @FocusedValue

### 2. ❌ Manual Thread Dispatching
- **Problem:** Verbose, error-prone
- **Solution:** Use @MainActor

### 3. ❌ Creating Service Instances in Views
- **Problem:** Recreated on every update
- **Solution:** Use @EnvironmentObject

### 4. ❌ Rebuilding Hierarchies on Every Update
- **Problem:** Performance degradation
- **Solution:** Cache with @State + .onChange

### 5. ❌ Ignoring Task Cancellation
- **Problem:** Memory leaks
- **Solution:** Check Task.isCancelled

---

## Documentation Structure

```
fichero/
├── CLAUDE.md                                    # ✅ Updated - Root guide
├── ai/
│   └── contexts/
│       └── frontend/
│           ├── development_standards.md         # ✅ Updated - Standards
│           ├── SWIFTUI_PRINCIPLES.md            # ✅ NEW - Comprehensive guide
│           ├── overview.md                      # (Unchanged - still valid)
│           ├── key_files.md                     # (Unchanged - still valid)
│           └── workflow_checklist.md            # (Unchanged - still valid)
└── docs/
    ├── SWIFTUI_CODE_REVIEW.md                   # ✅ Created earlier - Detailed analysis
    ├── DRAG_DROP_CODE_REVIEW.md                 # ✅ Created earlier - Drag & drop patterns
    └── P0_FIXES_SUMMARY.md                      # ✅ Created earlier - Implemented fixes
```

---

## Key Messages Emphasized

### 1. **100% SwiftUI - NO AppKit**
- Repeated in CLAUDE.md, development_standards.md, SWIFTUI_PRINCIPLES.md
- Clear prohibition with exceptions process

### 2. **Use MCP Tools BEFORE Custom Solutions**
- Sosumi for Apple documentation
- Ref for Swift language reference
- Decision matrix for when to use each

### 3. **Follow P0 SwiftUI Patterns**
- @FocusedValue (not NotificationCenter)
- Cache computations (not rebuild every update)
- Handle cancellation (not leak tasks)
- @MainActor (not DispatchQueue.main)
- OSLog (not NSLog/print)

### 4. **Code Quality Standards**
- View files < 300 lines
- Use @ViewBuilder
- Inject services via @EnvironmentObject
- SwiftLint required

---

## For Future Developers

**Start Here:**
1. **CLAUDE.md** - Project overview and quick reference
2. **ai/contexts/frontend/SWIFTUI_PRINCIPLES.md** - Mandatory SwiftUI patterns
3. **SWIFTUI_CODE_REVIEW.md** - Detailed anti-pattern analysis

**When Writing Swift:**
1. Check Sosumi MCP for proper SwiftUI API
2. Follow patterns in SWIFTUI_PRINCIPLES.md
3. Run SwiftLint before committing
4. Use code review checklist

**When Stuck:**
1. Search Sosumi: `searchAppleDocumentation("your question")`
2. Search Ref: `searchDocumentation("Swift feature")`
3. Check SWIFTUI_PRINCIPLES.md for examples
4. Review SWIFTUI_CODE_REVIEW.md for anti-patterns

---

## Summary

✅ **All frontend documentation updated** to enforce SwiftUI-only development
✅ **MCP tools documented** with practical examples (Sosumi, Ref)
✅ **Comprehensive guide created** (SWIFTUI_PRINCIPLES.md)
✅ **Anti-patterns catalogued** with before/after examples
✅ **Code review checklist** added for all commits

**The message is clear:** Fichero is 100% SwiftUI. Check Sosumi/Ref MCP before implementing custom solutions. Follow the mandatory patterns in SWIFTUI_PRINCIPLES.md.
