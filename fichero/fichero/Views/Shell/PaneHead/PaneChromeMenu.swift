import SwiftUI

/// The pane head's SPLIT control (Daniel, 2026-08-23: the "+" that lets us
/// "split it vertical, horizontal").
///
/// It carried the pin row too until 2026-09-02, when Daniel reported that
/// with splits open "there is no way to pin a pane to what it currently
/// shows": pinning is a MODE the pane is in, and a mode needs a control that
/// shows its state closed. The pin is now a one-click toggle in `PaneHead`
/// beside this menu; this stays the additive split menu it is named for.
///
/// Renders from what the pane actually has — split actions arrive via the
/// head's environment; with none, nothing renders.
struct PaneChromeMenu: View {
    var splitActions: SplitAxisActions?

    var body: some View {
        if splitActions != nil {
            Menu {
                if let actions = splitActions {
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
                Image(systemName: "plus")
                    .foregroundStyle(Color.secondary)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Split this pane")
            .accessibilityLabel("Split this pane")
        }
    }
}
