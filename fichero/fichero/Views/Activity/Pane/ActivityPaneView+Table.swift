import SwiftUI

/// What one Activity pane remembers across a relaunch (`activity.pane.one-outline-table`, `.default-columns`,
/// `.history-kept-and-filterable`): its grouping, its filter, the rows left open and its columns; kept per pane key in one
/// app preference.
struct ActivityPanePrefs: Codable, Equatable {
    var grouping: ActivityPane.Grouping = .run
    var filter = ""
    var expanded: Set<String> = []
    var columns = TableColumnCustomization<ActivityMonitorRow>()

    static func load(_ data: Data, key: String) -> ActivityPanePrefs {
        (try? JSONDecoder().decode([String: ActivityPanePrefs].self, from: data))?[key] ?? ActivityPanePrefs()
    }

    static func store(_ data: Data, key: String, change: (inout ActivityPanePrefs) -> Void) -> Data {
        var all = (try? JSONDecoder().decode([String: ActivityPanePrefs].self, from: data)) ?? [:]
        var prefs = all[key] ?? ActivityPanePrefs()
        change(&prefs)
        all[key] = prefs
        return (try? JSONEncoder().encode(all)) ?? data
    }
}

extension ActivityPane.Grouping: Codable {}

/// The pane's selected row, for the Inspector: its details' selection and the versions of its steps.
struct ActivityPaneSelection: Equatable {
    let selection: ActivitySelection
    var versions: [ActivityPane.StepVersions] = []
}

extension ActivityPaneView {
    // MARK: - The table

    var table: some View {
        Table(of: ActivityMonitorRow.self, selection: $selection, sortOrder: $sortOrder, columnCustomization: Binding(
            get: { prefs.columns }, set: { value in update { $0.columns = value } }
        )) {
            TableColumn("") { row in sourceCell(row) }
                .width(22).customizationID(ActivityPane.Column.source.rawValue)
            TableColumn(ActivityPane.Column.name.title, value: \.name) { row in nameCell(row) }
                .width(min: 160, ideal: 260).customizationID(ActivityPane.Column.name.rawValue)
            TableColumn(ActivityPane.Column.state.title, value: \.stateRankKey) { row in stateCell(row) }
                .width(min: 60, ideal: 160).customizationID(ActivityPane.Column.state.rawValue)
            TableColumn(ActivityPane.Column.trail.title) { row in textCell(ActivityPane.progressLine(row)) }
                .width(min: 80, ideal: 240).customizationID(ActivityPane.Column.trail.rawValue)
            TableColumn(ActivityPane.Column.time.title, value: \.secondsKey) { row in textCell(ActivityPane.timeLine(row)) }
                .width(min: 50, ideal: 80).customizationID(ActivityPane.Column.time.rawValue)
            TableColumn(ActivityPane.Column.cost.title, value: \.costKey) { row in textCell(ActivityPane.costLine(row)) }
                .width(min: 50, ideal: 110).customizationID(ActivityPane.Column.cost.rawValue)
            TableColumn(ActivityPane.Column.model.title, value: \.modelKey) { row in textCell(row.model ?? "") }
                .customizationID(ActivityPane.Column.model.rawValue).defaultVisibility(.hidden)
            TableColumn(ActivityPane.Column.startedBy.title) { row in textCell(row.startedBy ?? "") }
                .customizationID(ActivityPane.Column.startedBy.rawValue).defaultVisibility(.hidden)
            TableColumn(ActivityPane.Column.started.title, value: \.startedKey) { row in
                textCell(row.started.map { $0.formatted(date: .abbreviated, time: .shortened) } ?? "")
            }
            .customizationID(ActivityPane.Column.started.rawValue).defaultVisibility(.hidden)
            TableColumn(ActivityPane.Column.kind.title) { row in kindCell(row) }
                .width(22).customizationID(ActivityPane.Column.kind.rawValue).defaultVisibility(.hidden)
        } rows: {
            ForEach(shownRows) { row in
                if let children = row.children, !children.isEmpty {
                    DisclosureTableRow(row, isExpanded: expanded(row.id)) {
                        ForEach(children) { TableRow($0) }
                    }
                } else {
                    TableRow(row)
                }
            }
        }
        .contextMenu(forSelectionType: ActivityMonitorRow.ID.self) { ids in
            contextMenu(rows(ids))
        } primaryAction: { ids in
            // A double-click DISCLOSES the row and selects it (decision 8); its details are already in the Inspector.
            for id in ids where (find(id)?.children ?? []).isEmpty == false { toggle(id) }
            selection = ids
        }
        #if os(macOS)
        .onDeleteCommand { requestDelete(rows(selection)) }
        #endif
        .accessibilityIdentifier("activity.table")
    }

