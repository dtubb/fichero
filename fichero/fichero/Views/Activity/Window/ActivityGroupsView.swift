import SwiftUI

/// The Activity window's list: NOW, UP NEXT and DONE TODAY, one row per run, one button per row (the one-bar design,
/// #5960: `activity.window.three-groups`, `activity.window.one-button`, `activity.window.row-subtitle`).
///
/// No table header and no empty-group prose: a group with nothing in it is not drawn. The stage bar, the page grid and
/// the opened run's new look are later slices (`activity.window.stage-bar`, `activity.window.page-grid`); a row's bar
/// here is the plain pages-done bar.
struct ActivityGroupsView: View {
    let groups: ActivityWindowGroups
    /// With work from several projects the project leads a row's name (`activity.window.project-prefix`).
    let showsProject: Bool
    let appeared: (ActivityMonitorRow) async -> Void
    let perform: (ActivityMonitorRow.OneButton, ActivityMonitorRow) -> Void
    let open: (ActivityMonitorRow) -> Void
    /// A recipe run's stage bar; empty for any other row.
    var stageSegments: (ActivityMonitorRow) -> [ActivityStageBar.Segment] = { _ in [] }
    let stopTarget: (ActivityMonitorRow) -> ActivityRunMenuTarget
    /// Clear Failed and Clear Finished, from the DONE TODAY heading (`activity.window.done-today`).
    let clearFailed: () -> Void
    let clearFinished: () -> Void
    /// Delete is a context-menu item (`activity.window.one-button`); only a run deletes.
    let delete: ([ActivityMonitorRow]) -> Void
    @AppStorage("activity.doneTodayExpanded") private var doneExpanded = false
    /// Finder-like: rows multi-select, and Delete (⌫ or the context menu) acts on all of them.
    @State private var selection: Set<ActivityMonitorRow.ID> = []

    private var allShown: [ActivityMonitorRow] { groups.now + groups.upNext + (doneExpanded ? groups.doneToday : []) }
    private func deletable(_ rows: [ActivityMonitorRow]) -> [ActivityMonitorRow] { rows.filter { $0.kind == .run && !$0.phase.isLive } }

    /// The one selected row's Stop / Read Again target, for Project › Activity in the menu bar (`FocusedActivityRunButtons`);
    /// nil with none or several selected, so those commands are disabled.
    private var selectedRunTarget: ActivityRunMenuTarget? {
        let rows = allShown.filter { selection.contains($0.id) }
        return rows.count == 1 ? rows.first.map(stopTarget) : nil
    }

