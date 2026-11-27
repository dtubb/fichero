import SwiftUI

/// What one Activity pane remembers across a relaunch (`activity.pane.one-outline-table`, `.default-columns`,
/// `.history-kept-and-filterable`): its grouping, its filter, the rows left open and its columns; kept per pane key in one
/// app preference.
struct ActivityPanePrefs: Codable, Equatable {
    var grouping: ActivityPane.Grouping = .run
    var filter = ""
    var expanded: Set<String> = []
    /// The Runs tab's columns (the columns a pane had before the tabs, kept).
    var columns = TableColumnCustomization<ActivityMonitorRow>()
    /// The tab, and the other tabs' columns as a person set them (`activity.window.toolbar-tabs`, #6588).
    var tab: ActivityPane.Tab = .runs
    var tabColumns: [String: TableColumnCustomization<ActivityMonitorRow>] = [:]
    /// Each sidebar item's centre view, Table, Graph or Visual (`activity.window.centre-views`), by the item's raw
    /// value.
    var centreViews: [String: ActivityCentreView] = [:]

    init() {}

    /// Every key optional: prefs a pane stored before a key existed still load, never reset.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        grouping = try container.decodeIfPresent(ActivityPane.Grouping.self, forKey: .grouping) ?? .run
        filter = try container.decodeIfPresent(String.self, forKey: .filter) ?? ""
        expanded = try container.decodeIfPresent(Set<String>.self, forKey: .expanded) ?? []
        columns = try container.decodeIfPresent(TableColumnCustomization<ActivityMonitorRow>.self, forKey: .columns) ?? .init()
        tab = try container.decodeIfPresent(ActivityPane.Tab.self, forKey: .tab) ?? ActivityPane.Tab.of(grouping)
        tabColumns = try container.decodeIfPresent([String: TableColumnCustomization<ActivityMonitorRow>].self,
                                                   forKey: .tabColumns) ?? [:]
        centreViews = try container.decodeIfPresent([String: ActivityCentreView].self, forKey: .centreViews) ?? [:]
    }

    /// The item's centre view as chosen, if the item offers it, else Table.
    func centreView(for tab: ActivityPane.Tab) -> ActivityCentreView {
        centreViews[tab.rawValue].flatMap { ActivityCentreView.offered(for: tab).contains($0) ? $0 : nil } ?? .table
    }

    /// The tab's columns: the Runs tab's own, another tab's as set, else that tab's defaults.
    func columns(for tab: ActivityPane.Tab) -> TableColumnCustomization<ActivityMonitorRow> {
        if tab == .runs { return columns }
        if let set = tabColumns[tab.rawValue] { return set }
        var defaults = TableColumnCustomization<ActivityMonitorRow>()
        for column in ActivityPane.Column.allCases where column != .name {
            defaults[visibility: column.rawValue] = tab.columns.contains(column) ? .visible : .hidden
        }
        return defaults
    }

    mutating func setColumns(_ value: TableColumnCustomization<ActivityMonitorRow>, for tab: ActivityPane.Tab) {
        if tab == .runs { columns = value } else { tabColumns[tab.rawValue] = value }
    }

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

    func table(_ shown: [ActivityMonitorRow]) -> some View {
        Table(of: ActivityMonitorRow.self, selection: $selection, sortOrder: $sortOrder, columnCustomization: Binding(
            get: { prefs.columns(for: prefs.tab) }, set: { value in update { $0.setColumns(value, for: $0.tab) } }
        )) {
            // Two builders: one of fourteen columns was past the type checker's time.
            leadingColumns
            otherColumns
        } rows: {
            ForEach(shown) { row in
                if let children = row.children, !children.isEmpty {
                    DisclosureTableRow(row, isExpanded: expanded(row.id)) {
                        ForEach(children) { child in
                            // A multi-page file opens to its pages: the one further level (`activity.pane.one-outline-table`).
                            if let pages = child.children, !pages.isEmpty {
                                DisclosureTableRow(child, isExpanded: expanded(child.id)) {
                                    ForEach(pages) { TableRow($0) }
                                }
                            } else {
                                TableRow(child)
                            }
                        }
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
            for id in ids where (find(id, in: shown)?.children ?? []).isEmpty == false { toggle(id) }
            selection = ids
        }
        #if os(macOS)
        .onDeleteCommand { requestDelete(rows(selection)) }
        #endif
        // The menu bar acts on THIS pane only while its table has the focus: two Activity panes in a window, or the
        // Activity window beside a main window, never take each other's verbs (a scene value: the last pane drawn won).
        .focusedValue(\.activityRun, selectedRunTarget(in: shown))
        .focusedValue(\.activityVerbs, verbTarget(in: shown))
        .focusedValue(\.activityView, viewTarget)
        .accessibilityIdentifier("activity.table")
    }

    typealias PaneColumns = TableColumnBuilder<ActivityMonitorRow, KeyPathComparator<ActivityMonitorRow>>

    /// The Runs tab's columns, on by default.
    @PaneColumns
    var leadingColumns: some TableColumnContent<ActivityMonitorRow, KeyPathComparator<ActivityMonitorRow>> {
            TableColumn("") { row in sourceCell(row) }
                .width(22).customizationID(ActivityPane.Column.source.rawValue)
            TableColumn(ActivityPane.Column.name.title(in: prefs.tab), value: \.name) { row in nameCell(row) }
                .width(min: 160, ideal: 260).customizationID(ActivityPane.Column.name.rawValue)
                // Never hidden: a run row reads its tree when its Name cell is first drawn.
                .disabledCustomizationBehavior(.visibility)
            TableColumn(ActivityPane.Column.state.title(in: prefs.tab), value: \.stateRankKey) { row in stateCell(row) }
                .width(min: 60, ideal: 160).customizationID(ActivityPane.Column.state.rawValue)
            TableColumn(ActivityPane.Column.trail.title(in: prefs.tab)) { row in textCell(ActivityPane.progressLine(row)) }
                .width(min: 80, ideal: 240).customizationID(ActivityPane.Column.trail.rawValue)
            TableColumn(ActivityPane.Column.time.title(in: prefs.tab), value: \.secondsKey) { row in textCell(ActivityPane.timeLine(row)) }
                .width(min: 50, ideal: 80).customizationID(ActivityPane.Column.time.rawValue)
            TableColumn(ActivityPane.Column.cost.title(in: prefs.tab), value: \.costKey) { row in textCell(ActivityPane.costLine(row)) }
                .width(min: 50, ideal: 110).customizationID(ActivityPane.Column.cost.rawValue)
    }

    /// The columns off on the Runs tab: the header menu's, and the Cost and Where tabs' (decision 23).
    @PaneColumns
    var otherColumns: some TableColumnContent<ActivityMonitorRow, KeyPathComparator<ActivityMonitorRow>> {
            TableColumn(ActivityPane.Column.model.title(in: prefs.tab), value: \.modelKey) { row in textCell(row.model ?? "") }
                .customizationID(ActivityPane.Column.model.rawValue).defaultVisibility(.hidden)
            TableColumn(ActivityPane.Column.startedBy.title(in: prefs.tab)) { row in textCell(ActivityPane.startedByLine(row)) }
                .customizationID(ActivityPane.Column.startedBy.rawValue).defaultVisibility(.hidden)
            TableColumn(ActivityPane.Column.started.title(in: prefs.tab), value: \.startedKey) { row in
                textCell(row.started.map { $0.formatted(date: .abbreviated, time: .shortened) } ?? "")
            }
            .customizationID(ActivityPane.Column.started.rawValue).defaultVisibility(.hidden)
            TableColumn(ActivityPane.Column.kind.title(in: prefs.tab)) { row in kindCell(row) }
                .width(22).customizationID(ActivityPane.Column.kind.rawValue).defaultVisibility(.hidden)
            // The Cost and Where tabs' columns (decision 23); off on the Runs tab.
            TableColumn(ActivityPane.Column.tokens.title(in: prefs.tab)) { row in textCell(row.tokens > 0 ? row.tokens.formatted() : "") }
                .customizationID(ActivityPane.Column.tokens.rawValue).defaultVisibility(.hidden)
            TableColumn(ActivityPane.Column.toFinish.title(in: prefs.tab)) { row in textCell(ActivityPane.toFinishLine(row)) }
                .customizationID(ActivityPane.Column.toFinish.rawValue).defaultVisibility(.hidden)
            TableColumn(ActivityPane.Column.runsOn.title(in: prefs.tab)) { row in textCell(ActivityPane.whereLine(row)) }
                .customizationID(ActivityPane.Column.runsOn.rawValue).defaultVisibility(.hidden)
            TableColumn(ActivityPane.Column.lane.title(in: prefs.tab)) { row in textCell(row.lane.map { $0.capitalized } ?? "") }
                .customizationID(ActivityPane.Column.lane.rawValue).defaultVisibility(.hidden)
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
        return ActivityHoverTrackingView { hovered in HStack(spacing: 6) {
            Group {
                if let symbol = glyph.symbol {
                    Image(systemName: symbol).foregroundStyle(glyph.tint)
                } else {
                    ProgressView().controlSize(.small)
                }
            }
            .help(row.reason.map { "\(glyph.word): \($0)" } ?? glyph.word)
            .accessibilityLabel(glyph.word)
            // The page in view goes next (`activity.foreground.one-glyph-not-words`, #6442): one glyph, the words only
            // in its tooltip and for VoiceOver.
            if ActivityPane.isNextForThePageInView(row) {
                Image(systemName: "eye.fill").foregroundStyle(.secondary)
                    .help(ActivityPane.inViewWord).accessibilityLabel(ActivityPane.inViewWord)
            }
            if !line.isEmpty {
                Text(line).font(.caption).foregroundStyle(glyph.isFailure ? AnyShapeStyle(.red) : AnyShapeStyle(.secondary))
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
            // The row's own Play/Pause and Stop on the selected or hovered row (decision 31), small, as Xcode's.
            if selection.contains(row.id) || hovered {
                ForEach(row.rowControls) { verb in
                    Button { perform(verb, on: [row]) } label: { Label(verb.title, systemImage: verb.symbol) }
                        .labelStyle(.iconOnly).buttonStyle(.borderless).controlSize(.small)
                        .help("\(verb.title) \(row.name)")
                        .accessibilityLabel("\(verb.title) \(row.name)")
                        .accessibilityIdentifier("activity.row.\(row.jobId ?? row.id).control.\(verb.rawValue)")
                }
            }
            if let button = row.paneButton {
                // Its WORD, never an icon alone (`activity.pane.fix-button-has-words`, #6599).
                Button(button.title) { press(button, on: row) }
                    .controlSize(.small)
                    .buttonStyle(.bordered)
                    .fixedSize()
                    .help("\(button.title) \(row.name)")
                    .accessibilityLabel("\(button.title) \(row.name)")
                    .accessibilityIdentifier("activity.row.\(row.jobId ?? row.id).\(button.title.lowercased())")
            }
        } }
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
        // No Read Again beside Retry: Retry runs a failed run again over its unread pages (`activity.pane.verbs-one-word-each`).
    }

    // MARK: - Selection

    /// The rows of `ids` in `shown` (the list being drawn), or in the list built afresh for an event.
    func rows(_ ids: Set<ActivityMonitorRow.ID>, in shown: [ActivityMonitorRow]? = nil) -> [ActivityMonitorRow] {
        let shown = shown ?? shownRows
        return ids.compactMap { find($0, in: shown) }
    }

    func find(_ id: ActivityMonitorRow.ID, in shown: [ActivityMonitorRow]? = nil) -> ActivityMonitorRow? {
        ActivityPane.row(id, in: shown ?? shownRows)
    }

    /// The one selected row's details and its steps' versions; nil with none or several selected.
    var selectedPick: ActivityPaneSelection? { ActivityPane.pick(selection, shown: shownRows, all: allRows) }
}
