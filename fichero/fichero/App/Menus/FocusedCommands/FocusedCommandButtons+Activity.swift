import SwiftUI

// MARK: - Activity's Stop and Read Again in the menu bar (#5652 slice 3, `menus.context-matches-bar`)

/// What one Activity row offers: Stop while it runs or waits, and the run's own "read again" offer once
/// it has ended (`ActivityMonitorRow.readAgainLabel`). Made by `ActivityMonitorWindow.runMenuTarget(for:)`
/// for the row's own buttons, its context menu and the menu bar alike, so all three call the same
/// closures.
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

/// Stop, as ONE item: the Activity row's own button (icon only), its context menu and Project › Activity
/// all render this, so they never disagree (`FindDocumentsMenuItem`'s pattern).
struct ActivityStopMenuItem: View {
    let target: ActivityRunMenuTarget?

    var body: some View {
        Button {
            target?.stop()
        } label: {
            Label(ActivityMonitorRow.Control.stop.label, systemImage: ActivityMonitorRow.Control.stop.systemImage)
        }
        .disabled(FocusedActivityRunButtons.stopDisabledReason(target) != nil)
    }
}

/// Read Again, as ONE item: the run's own offer ("Read the 3 pages that failed") on the row's button, its
/// context menu and Project › Activity; "Read Again" when the run offers nothing.
struct ActivityReadAgainMenuItem: View {
    let target: ActivityRunMenuTarget?

    var body: some View {
        Button {
            target?.readAgain()
        } label: {
            Label(FocusedActivityRunButtons.readAgainTitle(target), systemImage: "arrow.clockwise")
        }
        .disabled(FocusedActivityRunButtons.readAgainDisabledReason(target) != nil)
    }
}

/// Project › Activity › Stop and Read Again, on the Activity window's selected row. Each is disabled
/// with its reason under it when it cannot act (the Segment menu's pattern). No chords: ⌘. is the
/// system's cancel, and neither is a muscle-memory verb.
struct FocusedActivityRunButtons: View {
    @FocusedValue(\.activityRun) private var target

    var body: some View {
        ActivityStopMenuItem(target: target)
        if let reason = Self.stopDisabledReason(target) {
            Text(reason)
        }
        ActivityReadAgainMenuItem(target: target)
        // With no run selected, the one reason under Stop says so for both.
        if target != nil, let reason = Self.readAgainDisabledReason(target) {
            Text(reason)
        }
    }

    static var noRunSelected: String { "Select a run in the Activity window" }

    /// Why Stop cannot act, or nil when it can.
    static func stopDisabledReason(_ target: ActivityRunMenuTarget?) -> String? {
        guard let target else { return noRunSelected }
        return target.canStop ? nil : "Only a run that is running or waiting can be stopped"
    }

    /// Why Read Again cannot act, or nil when it can.
    static func readAgainDisabledReason(_ target: ActivityRunMenuTarget?) -> String? {
        guard let target else { return noRunSelected }
        return target.readAgainLabel == nil ? "Only an ended run with pages to read again offers this" : nil
    }

    /// The run's own offer when it has one, else the verb.
    static func readAgainTitle(_ target: ActivityRunMenuTarget?) -> String {
        target?.readAgainLabel ?? "Read Again"
    }
}
