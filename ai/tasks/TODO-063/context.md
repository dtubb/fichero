# TODO-063 Context

## Background

Fichero uses NavigationSplitView with 3 columns:
1. **Sidebar** (~250-300px) - Navigate, Search, Chat, Workflows, Activity
2. **Browser** (~400px) - Document list, search results
3. **Inspector** (~300px) - Document details, metadata

Currently the app opens too narrow, cutting off the sidebar.

## Related Files

- `Fichero/Fichero/FicheroApp.swift` - Main app entry point
- `Fichero/Fichero/Views/ContentView.swift` - 3-column layout

## SwiftUI Window Sizing

```swift
WindowGroup {
    ContentView()
}
.defaultSize(width: 1200, height: 800)
```

## Minimum Sizes

- Sidebar: 250px (for mode switching)
- Browser: 400px (for document list)
- Inspector: 300px (for metadata)
- **Total minimum**: 950px
- **Recommended**: 1200px

## Screen Compatibility

- 13" MacBook Pro: 1440x900 → 1200x800 fits comfortably
- 15" MacBook Pro: 1680x1050 → plenty of space
- External displays: even better

## SwiftUI Best Practices

- Use `.defaultSize()` on WindowGroup (not on views)
- System handles DPI scaling automatically
- NavigationSplitView handles column sizing
- Users can resize, but default should be usable

## Testing

To fully test:
1. Close app
2. Delete preferences: `defaults delete ca.tubb.Fichero`
3. Relaunch app
4. Verify layout

## References

- SwiftUI WindowGroup: https://developer.apple.com/documentation/swiftui/windowgroup
- NavigationSplitView: https://developer.apple.com/documentation/swiftui/navigationsplitview
