import SwiftUI

// MARK: - Activity's Stop and Read Again in the menu bar (#5652 slice 3, `menus.context-matches-bar`)

/// What one Activity row, or one stage's failed pages, offers: Stop while it runs or waits, and the
/// run's own "read again" offer once it has ended (`ActivityMonitorRow.readAgainLabel`). Made ONLY by
/// `make(…)` / `stage(…)`, whose closures are the one Stop (`ActivityStore.cancelJob`) and the one Read
/// Again (`ActivityStore.readPagesAgain`): the Activity row's buttons, its context menu, the menu bar,
/// the Activity details and the project window's run strip all act through them.
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

    /// A row's target. `report` gets the failure in words, or nil when the engine took it.
    static func make(
        rowId: String, rowName: String, canStop: Bool, jobId: String?, runThreadId: String?,
        readAgainLabel: String?, store: ActivityStore?, report: @escaping @MainActor (String?) -> Void
    ) -> Self {
        Self(
            rowId: rowId, rowName: rowName, canStop: canStop, readAgainLabel: readAgainLabel,
            stop: {
                guard let store, let jobId else { return }
                Task {
                    report(await stopJob(jobId: jobId, runThreadId: runThreadId, store: store)
                        .map { "Couldn't stop \(rowName): \($0)" })
                }
            },
            readAgain: {
                guard let store, let runThreadId else { return }
                Task {
                    report(await store.readPagesAgain(runThreadId: runThreadId)
                        .map { "Couldn't read the pages again: \($0)" })
                }
            }
        )
    }

    /// The one Stop (`ActivityStore.cancelJob`), for the Activity pane's verbs on several rows too; nil when the engine took it.
    static func stopJob(jobId: String, runThreadId: String?, store: ActivityStore) async -> String? {
        await store.cancelJob(jobId: jobId, runThreadId: runThreadId)
    }

    /// One stage's failed pages (the details' stage cards and summary, the project window's run strip):
    /// Read Again only, on that stage's thread.
    static func stage(
        threadId: String, offer: String, store: ActivityStore?, report: @escaping @MainActor (String?) -> Void
    ) -> Self {
        make(rowId: threadId, rowName: offer, canStop: false, jobId: nil, runThreadId: threadId,
             readAgainLabel: offer, store: store, report: report)
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

    nonisolated static var noRunSelected: String { "Select a run in the Activity window" }

    /// Why Stop cannot act, or nil when it can.
    nonisolated static func stopDisabledReason(_ target: ActivityRunMenuTarget?) -> String? {
        guard let target else { return noRunSelected }
        return target.canStop ? nil : "Only a run that is running or waiting can be stopped"
    }

    /// Why Read Again cannot act, or nil when it can.
    nonisolated static func readAgainDisabledReason(_ target: ActivityRunMenuTarget?) -> String? {
        guard let target else { return noRunSelected }
        return target.readAgainLabel == nil ? "Only an ended run with pages to read again offers this" : nil
    }

    /// The run's own offer when it has one, else the verb.
    nonisolated static func readAgainTitle(_ target: ActivityRunMenuTarget?) -> String {
        target?.readAgainLabel ?? "Read Again"
    }
}

/// Project › Activity's verbs on the focused Activity pane's selection (`activity.pane.commands-through-the-table`): the ONE
/// verb list (`ActivityPaneVerb`), each enabled by the Mail rule and disabled, never hidden, when no selected row allows it.
/// Stop is `FocusedActivityRunButtons`' one item. No chords: Delete is the table's own Delete key.
struct FocusedActivityVerbButtons: View {
    @FocusedValue(\.activityVerbs) private var target

    static let verbs: [ActivityPaneVerb] = [.pause, .resume, .retry, .archive, .putBack, .delete]

    var body: some View {
        ForEach(Self.verbs) { verb in
            Button(verb.title) { target?.perform(verb) }
                .disabled(!(target?.enabled.contains(verb) ?? false))
        }
    }
}

/// Project › Activity › Pause Automatic Work / Resume Automatic Work (`activity.pane.run-automatically-is-a-setting`): the
/// background lane's two verbs, on the front window's project, through the same engine action as the setting
/// (`ActivityStore.setBackgroundMode`). The one the mode does not offer is disabled, never hidden.
struct FocusedAutomaticWorkButtons: View {
    @FocusedValue(\.projectMenu) private var project

    var body: some View {
        let store = project?.library?.activityStore
        let offersPause = RunAutomaticallySetting.offersPause(store.map { ActivityModeIndicator(store: $0).mode })
        Button(RunAutomaticallySetting.pauseCommand) { set(.paused, on: store) }
            .disabled(offersPause != true)
        Button(RunAutomaticallySetting.resumeCommand) { set(.automatic, on: store) }
            .disabled(offersPause != false)
    }

    private func set(_ mode: ActivityMode, on store: ActivityStore?) {
        guard let store else { return }
        Task { _ = await store.setBackgroundMode(mode) }
    }
}

/// View › Activity ▸ Group by Run / Group by File and Show Archived (`activity.pane.commands-through-the-table`), on the
/// focused Activity pane: the same choices as its head's lens menu and its More menu. No chords.
struct FocusedActivityViewButtons: View {
    @FocusedValue(\.activityView) private var target

    var body: some View {
        ForEach(ActivityPane.Grouping.allCases) { grouping in
            Toggle("Group by \(grouping.title)", isOn: Binding(
                get: { target?.grouping == grouping },
                set: { isOn in if isOn { target?.setGrouping(grouping) } }
            ))
        }
        .disabled(target == nil)
        Divider()
        Toggle("Show Archived", isOn: Binding(
            get: { target?.showsArchived ?? false },
            set: { target?.setShowsArchived($0) }
        ))
        .disabled(target == nil)
    }
}
