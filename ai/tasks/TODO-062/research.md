# TODO-062: Research - ID-Based Selection in SwiftUI List

## Question
Is ID-based selection the proper SwiftUI way for List selection?

## Answer: YES ✅

## Apple Documentation Confirms

### From List Initializer Documentation

```swift
init<Data, RowContent>(
    _ data: Binding<Data>,
    selection: Binding<SelectionValue?>?,
    @ViewBuilder rowContent: @escaping (Binding<Data.Element>) -> RowContent
) where Content == ForEach<...>, Data.Element : Identifiable
```

**Key Point:** The `SelectionValue` type can be **any type**, not just the item itself. Most commonly:
- `SelectionValue` = `Data.Element.ID` (the ID type - **recommended**)
- `SelectionValue` = `Data.Element` (the whole item - requires Hashable)

### From Apple Developer Forums

**[SwiftUI List selection](https://developer.apple.com/forums/thread/122140):**
> "When using List with selection where items conform to Identifiable, you don't need to specify an ID in the List initializer if your selection is of type `Item.ID`"

**[Selection Parameter in List](https://developer.apple.com/forums/thread/125382):**
> "The selection binding value must be an Optional. To use selection with objects (not just IDs), the object type must conform to both Identifiable and Hashable protocols."

**Key insight:** Using ID-based selection is simpler because:
- IDs are already Hashable (String, UUID, etc.)
- Items don't need Hashable conformance
- Selection persists across data rebuilds

### From SwiftUI Tutorials

**[Building lists and navigation](https://developer.apple.com/tutorials/swiftui/building-lists-and-navigation):**
Shows examples using ID-based selection for navigation.

## Current vs Proper Implementation

### Current (Problematic)
```swift
// ContentView
@State var selectedSidebarItem: SidebarItem?  // Whole struct

// SidebarView
List(selection: $selectedItem) {
    ForEach(items) { item in
        Row(item).tag(item)  // ❌ Tags with struct instance
    }
}
```

**Problem:** When `items` array rebuilds with new struct instances (even with same IDs), selection is lost because SwiftUI compares struct instances, not IDs.

### Proper (Apple's Way)
```swift
// ContentView
@State var selectedSidebarItemId: String?  // Just the ID!

// SidebarView
List(selection: $selectedItemId) {
    ForEach(items) { item in
        Row(item).tag(item.id)  // ✅ Tags with ID (String)
    }
}
```

**Benefits:**
- Selection persists across data rebuilds automatically
- No manual restoration needed
- SwiftUI compares IDs (stable) not struct instances (recreated)
- Simpler, more predictable behavior

## Deriving the Item from ID

When you need the actual item:

```swift
var selectedItem: SidebarItem? {
    guard let id = selectedItemId else { return nil }

    let allItems = libraryItems + searchItems + chatItems + workflowItems
    return findItemById(id, in: allItems)
}
```

## Conclusion

**ID-based selection IS the proper SwiftUI way.**

Apple's documentation and examples consistently show using `Item.ID` for selection bindings rather than the full item. This approach:
- Aligns with SwiftUI's value-type philosophy
- Works seamlessly with data updates
- Requires no manual intervention
- Is more performant (comparing IDs vs entire structs)

## Sources

- [init(_:selection:rowContent:) - Apple Documentation](https://developer.apple.com/documentation/swiftui/list/init(_:selection:rowcontent:)-1q8lq)
- [SwiftUI List selection - Apple Developer Forums](https://developer.apple.com/forums/thread/122140)
- [Selection Parameter in List - Apple Developer Forums](https://developer.apple.com/forums/thread/125382)
- [Building lists and navigation - SwiftUI Tutorial](https://developer.apple.com/tutorials/swiftui/building-lists-and-navigation)
