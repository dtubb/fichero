import SwiftUI

/// The ids a sidebar row's context-menu verb acts on (#6528), Finder-style: a right-click inside a multi-selection acts
/// on the whole selection (in selection order); a right-click outside it, or with nothing else selected, acts on the
/// clicked row alone. The clicked row is the row under the pointer, never its parent.
func sidebarContextTargetIds(clicked: String, selection: [String]) -> [String] {
    guard selection.count > 1, selection.contains(clicked) else { return [clicked] }
    return selection
}

/// Whether an expandable row's whole group carries its context menu. An expanded group holds its child rows inside it,
/// and SwiftUI hands a right-click on any of them to the OUTERMOST menu, so the group's menu would act on the ancestor
/// (#6528). While it holds no child rows the group carries the menu, which keeps the chevron and indent strip live
/// (#571); expanded, only the row's own label does.
func sidebarGroupCarriesContextMenu(_ item: SidebarItem, isExpanded: Bool) -> Bool {
    !sidebarBuildsChildRows(item, isExpanded: isExpanded)
}

/// Whether a root row's fallback tap (the ⇧/⌘ click path) acts (#6534). The gesture sits on the whole row, and an
/// expanded row's child rows are inside it, so a click on a child also reached the PARENT's handler: a shift-click
/// added the parent to the range, and a plain click selected the parent instead of the child. An expanded row's
/// handler does nothing; the List's own selection handles its children.
func sidebarFallbackTapActs(_ item: SidebarItem, _ expanded: Bool) -> Bool {
    !sidebarBuildsChildRows(item, isExpanded: expanded)
}

/// Whether an expanded row's LABEL takes the fallback tap: exactly when the whole-row handler above stands down. Its
/// name sits over the drag machinery like any other row's, so with neither handler a click on an expanded folder's
/// name selected nothing (only the strip to its left did). The label holds none of the child rows, so a click on a
/// child still never reaches the parent. One of the two acts for any row, never both, so a ⌘-click toggles once.
func sidebarExpandedLabelTapActs(_ item: SidebarItem, _ expanded: Bool) -> Bool {
    sidebarBuildsChildRows(item, isExpanded: expanded)
}

#if os(macOS)
/// The modifiers of a sidebar click, as Finder reads them: Shift is a continuous range, Command adds or removes the one
/// clicked row. Option has no selection meaning in Finder, and none here (#6534).
func sidebarClickModifiers() -> (shift: Bool, command: Bool) {
    let flags = NSEvent.modifierFlags
    return (flags.contains(.shift), flags.contains(.command))
}
#endif

/// Puts `menu` on the content only when `carries` is true.
struct SidebarGroupContextMenu<MenuItems: View>: ViewModifier {
    let carries: Bool
    @ViewBuilder let menu: () -> MenuItems

    @ViewBuilder
    func body(content: Content) -> some View {
        if carries {
            content.contextMenu { menu() }
        } else {
            content
        }
    }
}

#Preview("Sidebar context targets") {
    let selection = ["a", "b", "c"]
    VStack(alignment: .leading, spacing: 6) {
        Text("Right-click b in {a, b, c}: \(sidebarContextTargetIds(clicked: "b", selection: selection).joined(separator: ", "))")
        Text("Right-click z outside it: \(sidebarContextTargetIds(clicked: "z", selection: selection).joined(separator: ", "))")
    }
    .padding()
}
