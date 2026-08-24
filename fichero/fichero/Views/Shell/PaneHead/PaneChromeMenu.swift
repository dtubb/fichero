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
                    // ADDITIONS only (Daniel, 2026-08-23): the "+" never
                    // removes a split — the pane's X collapses it. A row
                    // shows only while its toggle ADDS: thirds are a
                    // single-axis affair, so a 2×2 grid offers neither.
                    let grid = actions.hasVertical && actions.hasHorizontal
                    if actions.verticalCount == 1 || (actions.verticalCount == 2 && !grid) {
                        Button {
                            actions.onToggleVertical()
                        } label: {
                            Label(
                                actions.hasVertical ? "Add Third Vertical Pane" : "Split Vertical",
                                systemImage: ToolbarSymbols.splitVertical
                            )
                        }
                    }
                    if actions.horizontalCount == 1 || (actions.horizontalCount == 2 && !grid) {
                        Button {
                            actions.onToggleHorizontal()
                        } label: {
                            Label(
                                actions.hasHorizontal ? "Add Third Horizontal Pane" : "Split Horizontal",
                                systemImage: ToolbarSymbols.splitHorizontal
                            )
                        }
                    }
                }
            } label: {
                Image(systemName: isPinned?.wrappedValue == true ? "pin.fill" : "plus")
                    .foregroundStyle(isPinned?.wrappedValue == true ? Color.accentColor : Color.secondary)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Pin or split this pane")
            .accessibilityLabel("Pane options")
        }
    }
}
