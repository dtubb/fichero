import SwiftUI

/// The shared pane-head chrome controls (Daniel, 2026-08-23: "share code for
/// the other ones so it's consistent across them all"): ONE "+" menu with the
/// split options, and beside it a PIN MENU — pin has its own icon, and being
/// a menu leaves room for "pin to a library" style scopes to join.
///
/// A pane adopts by passing what it actually has: no split actions → no "+"
/// control; no pin binding → no pin control.
struct PaneChromeMenu: View {
    var splitActions: SplitAxisActions?
    var isPinned: Binding<Bool>?
    /// What pinning means for THIS pane, for the row title/help.
    var pinLabel: String = "Pin to Current Document"
    var unpinLabel: String = "Unpin — Follow Selection"

    var body: some View {
        if let actions = splitActions {
            // Named by the AXIS of the divider (Daniel, 2026-08-23): "Split
            // Horizontal" / "Split Vertical", not left/right prose.
            Menu {
                Button(
                    actions.hasVertical
                        ? (actions.paneCount == 3 ? "Remove Vertical Split" : "Add Third Vertical Pane")
                        : "Split Vertical"
                ) { actions.onToggleVertical() }
                Button(
                    actions.hasHorizontal
                        ? (actions.paneCount == 3 ? "Remove Horizontal Split" : "Add Third Horizontal Pane")
                        : "Split Horizontal"
                ) { actions.onToggleHorizontal() }
            } label: {
                Image(systemName: "plus")
                    .foregroundStyle(.secondary)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Split this pane")
            .accessibilityLabel("Split this pane")
        }
        if let isPinned {
            if splitActions != nil {
                Divider().frame(height: PaneHeadMetrics.dividerHeight)
            }
            Menu {
                Button {
                    isPinned.wrappedValue.toggle()
                } label: {
                    Label(
                        isPinned.wrappedValue ? unpinLabel : pinLabel,
                        systemImage: isPinned.wrappedValue ? "pin.slash" : "pin"
                    )
                }
                // ponytail: "Pin to Library…" joins here when pane-per-library
                // scoping exists — the menu shape is why pin is a menu.
            } label: {
                Image(systemName: isPinned.wrappedValue ? "pin.fill" : "pin")
                    .foregroundStyle(isPinned.wrappedValue ? Color.accentColor : Color.secondary)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help(isPinned.wrappedValue ? "Pinned — click for options" : "Pin this pane")
            .accessibilityLabel("Pin options")
        }
    }
}
