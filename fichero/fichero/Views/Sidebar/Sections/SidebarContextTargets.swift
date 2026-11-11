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
