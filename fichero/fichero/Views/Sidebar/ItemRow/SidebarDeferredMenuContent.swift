import SwiftUI

/// Defers context-menu construction to menu-open time (#4544).
///
/// `.contextMenu { rowContextMenu }` evaluated the whole menu tree on EVERY
/// row render — `closure #1 in SidebarItemRow.rowContextMenu.getter` was 506
/// main-thread samples in aug4.trace, the single largest app-frame cost in
/// the profile. Apple's documentation for `contextMenu(menuItems:)` gives the
/// closure no laziness guarantee, and empirically SwiftUI calls it during row
/// update, not at menu display.
///
/// Wrapping the content in a child view changes what that eager call
/// produces: one cheap struct init capturing the closure. The expensive part
/// — resolving workflow targets, the selection set, delete targets — moves
/// into `body`, which SwiftUI evaluates only when it actually renders the
/// menu, i.e. when the user opens it.
///
/// This is also half of #4556 (first right-click shows an incomplete menu):
/// content is now resolved at OPEN time, after lazily-loaded stores have
/// had a chance to fill.
struct SidebarDeferredMenuContent<Content: View>: View {
    let content: () -> Content

    init(@ViewBuilder content: @escaping () -> Content) {
        self.content = content
    }

    var body: some View {
        content()
    }
}
