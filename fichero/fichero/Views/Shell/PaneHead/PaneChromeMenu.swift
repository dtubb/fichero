import SwiftUI

/// The ONE shared chrome control on every pane head's right (Daniel,
/// 2026-08-23, final form: "combine pin and the + so that the menu lets us
/// pin the current view, or split it vertical, horizontal"): a single menu
/// carrying pin-to-current-view and the split options.
///
/// Renders from what the pane actually has — split actions arrive via the
/// head's environment, pin via the pane's binding; with neither, nothing
/// renders. The closed control wears a filled pin while pinned so the state
/// stays readable.
struct PaneChromeMenu: View {
    var splitActions: SplitAxisActions?
    var isPinned: Binding<Bool>?
    var pinLabel: String = "Pin to Current View"
    var unpinLabel: String = "Unpin — Follow Selection"

    var body: some View {
        if splitActions != nil || isPinned != nil {
            Menu {
                if let isPinned {
                    Button {
                        isPinned.wrappedValue.toggle()
                    } label: {
                        Label(
                            isPinned.wrappedValue ? unpinLabel : pinLabel,
                            systemImage: isPinned.wrappedValue ? "pin.slash" : "pin"
                        )
                    }
                }
                if let actions = splitActions {
                    if isPinned != nil { Divider() }
                    // Named by the AXIS of the divider (Daniel, 2026-08-23).
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
                }
            } label: {
                Image(systemName: isPinned?.wrappedValue == true ? "pin.fill" : "plus")
                    .foregroundStyle(isPinned?.wrappedValue == true ? Color.accentColor : Color.secondary)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Pin or split this pane")
            .accessibilityLabel("Pane options")
        }
    }
}