    /// The disclosure of one row, remembered per row and per pane.
    private func expanded(_ id: String) -> Binding<Bool> {
        Binding(get: { prefs.expanded.contains(id) }, set: { open in
            update { if open { $0.expanded.insert(id) } else { $0.expanded.remove(id) } }
        })
    }

    private func toggle(_ id: String) {
        update { prefs in if prefs.expanded.remove(id) == nil { prefs.expanded.insert(id) } }
    }

    // MARK: - Cells

    private func sourceCell(_ row: ActivityMonitorRow) -> some View {
        Group {
            if row.kind == .run || row.kind == .job {
                Image(systemName: row.source.symbol).foregroundStyle(.secondary)
                    .help(row.source.word).accessibilityLabel(row.source.word)
            }
        }
    }

    private func kindCell(_ row: ActivityMonitorRow) -> some View {
        Group {
            if let kind = row.kindGlyph {
                Image(systemName: kind.symbol).foregroundStyle(.secondary).help(kind.word).accessibilityLabel(kind.word)
            }
        }
    }

    private func nameCell(_ row: ActivityMonitorRow) -> some View {
        HStack(spacing: 4) {
            Text(row.displayName(showsProject: showsProject && row.projectName != nil))
                .lineLimit(1).truncationMode(.middle)
            if row.counts {
                Image(systemName: "star.fill").font(.caption2).foregroundStyle(.secondary)
                    .help("Its results count").accessibilityLabel("counts")
            }
        }
        .opacity(row.isArchived ? 0.5 : 1)
        .task(id: row.id) { await rowAppeared(row) }
        .accessibilityIdentifier("activity.row.\(row.jobId ?? row.id)")
    }

    /// ONE glyph for the state, its word in the tooltip and for VoiceOver; a failed or held row adds its line of at most
    /// eight words; the row's one button (the primary fix, else the state's verb) at the end.
    private func stateCell(_ row: ActivityMonitorRow) -> some View {
        let glyph = ActivityPane.glyph(row)
        let line = ActivityPane.stateLine(row)
        return HStack(spacing: 6) {
            Group {
                if let symbol = glyph.symbol {
                    Image(systemName: symbol).foregroundStyle(glyph.isFailure ? AnyShapeStyle(.red) : AnyShapeStyle(.secondary))
                } else {
                    ProgressView().controlSize(.small)
                }
            }
            .help(row.reason.map { "\(glyph.word): \($0)" } ?? glyph.word)
            .accessibilityLabel(glyph.word)
            if !line.isEmpty {
                Text(line).font(.caption).foregroundStyle(glyph.isFailure ? AnyShapeStyle(.red) : AnyShapeStyle(.secondary))
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
            if let button = row.paneButton {
                Button { press(button, on: row) } label: { Label(button.title, systemImage: button.symbol) }
                    .labelStyle(.iconOnly)
                    .buttonStyle(.borderless)
                    .help("\(button.title) \(row.name)")
                    .accessibilityLabel("\(button.title) \(row.name)")
                    .accessibilityIdentifier("activity.row.\(row.jobId ?? row.id).\(button.title.lowercased())")
            }
        }
    }

    private func textCell(_ text: String) -> some View {
        Text(text).font(.callout).foregroundStyle(.secondary).monospacedDigit().lineLimit(1)
    }

    // MARK: - The context menu: the one verb list, by the Mail rule

    @ViewBuilder
    private func contextMenu(_ rows: [ActivityMonitorRow]) -> some View {
        ForEach(ActivityPaneVerb.allCases) { verb in
            Button(role: verb == .delete ? .destructive : nil) { perform(verb, on: rows) } label: {
                Label(verb.title, systemImage: verb.symbol)
            }
            .disabled(!verb.isEnabled(for: rows))
        }
        if rows.count == 1, let row = rows.first {
            Divider()
            ActivityReadAgainMenuItem(target: runMenuTarget(for: row))
        }
    }

    // MARK: - Selection

    func rows(_ ids: Set<ActivityMonitorRow.ID>) -> [ActivityMonitorRow] {
        ids.compactMap(find)
    }

    func find(_ id: ActivityMonitorRow.ID) -> ActivityMonitorRow? {
        func search(_ rows: [ActivityMonitorRow]) -> ActivityMonitorRow? {
            for row in rows {
                if row.id == id { return row }
                if let found = search(row.children ?? []) { return found }
            }
            return nil
        }
        return search(shownRows)
    }

    /// The one selected row's details and its steps' versions; nil with none or several selected.
    var selectedPick: ActivityPaneSelection? {
        guard selection.count == 1, let id = selection.first, let row = find(id), let picked = row.selection else { return nil }
        let run = row.kind == .run ? row : allRows.first { $0.id == row.runRowID }
        return ActivityPaneSelection(selection: picked, versions: run.map(ActivityPane.versions(of:)) ?? [])
    }
}
