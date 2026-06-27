# Frontend Development Workflow Checklist

**Last Updated**: December 31, 2025
**For**: Fichero macOS App Development

> **Updated 2026-06-06:** several process references below are stale — read with
> these corrections:
> - **Tasks are tracked in GitHub Issues + Milestones**, not `docs/agent-workflow/TODO.md`
>   (retired). Ignore the "check / update TODO.md" steps.
> - **Branch discipline**: commit milestone work directly to the milestone branch
>   (e.g. `main`); do **not** create per-task `feature-branch-name` branches and do
>   not `git pull origin main` into your work — see `AGENTS.md` → "Rules I Don't Break".
> - **AppKit**: "100% SwiftUI" is aspirational. SwiftUI-first with ~8 sanctioned
>   `NSViewRepresentable` bridges (PDFKit, magnifier, text editors, …). The
>   `APPKIT_FINAL_AUDIT.md` referenced below has been retired — see
>   `docs/architecture/swiftui/development_standards.md`.
> - **New `.swift` files must be registered** with `ruby scripts/add-swift-file.rb <path>`
>   (the main target uses traditional PBX refs); the build gate is `bash scripts/verify_all.sh`.
> - Prefer the **Xcode MCP** build/test tools over the raw `xcodebuild` invocations shown here.

---

## Daily Development Workflow

### 1. Start Development Session

**Prerequisites**:
```bash
# [ ] Start Python backend (REQUIRED)
cd "$(git rev-parse --show-toplevel)"
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765

# [ ] Open Xcode project
open Fichero/Fichero.xcodeproj

# [ ] Pull latest changes
git pull origin main
```

