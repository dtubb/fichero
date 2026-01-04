# TODO-063: Increase Default Window Size

**Priority**: P1 (High - Quick Win)
**Category**: Frontend
**Estimated Time**: 1-2 hours
**Dependencies**: None

---

## Goal

Fix the app opening with a window that's too narrow, causing the sidebar to be cut off. Set a larger default window size so all UI elements are visible on launch.

---

## Implementation Steps

### 1. Find Window Configuration
- [ ] Locate FicheroApp.swift
- [ ] Find WindowGroup or scene configuration
- [ ] Identify where default size is set (or not set)

### 2. Set Default Window Size
- [ ] Add `.defaultSize(width:height:)` modifier to WindowGroup
- [ ] Set width to accommodate 3-column layout:
  - Sidebar: ~250-300px
  - Browser: ~400px minimum
  - Inspector: ~300px
  - **Recommended**: 1200x800
- [ ] Ensure size works on 13" MacBook Pro (1440x900 screen)

### 3. Test
- [ ] Close app completely
- [ ] Relaunch app
- [ ] Verify sidebar fully visible
- [ ] Verify all three columns visible without scrolling
- [ ] Check on different screen sizes if possible

### 4. Code Quality
- [ ] Run SwiftLint: `swiftlint lint --path Fichero/Fichero/`
- [ ] Build: `xcodebuild -project Fichero/Fichero.xcodeproj -scheme Fichero build`
- [ ] Verify no errors or warnings

---

## Expected Code Change

```swift
WindowGroup {
    ContentView()
        .environmentObject(documentStore)
}
.defaultSize(width: 1200, height: 800)
```

---

## Files to Modify

- `Fichero/Fichero/FicheroApp.swift`

**Lines Changed**: ~2-5 lines

---

## Success Criteria

- ✅ App opens with sidebar fully visible
- ✅ No horizontal scrolling required
- ✅ All three columns visible comfortably
- ✅ SwiftLint passes with zero errors
- ✅ Build succeeds

---

## Notes

- This is a pure SwiftUI change
- No backend involved
- Quick win to deliver immediate value
- Future enhancement: Save/restore window size per user preference
