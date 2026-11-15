import SwiftUI

// The pane's bottom bar, its More menu and its status line, split out of ActivityPaneView.swift (SwiftLint's size limits).

extension ActivityPaneView {
    /// The pane's one bottom bar, the app's (`activity.pane.bottom-bar-like-every-pane`, #6588): the Filter field with what the
    /// list shows in its menu, and the status figures. The columns are chosen from a column header's menu, their widths kept
    /// (`activity.pane.columns-from-the-header`, decision 35).
    var bottomBar: some View {
        PaneFilterBar(placement: .bottom) {
            PaneFilterField(text: Binding(get: { prefs.filter }, set: { value in update { $0.filter = value } }),
                            prompt: "Filter: model: Kraken state: failed", accessibilityID: "activity.filter") {
                Toggle("Show Archived", isOn: $showArchived)
                Divider()
                Button("Failed") { update { $0.filter = "state: failed" } }
                Button("Today") { update { $0.filter = "date: today" } }
                Button("Started Automatically") { update { $0.filter = "started by: automatic" } }
            }
            .frame(maxWidth: 360)
            Spacer(minLength: 8)
            // The window's figures are its bottom panel's; the bar keeps the notice there, the whole line in a main window's pane.
            Text((showsHead ? [statusBarText, notice] : [notice]).compactMap { $0 }.joined(separator: " · "))
                .font(.caption).foregroundStyle(.secondary).monospacedDigit().lineLimit(1)
                .accessibilityIdentifier("activity.statusbar")
            if showsHead { moreMenu }
        }
    }

    /// The More menu: Show Archived, Archive Finished… and Archive Failed (`activity.window.toolbar-verbs`), the window's
    /// toolbar's, and the bottom bar's in a main window's pane.
    var moreMenu: some View {
        Menu {
            Toggle("Show Archived", isOn: $showArchived)
            Button("Archive Finished…") { confirmingArchiveFinished = true }
            Button("Archive Failed") { Task { await archiveFailed() } }
        } label: {
            Label("More", systemImage: "ellipsis.circle")
        }
        .help("Show Archived, Archive Finished…, Archive Failed")
        .accessibilityIdentifier("activity.more")
    }

    /// "3 running · 12 waiting · $3.20 today", Finder style, and "Automatic work paused" while it is.
    var statusBarText: String {
        let rows = allRows
        let today = rows.filter { row in (row.started ?? row.ended).map { Calendar.current.isDateInToday($0) } ?? row.phase.isLive }
        let spent = today.compactMap(\.costUsd).reduce(0, +)
        let counts = ActivityTrail.statusBar(running: rows.filter { $0.phase == .running }.count,
                                             waiting: rows.filter { $0.phase == .waiting }.count,
                                             spentTodayUsd: spent > 0 ? spent : nil)
        let paused = libraries.contains { $0.activityStore.backgroundMode == .paused }
        return paused ? counts + " · Automatic work paused" : counts
    }
}