**Check Status**:
- [ ] Backend running on port 8765 (http://localhost:8765/docs)
- [ ] No merge conflicts
- [ ] Latest code from main branch

---

### 2. Before Writing Code

**Planning**:
- [ ] Understand the requirement/bug
- [ ] Check `docs/agent-workflow/TODO.md` for task details
- [ ] Read relevant context files (`key_files.md`, `SWIFTUI_PRINCIPLES.md`)
- [ ] Identify affected files (use `key_files.md`)
- [ ] Check if files need splitting (> 400 lines?)

**Research**:
- [ ] Check Sosumi MCP for SwiftUI patterns
- [ ] Check Ref MCP for Swift language features
- [ ] Review sample code in `/sample_code` directory
- [ ] Review similar existing implementations

---

## New View Implementation

### Planning (10-15 min)
- [ ] Sketch the view hierarchy on paper
- [ ] Identify state needed (`@State`, `@Observable`, `@EnvironmentObject`)
- [ ] Plan API endpoints needed
- [ ] Check if view can reuse existing components
- [ ] Estimate file size (target < 400 lines)

### Implementation

**File Creation**:
- [ ] Create file in correct directory (`Views/FeatureName/`)
- [ ] Use standard file template:
  ```swift
  import SwiftUI
  import OSLog

  private let logger = Logger(subsystem: "com.tubb.Fichero", category: "FileName")

  struct MyView: View {
      // MARK: - Properties
      // MARK: - Body
      // MARK: - Subviews
      // MARK: - Actions
  }

  #Preview { MyView() }
  ```

**State Management**:
- [ ] Use `@State` for local view state
- [ ] Use `@StateObject` for view model ownership
- [ ] Use `@EnvironmentObject` for shared services
- [ ] Use `@Observable` for iOS 17+ view models
- [ ] NEVER create services in view body

**SwiftUI Compliance**:
- [ ] 100% SwiftUI (NO AppKit unless unavoidable)
- [ ] Use `@FocusedValue` for menu commands (NO NotificationCenter)
- [ ] Use `@ViewBuilder` for computed views
- [ ] Cache expensive computations
- [ ] Handle task cancellation in `.task {}` blocks

**Swift 6 Concurrency**:
- [ ] Mark UI classes with `@MainActor`
- [ ] Use `Task { @MainActor in ... }` for UI updates from background
- [ ] Check `Task.isCancelled` in all `.task {}` blocks
- [ ] No `DispatchQueue` in `@MainActor` classes
- [ ] Make thread-safe classes conform to `Sendable`

**Code Quality**:
- [ ] Descriptive variable names (no `x`, `y`, `i`)
- [ ] Functions < 50 lines
- [ ] File < 400 lines (if larger, split immediately)
- [ ] Use OSLog (not NSLog/print)
- [ ] Add `#Preview` for visual testing

### Testing
- [ ] Test in Xcode preview (⌘⌥↩)
- [ ] Test with sample data
- [ ] Test loading states
- [ ] Test error states
- [ ] Test with no backend connection
- [ ] Test keyboard shortcuts
- [ ] Test accessibility (VoiceOver if possible)

---

## Modifying Existing Code

### Before Editing
- [ ] Read the entire file first
- [ ] Understand current architecture
- [ ] Check for existing patterns to follow
- [ ] Note file size (will edit push it over 400 lines?)

### Making Changes
- [ ] Keep changes minimal and focused
- [ ] Don't refactor while fixing bugs
- [ ] Don't add "improvements" beyond the task
- [ ] Maintain existing code style
- [ ] Update comments if logic changes

### Swift 6 Checks
- [ ] No new concurrency warnings introduced
- [ ] Proper actor isolation maintained
- [ ] Task cancellation still handled
- [ ] No `DispatchQueue` added to `@MainActor` classes

---

## Before Committing

### Code Quality Checks

**Run SwiftLint** (MANDATORY):
```bash
cd Fichero
swiftlint
```
**Expected**: Zero errors, warnings are acceptable for TODOs

**Build Project** (MANDATORY):
```bash
xcodebuild -project Fichero.xcodeproj -scheme Fichero -configuration Debug build
```
**Expected**: `** BUILD SUCCEEDED **` with no Swift errors

**Check for Violations**:
- [ ] No files > 400 lines (recommended limit)
- [ ] No files > 1,000 lines (hard limit - MUST split)
- [ ] No functions > 50 lines
- [ ] No cyclomatic complexity > 10
- [ ] No identifier names like `x`, `y`, `i`, `a`, `b`
- [ ] No line lengths > 120 characters

### Swift 6 Verification
- [ ] No concurrency warnings in Xcode
- [ ] All `.task {}` blocks check cancellation
- [ ] UI updates use `@MainActor` (not DispatchQueue.main)
- [ ] Thread-safe types are `Sendable`

### SwiftUI Verification
- [ ] No AppKit except in justified files (see `APPKIT_FINAL_AUDIT.md`)
- [ ] No NotificationCenter for app logic
- [ ] Using @FocusedValue for menu commands
- [ ] All views have `#Preview`

### Testing
- [ ] Manual testing in Xcode (⌘R)
- [ ] Test with backend running
- [ ] Test without backend (connection error handling)
- [ ] Preview canvas works (⌘⌥↩)

---

## Git Workflow

### Committing
```bash
# [ ] Check status
git status

# [ ] Review changes
git diff

# [ ] Stage specific files (not `git add .`)
git add Fichero/Fichero/Views/MyView.swift
git add Fichero/Fichero/Models/MyModel.swift

# [ ] Commit with descriptive message
git commit -m "Add MyView for feature X

- Implement SwiftUI view with @Observable state
- Add API integration for endpoint Y
- Include error handling and loading states
- All Swift 6 concurrency checks pass

🤖 Generated with Claude Code
Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

**Good Commit Messages**:
- Start with verb: "Add", "Fix", "Update", "Refactor"
- Explain WHY, not just WHAT
- Reference issue/task numbers if applicable
- Include compliance notes (Swift 6, SwiftLint, etc.)

**Bad Commit Messages**:
- "Update file" (too vague)
- "WIP" (not descriptive)
- "asdf" (meaningless)

### Pushing
```bash
# [ ] Pull latest first
git pull origin main

# [ ] Resolve any conflicts
# ... fix conflicts ...

# [ ] Push to remote
git push origin feature-branch-name
```

---

## File Size Management

### When a File Reaches 400 Lines

**Immediate Action Required**:
1. Stop adding to the file
2. Plan the split (by component, responsibility, or feature)
3. Create new files with extracted code
4. Update imports and references
5. Add new files to Xcode project
6. Test thoroughly
7. Commit with message: "Refactor MyView - split into components"

**Splitting Strategies**:
- **By Component**: Extract toolbar, sidebar, inspector into separate files
- **By Responsibility**: Extract data fetching, formatting, validation
- **By Feature**: Extract search, filter, sort into separate files

**Example**: `EditorView.swift` (1,981 lines) →
- `EditorView.swift` (< 200 lines)
- `EditorToolbar.swift`
- `EditorCanvas.swift`
- `EditorInspector.swift`
- `EditorHelpers.swift`

---

## Common Tasks Quick Reference

### Adding a New Feature
1. Read `docs/agent-workflow/TODO.md` for task details
2. Check `key_files.md` for affected files
3. Review `SWIFTUI_PRINCIPLES.md` for patterns
4. Implement following workflow above
5. Run SwiftLint and build
6. Test manually
7. Commit with descriptive message
8. Update `docs/agent-workflow/TODO.md` task status

### Fixing a Bug
1. Reproduce the bug
2. Add logging if needed
3. Identify root cause
4. Make minimal fix
5. Test fix works
6. Test related functionality (no regressions)
7. Run SwiftLint and build
8. Commit with bug description

### Refactoring
1. Ensure tests pass first
2. Make incremental changes
3. Test after each change
4. Don't change behavior
5. Run SwiftLint and build
6. Commit each logical step

### Adding API Integration
1. Review backend API docs (`/api/docs`)
2. Add endpoint to `APIClient.swift` or relevant service
3. Create/update data models
4. Add error handling
5. Add loading states
6. Test with backend running
7. Test without backend (error handling)

---

## Troubleshooting

### Build Fails
```bash
# Clean build folder
xcodebuild clean -project Fichero.xcodeproj -scheme Fichero

# Rebuild
xcodebuild -project Fichero.xcodeproj -scheme Fichero build
```

### SwiftLint Errors
```bash
# Auto-fix formatting issues
swiftlint --fix --format

# Check specific file
swiftlint lint --path Fichero/Fichero/Views/MyView.swift
```

### Concurrency Warnings
- Check if class needs `@MainActor`
- Use `Task { @MainActor in ... }` for UI updates
- Ensure thread-safe types conform to `Sendable`
- Remove `DispatchQueue` from `@MainActor` classes

### Preview Not Working
- Ensure all dependencies are injected
- Provide sample data in preview
- Check for async operations in init
- Restart Xcode if canvas is stuck

---

## Performance Checks

### Before Committing Large Changes
- [ ] Profile with Instruments (Time Profiler)
- [ ] Check for memory leaks (Leaks instrument)
- [ ] Monitor view updates (Debug Navigator)
- [ ] Test with large datasets
- [ ] Test scrolling performance

### Optimization Checklist
- [ ] Cache expensive computations
- [ ] Lazy load data when possible
- [ ] Use `LazyVStack`/`LazyHStack` for long lists
- [ ] Minimize view updates
- [ ] Profile before and after changes

---

## Documentation Updates

### When to Update Docs
- [ ] Added new major feature → Update `overview.md`
- [ ] Added new file/module → Update `key_files.md`
- [ ] Changed architecture → Update `overview.md`
- [ ] New best practice → Update `SWIFTUI_PRINCIPLES.md`
- [ ] Changed workflow → Update this file

### Doc Locations
- `docs/architecture/swiftui/overview.md` - High-level architecture
- `docs/architecture/swiftui/key_files.md` - File organization
- `docs/architecture/swiftui/SWIFTUI_PRINCIPLES.md` - Code patterns
- `docs/architecture/swiftui/development_standards.md` - Standards and guidelines
- `docs/architecture/swiftui/workflow_checklist.md` - This file

---

## Resources

### Quick Links
- Backend API: http://localhost:8765/docs
- Sample Code: `fichero/sample_code`
- Frontend Docs: `docs/architecture/swiftui/`
- TODO List: GitHub Issues + Milestones (the source of truth; the old `docs/agent-workflow/TODO.md` is retired)

### MCP Tools
- **Sosumi**: `searchAppleDocumentation("swiftui drag drop")`
- **Ref**: `searchDocumentation("Swift @Observable")`
- **Filesystem**: Read/write files in project
- **Memory**: Store project knowledge

### When Stuck
1. Check Sosumi for SwiftUI equivalent
2. Check Ref for Swift language features
3. Review similar code in project
4. Read `SWIFTUI_PRINCIPLES.md`
5. Ask for clarification

---

## Summary

**Daily Checklist**:
1. ✅ Start backend
2. ✅ Write code following SWIFTUI_PRINCIPLES.md
3. ✅ Keep files < 400 lines
4. ✅ Run SwiftLint (zero errors)
5. ✅ Build succeeds
6. ✅ Test manually
7. ✅ Commit with good message

**Quality Gates**:
- File size < 400 lines
- SwiftLint passes
- Build succeeds
- No Swift 6 concurrency warnings
- Manual testing passes
- Preview works

**Remember**:
- 100% SwiftUI (NO AppKit unless unavoidable)
- Swift 6 compliant (@MainActor, Sendable, Task cancellation)
- Small, focused files (< 400 lines)
- Descriptive names (no `x`, `y`, `i`)
- OSLog for logging (no NSLog/print)