    var body: some View {
        List(selection: $selection) {
            if !groups.now.isEmpty {
                Section("Now") { ForEach(groups.now) { rowView($0) } }
            }
            if !groups.upNext.isEmpty {
                Section("Up Next") { ForEach(groups.upNext) { rowView($0) } }
            }
            if !groups.doneToday.isEmpty {
                Section {
                    if doneExpanded { ForEach(groups.doneToday) { rowView($0) } }
                } header: {
                    HStack {
                        Button {
                            doneExpanded.toggle()
                        } label: {
                            Label("Done Today (\(groups.doneToday.count))",
                                  systemImage: doneExpanded ? "chevron.down" : "chevron.right")
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("activity.doneToday.toggle")
                        Spacer()
                        Menu("Clear") {
                            Button("Clear Failed", role: .destructive, action: clearFailed)
                            Button("Clear Finished…", role: .destructive, action: clearFinished)
                        }
                        .menuStyle(.borderlessButton)
                        .fixedSize()
                        .accessibilityIdentifier("activity.doneToday.clear")
                    }
                }
            }
        }
        .accessibilityIdentifier("activity.groups")
        .focusedSceneValue(\.activityRun, selectedRunTarget)
        // Selection-based, so a single click selects at once (a per-row double-tap gesture can hold it back) and a
        // double-click opens the run.
        .contextMenu(forSelectionType: ActivityMonitorRow.ID.self) { ids in
            let rows = allShown.filter { ids.contains($0.id) }
            if rows.count == 1, let row = rows.first {
                if row.controls.contains(.stop) { ActivityStopMenuItem(target: stopTarget(row)) }
                Button("Show Details") { open(row) }
            }
            let targets = deletable(rows)
            if !targets.isEmpty {
                Button(targets.count > 1 ? "Delete \(targets.count) Runs" : "Delete", role: .destructive) { delete(targets) }
            }
        } primaryAction: { ids in
            if ids.count == 1, let row = allShown.first(where: { ids.contains($0.id) }) { open(row) }
        }
        #if os(macOS)
        .onDeleteCommand { delete(deletable(allShown.filter { selection.contains($0.id) })) }
        #endif
    }

    private func rowView(_ row: ActivityMonitorRow) -> some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title(row)).lineLimit(1)
                let segments = stageSegments(row)
                if !segments.isEmpty {
                    ActivityStageBar(segments: segments)
                } else if row.total > 0, row.phase == .running || row.phase == .paused {
                    ProgressView(value: Double(row.done), total: Double(row.total))
                }
                Text(subtitle(row)).font(.caption).foregroundStyle(.secondary).lineLimit(2)
            }
            Spacer(minLength: 8)
            if !row.costText.isEmpty, row.costUsd != nil {
                Text(row.costText).font(.caption).foregroundStyle(.secondary).monospacedDigit()
            }
            if let button = row.oneButton {
                Button { perform(button, row) } label: { Label(label(button), systemImage: symbol(button)) }
                    .labelStyle(TitleOrIconLabelStyle(showsTitle: button == .retry || button == .show))
                    .accessibilityLabel(label(button))
                    .buttonStyle(.borderless)
                    .help("\(label(button)) \(row.name)")
                    .accessibilityIdentifier("activity.row.\(row.jobId ?? row.id).\(label(button).lowercased())")
            }
        }
        .contentShape(Rectangle())
        .task(id: row.id) { await appeared(row) }
        .accessibilityIdentifier("activity.row.\(row.jobId ?? row.id)")
    }

    private func title(_ row: ActivityMonitorRow) -> String { row.displayName(showsProject: showsProject) }

    /// The state's words, then the counts and the time left; a waiting row says what it waits for and never ticks.
    private func subtitle(_ row: ActivityMonitorRow) -> String {
        [row.stateText, row.progressText].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    private func label(_ button: ActivityMonitorRow.OneButton) -> String {
        switch button {
        case .pause: "Pause"
        case .resume: "Resume"
        case .retry: "Retry"
        case .show: "Show"
        }
    }

    private func symbol(_ button: ActivityMonitorRow.OneButton) -> String {
        switch button {
        case .pause: "pause.fill"
        case .resume: "play.fill"
        case .retry: "arrow.counterclockwise"
        case .show: "chevron.right"
        }
    }
}

#Preview("Now, Up Next and Done Today") {
    let running = ActivityMonitorRow.job(
        ActivityJob(id: "embed-1", taskType: "embedding", name: "Embedding queue", current: 4, total: 10,
                    state: .running, reason: nil),
        libraryId: nil, projectName: "Marshall Diaries")
    let waiting = ActivityMonitorRow.job(
        ActivityJob(id: "embed-2", taskType: "embedding", name: "Embedding queue", current: 0, total: 10,
                    state: .waiting, reason: "Waiting: memory is tight"),
        libraryId: nil, projectName: "Marshall Diaries")
    return ActivityGroupsView(
        groups: ActivityWindowGroups(rows: [running, waiting]), showsProject: false,
        appeared: { _ in }, perform: { _, _ in }, open: { _ in },
        stopTarget: { row in
            ActivityRunMenuTarget(rowId: row.id, rowName: row.name, canStop: false, readAgainLabel: nil, stop: {}, readAgain: {})
        },
        clearFailed: {}, clearFinished: {}, delete: { _ in })
        .frame(width: 420, height: 320)
}

/// `.titleOnly` or `.iconOnly` chosen per button (a ternary cannot mix the two style types).
private struct TitleOrIconLabelStyle: LabelStyle {
    let showsTitle: Bool
    func makeBody(configuration: Configuration) -> some View {
        if showsTitle { configuration.title } else { configuration.icon }
    }
}
