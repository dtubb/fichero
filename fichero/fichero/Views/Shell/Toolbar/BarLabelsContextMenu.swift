import SwiftUI

/// Right-click either bar to show or hide its labels (Daniel, 2026-09-02) —
/// the gesture a Mac toolbar has always answered, on the two bars that hang
/// beneath it.
///
/// It is NOT a second setting. The entry writes the same flag
/// `ToolbarTextModeSync` bridges to the window toolbar's display mode, so
/// choosing Hide Labels here also turns the toolbar above to Icon Only, and
/// choosing Icon and Text up there brings both bars' labels back. Two doors,
/// one switch — a bar whose labels disagreed with the toolbar's would be the
/// clearest possible statement that they are unrelated, which is exactly
/// wrong.
struct BarLabelsContextMenu: View {
    let showsLabels: Bool
    /// nil when the host has not wired the setting — the menu then states the
    /// current mode without offering a change it cannot make.
    let onSetLabels: ((Bool) -> Void)?

    var body: some View {
        if let onSetLabels {
            Button(showsLabels ? "Hide Labels" : "Show Labels") {
                onSetLabels(!showsLabels)
            }
            .help(showsLabels
                  ? "Hide the labels here and in the window toolbar"
                  : "Show the labels here and in the window toolbar")
        }
    }
}
