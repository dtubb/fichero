import SwiftUI

// MARK: - Activity's Stop and Read Again in the menu bar (#5652 slice 3, `menus.context-matches-bar`)

/// What the Activity window's one selected row offers the menu bar: Stop while it runs or waits, and
/// the run's own "read again" offer once it has ended (`ActivityMonitorRow.readAgainLabel`). Published
/// by `ActivityMonitorWindow`; the same row's buttons and context menu call the same closures.
struct ActivityRunMenuTarget: Equatable {
    let rowId: String
    let rowName: String
    let canStop: Bool
    /// "Read the 3 pages that failed", or nil when the row offers nothing to read again.
    let readAgainLabel: String?
    let stop: @MainActor () -> Void
    let readAgain: @MainActor () -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.rowId == rhs.rowId && lhs.canStop == rhs.canStop && lhs.readAgainLabel == rhs.readAgainLabel
    }
}

extension FocusedValues {
    @Entry var activityRun: ActivityRunMenuTarget?
}

/// Project › Activity › Stop and Read Again, on the Activity window's selected row. Each is disabled
/// with its reason under it when it cannot act (the Segment menu's pattern). No chords: ⌘. is the
/// system's cancel, and neither is a muscle-memory verb.
struct FocusedActivityRunButtons: View {
    @FocusedValue(\.activityRun) private var target

    var body: some View {
        Button("Stop") { target?.stop() }
            .disabled(target?.canStop != true)
        if target == nil {
            Text("Select a run in the Activity window")
        } else if target?.canStop != true {
            Text("Only a run that is running or waiting can be stopped")
        }
        Button(target?.readAgainLabel ?? "Read Again") { target?.readAgain() }
            .disabled(target?.readAgainLabel == nil)
        if target != nil, target?.readAgainLabel == nil {
            Text("Only an ended run with pages to read again offers this")
        }
    }
}
