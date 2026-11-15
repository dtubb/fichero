//
//  ActivityPane.swift
//  Fichero
//
//  The Activity pane's pure model (#6441, docs/contributor_manual/specs/ui/activity-pane.md): the one flat outline
//  (`activity.pane.one-outline-table`), Group by File (`activity.pane.group-by-run-or-by-file`), the versions of a step
//  (`activity.pane.versions-are-siblings`), the one state glyph (`activity.pane.one-glyph-per-state`) and the one column
//  table (`activity.pane.default-columns`). Pure over `ActivityMonitorRow`, so every rule is tested without a view.
//

import Foundation
import SwiftUI

enum ActivityPane {
    // MARK: - Grouping

    /// Group by: Run | File, one switch per pane; a new pane opens by Run (decision 4).
    enum Grouping: String, CaseIterable, Identifiable {
        case run, file
        var id: String { rawValue }
        var title: String { self == .run ? "Run" : "File" }
    }

    /// The window's four tabs, one table (`activity.window.toolbar-tabs`, decision 23): each a grouping and a column set over
    /// the same rows. Runs: what is working and what needs me; Files: what happened to my pages; Cost: what it spends;
    /// Where: where it runs.
    enum Tab: String, CaseIterable, Identifiable, Codable {
        case runs, files, cost, place = "where"

        var id: String { rawValue }

        var title: String {
            switch self {
            case .runs: "Runs"
            case .files: "Files"
            case .cost: "Cost"
            case .place: "Where"
            }
        }

        var icon: String {
            switch self {
            case .runs: "list.bullet.indent"
            case .files: "doc.on.doc"
            case .cost: "dollarsign.circle"
            case .place: "desktopcomputer"
            }
        }

        var grouping: Grouping { self == .files ? .file : .run }

        /// The columns the tab shows until a person changes them.
        var columns: [Column] {
            switch self {
            case .runs: [.source, .name, .state, .trail, .time, .cost]
            case .files: [.name, .state, .trail, .started]
            case .cost: [.source, .name, .model, .tokens, .time, .cost, .toFinish]
            case .place: [.source, .name, .runsOn, .lane, .state]
            }
        }

        /// The tab a grouping chosen elsewhere (View › Activity ▸, a main window's lens) lands on.
        static func of(_ grouping: Grouping) -> Tab { grouping == .file ? .files : .runs }
    }

    /// The listed rows that are the selections asked for (the launch alert's Choose…), by job and project.
    static func rowIds(for wanted: [ActivitySelection], in rows: [ActivityMonitorRow]) -> Set<String> {
        let asked = Set(wanted)
        return Set(rows.filter { row in row.selection.map(asked.contains) ?? false }.map(\.id))
    }

    /// A run row is listed from the runs list, and its twin in the jobs list carries the engine's failure (its row words, its
    /// fix, its buttons): the run row takes it, so a failed run says why in its row, not a bare red X (#6588).
    static func withRunFailures(_ rows: [ActivityMonitorRow], jobs: [ActivityJob]) -> [ActivityMonitorRow] {
        let failures = Dictionary(jobs.compactMap { job in job.failure.map { (job.id, $0) } }, uniquingKeysWith: { first, _ in first })
        guard !failures.isEmpty else { return rows }
        return rows.map { row in
            guard row.kind == .run, row.failure == nil, let id = row.runThreadId ?? row.jobId, let failure = failures[id] else {
                return row
            }
            var row = row
            row.failure = failure
            if !failure.rowWords.isEmpty { row.reason = failure.rowWords }
            return row
        }
    }

    /// A job of its own opens to the files it works on NOW (`activity.pane.children-are-what-it-works-on`, #6599): a queue
    /// row's (`waiting:<kind>`) children are its items in flight, by name; none in flight, no disclosure.
    static func withQueuedFiles(_ rows: [ActivityMonitorRow], queued: [String: [ActivityQueuedItem]]) -> [ActivityMonitorRow] {
        rows.map { row in
            guard row.kind == .job, let kind = ActivityStore.queuedKind(ofRowId: row.id) else { return row }
            let inFlight = (queued[kind] ?? []).filter { $0.state == "running" }
            guard !inFlight.isEmpty else { return row }
            var row = row
            row.children = inFlight.map { item in
                var file = ActivityMonitorRow(
                    id: "\(row.id)|item:\(item.id)", kind: .page, libraryId: row.libraryId, runRowID: nil, runThreadId: nil,
                    jobId: item.id, name: item.name ?? "A page", projectName: nil, phase: .running, reason: item.reason,
                    workingOn: nil, done: 0, total: 0, started: nil, seconds: nil, costUsd: nil, tokens: 0, errors: 0,
                    model: nil, isLive: true, children: nil)
                file.documentId = item.subject
                file.engineKind = row.engineKind
                return file
            }
            return row
        }
    }

    /// What an empty pane says in its one line (`activity.pane.empty-says-one-line`, #6599): "Nothing running" with nothing to
    /// list, "No activity matches" when the filter hides every row; nil while there are rows.
    static func emptyLine(rowsShown: Int, filterIsEmpty: Bool) -> String? {
        guard rowsShown == 0 else { return nil }
        return filterIsEmpty ? "Nothing running" : "No activity matches"
    }

    /// The Where cell's words for the engine's place.
    static func whereLine(_ row: ActivityMonitorRow) -> String {
        switch row.runsOn {
        case "this-mac": "This Mac"
        case "other-mac": "Other Mac"
        case "cloud": "Cloud"
        case "cluster": "Cluster"
        default: ""
        }
    }

    /// The To Finish cell: the estimate of what is left to spend while it runs; nothing once it ended or for local work.
    static func toFinishLine(_ row: ActivityMonitorRow) -> String {
        guard row.phase.isLive, let left = row.costEstimateUsd, left > 0 else { return "" }
        return String(format: "~$%.2f", left)  // the Cost cell's own form ("$0.42"), never the locale's "US$"
    }

    // MARK: - The flat outline: rows sorted by state then start, two levels

    /// Where a state sorts: what runs, then what is held, then what waits, then what ended (newest first within each).
    static func stateRank(_ phase: ActivityMonitorRow.Phase) -> Int {
        switch phase {
        case .running: 0
        case .paused: 1
        case .waiting: 2
        case .failed: 3
        case .partial: 4
        case .interrupted: 5
        case .cancelled: 6
        case .done: 7
        case .notRun: 8
        case .unknown: 9
        }
    }

    /// Where a row sorts by default (`activity.pane.needs-you-first`, #6599): what NEEDS THE PERSON first (failed, partial,
    /// a row paused for a cause or stopped at quit), then what runs, then what waits (a row the person paused waits with
    /// it), then what ended.
    static func needsYouRank(_ row: ActivityMonitorRow) -> Int {
        switch row.phase {
        case .failed, .partial: 0
        case .paused: (row.reason ?? "").hasPrefix("Paused by you") ? 2 : 0
        case .running: 1
        case .waiting: 2
        case .done, .cancelled, .interrupted, .notRun, .unknown: 3
        }
    }

    /// The pane's rows by Run: no section rows, what needs the person first (newest first), then what runs, then what waits
    /// (in the lane's order), then what ended (newest first); each run row's children its FILES (`files(of:)`), never its
    /// steps.
    static func outline(_ rows: [ActivityMonitorRow]) -> [ActivityMonitorRow] {
        rows.sorted { lhs, rhs in
            let left = needsYouRank(lhs), right = needsYouRank(rhs)
            if left != right { return left < right }
            if left == 2, lhs.queueKey != rhs.queueKey { return lhs.queueKey < rhs.queueKey }
            if lhs.startedKey != rhs.startedKey { return lhs.startedKey > rhs.startedKey }
            return lhs.id < rhs.id
        }
        .map { row in
            var row = row
            // A run's files; a job of its own keeps the files in flight it was given (`withQueuedFiles`).
            row.children = files(of: row) ?? (row.kind == .job ? row.children : nil)
            return row
        }
    }

    /// A run's FILES: one row per distinct document among the page nodes of its tree, in the tree's order; its state the
    /// worst of its pages', its counts its pages; nil when the tree names no document (no disclosure).
    static func files(of row: ActivityMonitorRow) -> [ActivityMonitorRow]? {
        var order: [String] = []
        var pages: [String: [ActivityMonitorRow]] = [:]
        for page in leaves(of: row) {
            guard let documentId = page.documentId else { continue }
            if pages[documentId] == nil { order.append(documentId) }
            pages[documentId, default: []].append(page)
        }
        guard !order.isEmpty else { return nil }
        return order.map { documentId in fileRow(id: "\(row.id)|file:\(documentId)", documentId: documentId,
                                                  pages: pages[documentId] ?? [], parent: row) }
    }

    /// The selection carried across a Group by switch (`activity.pane.group-by-run-or-by-file`): a file stays selected as
    /// that file (by File, its row; by Run, its row under the first run that read it); a run row has no file to be, so it
    /// stays only where its id is listed. `rows` is the new grouping's outline.
    static func carry(_ selection: Set<String>, into rows: [ActivityMonitorRow]) -> Set<String> {
        let listed = rows.flatMap { [$0.id] + ($0.children ?? []).map(\.id) }
        return Set(selection.compactMap { id -> String? in
            guard let range = id.range(of: "file:") else { return listed.contains(id) ? id : nil }
            let file = "file:" + (id[range.upperBound...].split(separator: "|").first.map(String.init) ?? "")
            return listed.first { $0 == file || $0.hasSuffix("|" + file) }
        })
    }

    /// The file row Show in Activity selects: the first of the documents (a page, then its parent) that has a row by File.
    static func fileRowId(_ documentIds: [String], in fileRows: [ActivityMonitorRow]) -> String? {
        documentIds.lazy.map { "file:\($0)" }.first { id in fileRows.contains { $0.id == id } }
    }

    /// A column header's sort over the top-level rows; none chosen keeps the outline's state-then-start order, and a run's
    /// files keep their tree order under it.
    static func sorted(_ rows: [ActivityMonitorRow], by order: [KeyPathComparator<ActivityMonitorRow>]) -> [ActivityMonitorRow] {
        order.isEmpty ? rows : rows.sorted(using: order)
    }

    /// The page rows under a row, however deep (a run's steps hold its pages).
    static func leaves(of row: ActivityMonitorRow) -> [ActivityMonitorRow] {
        guard let children = row.children, !children.isEmpty else { return row.kind == .page ? [row] : [] }
        return children.flatMap(leaves)
    }

    /// The worst state among some rows: a failure shows over work going on, work going on over work done.
    static func worst(_ phases: [ActivityMonitorRow.Phase]) -> ActivityMonitorRow.Phase {
        let severity: [ActivityMonitorRow.Phase] = [.failed, .running, .paused, .waiting, .partial, .interrupted, .cancelled,
                                                    .done, .notRun, .unknown]
        return severity.first(where: phases.contains) ?? .unknown
    }

    private static func fileRow(id: String, documentId: String, pages: [ActivityMonitorRow],
                                parent: ActivityMonitorRow) -> ActivityMonitorRow {
        let first = pages.first
        var row = ActivityMonitorRow(
            id: id, kind: .page, libraryId: parent.libraryId, runRowID: parent.runRowID, runThreadId: parent.runThreadId,
            jobId: first?.jobId, name: first?.name ?? documentId, projectName: nil,
            phase: worst(pages.map(\.phase)), reason: pages.first { $0.phase == .failed }?.reason, workingOn: nil,
            done: pages.filter { $0.phase == .done }.count, total: pages.count,
            started: pages.compactMap(\.started).min(), seconds: sum(pages.compactMap(\.seconds)),
            costUsd: sum(pages.compactMap(\.costUsd)), tokens: pages.map(\.tokens).reduce(0, +),
            errors: pages.filter { $0.phase == .failed }.count, model: first?.model, isLive: false, children: nil
        )
        row.documentId = documentId
        row.engineKind = first?.engineKind
        row.ended = pages.compactMap(\.ended).max()
        return row
    }

    private static func sum(_ values: [Double]) -> Double? { values.isEmpty ? nil : values.reduce(0, +) }

    // MARK: - Group by File

    /// The pane's rows by File: each file the rows touched, in the order first met; a file row shows what runs on it now
    /// (its newest entry's state) and opens to its PATH through the steps, in run order (oldest first): one entry per
    /// step that touched it, "Letters › Read", with its model, result, time and cost. Where one step ran on the file more
    /// than once, the entries are its VERSIONS, side by side, and the newest that ended done is marked as counting.
    static func byFile(_ rows: [ActivityMonitorRow]) -> [ActivityMonitorRow] {
        var order: [String] = []
        var paths: [String: [ActivityMonitorRow]] = [:]
        var fileNames: [String: String] = [:]
        for run in rows.sorted(by: { $0.startedKey < $1.startedKey }) {
            for (step, page) in stepsAndPages(of: run) {
                guard let documentId = page.documentId else { continue }
                if paths[documentId] == nil { order.append(documentId); fileNames[documentId] = page.name }
                var entry = page
                entry.name = "\(run.name) › \(step?.name ?? run.name)"
                entry.id = "file:\(documentId)|\(page.id)"
                entry.model = page.model ?? step?.model
                entry.children = nil
                paths[documentId, default: []].append(entry)
            }
        }
        return order.map { documentId in
            let entries = markCounting(paths[documentId] ?? [])
            var row = fileRow(id: "file:\(documentId)", documentId: documentId, pages: entries, parent: entries[0])
            row.name = fileNames[documentId] ?? documentId
            row.phase = entries.last?.phase ?? row.phase
            row.runRowID = nil
            row.runThreadId = nil
            row.children = entries
            return row
        }
    }

    /// Each page of a run with the step it sits under (nil when the page is the run's own child).
    private static func stepsAndPages(of run: ActivityMonitorRow) -> [(ActivityMonitorRow?, ActivityMonitorRow)] {
        var out: [(ActivityMonitorRow?, ActivityMonitorRow)] = []
        func walk(_ row: ActivityMonitorRow, step: ActivityMonitorRow?) {
            for child in row.children ?? [] {
                if child.kind == .page, (child.children ?? []).isEmpty {
                    out.append((step, child))
                } else {
                    walk(child, step: child.kind == .step ? child : step)
                }
            }
        }
        walk(run, step: nil)
        return out
    }

    /// The versions of one step on one file: the newest that ended done counts; every other entry keeps `counts` false.
    static func markCounting(_ entries: [ActivityMonitorRow]) -> [ActivityMonitorRow] {
        var entries = entries
        var seen: Set<String> = []
        for index in entries.indices.reversed() where entries[index].phase == .done {
            if seen.insert(entries[index].name).inserted { entries[index].counts = true }
        }
        return entries
    }

    // MARK: - Versions of a step (the Inspector's section)

    /// One step that ran more than once under a run: its runs, newest first, the newest done one counting.
    struct StepVersions: Equatable, Identifiable {
        let step: String
        let versions: [ActivityMonitorRow]
        var id: String { step }
    }

    /// The steps of a run that have more than one version (a retry, Read Again, another model), from its tree alone.
    static func versions(of run: ActivityMonitorRow) -> [StepVersions] {
        let steps = (run.children ?? []).filter { $0.kind == .step }
        var order: [String] = []
        var byName: [String: [ActivityMonitorRow]] = [:]
        for step in steps {
            if byName[step.name] == nil { order.append(step.name) }
            byName[step.name, default: []].append(step)
        }
        return order.compactMap { name in
            let runs = byName[name] ?? []
            guard runs.count > 1 else { return nil }
            return StepVersions(step: name, versions: markCounting(runs).reversed())
        }
    }

    /// The versions the Inspector shows for a selected row: its run's, read from the run as listed (with its steps), not
    /// from the shown outline, whose run rows hold files.
    static func versions(for row: ActivityMonitorRow, in allRows: [ActivityMonitorRow]) -> [StepVersions] {
        let runId = row.kind == .run ? row.id : row.runRowID
        return allRows.first { $0.id == runId }.map(versions(of:)) ?? []
    }

    // MARK: - One glyph per state

    /// The state's ONE glyph (nil symbol = the system spinner), its word for the tooltip and VoiceOver, and whether it is
    /// drawn red (a failure) or green (done, `activity.pane.done-is-green`); everything else is secondary.
    struct Glyph: Equatable {
        let symbol: String?
        let word: String
        let isFailure: Bool
        var isSuccess = false

        /// Red for a failure, green for done, secondary for the rest: the table and the Inspector draw it alike.
        var tint: AnyShapeStyle {
            isFailure ? AnyShapeStyle(.red) : isSuccess ? AnyShapeStyle(.green) : AnyShapeStyle(.secondary)
        }
    }

    static func glyph(_ row: ActivityMonitorRow) -> Glyph {
        if let transient = row.transientState { return Glyph(symbol: nil, word: transient, isFailure: false) }
        switch row.phase {
        case .running: return Glyph(symbol: nil, word: "Running", isFailure: false)
        case .waiting: return Glyph(symbol: "circle", word: "Waiting", isFailure: false)
        case .paused, .interrupted: return Glyph(symbol: "pause.circle", word: "Paused", isFailure: false)
        case .cancelled: return Glyph(symbol: "stop.circle", word: "Stopped", isFailure: false)
        case .done: return Glyph(symbol: "checkmark.circle.fill", word: "Done", isFailure: false, isSuccess: true)
        case .partial: return Glyph(symbol: "checkmark.circle", word: "Done, some failed", isFailure: false, isSuccess: true)
        case .failed: return Glyph(symbol: "xmark.circle.fill", word: "Failed", isFailure: true)
        case .notRun: return Glyph(symbol: "minus", word: "Skipped", isFailure: false)
        case .unknown: return Glyph(symbol: "questionmark.circle", word: row.stateText, isFailure: false)
        }
    }

    // MARK: - The one column table

    /// The table's columns, and no others (`activity.pane.default-columns`): the six on by default, the four a person
    /// turns on from the header's menu. The raw value is the column's customization id, remembered per pane.
    enum Column: String, CaseIterable {
        case source, name, state, trail, time, cost, model, startedBy, started, kind, tokens, toFinish, runsOn, lane

        var isOnByDefault: Bool { Tab.runs.columns.contains(self) }

        /// The column's title on a tab (decision 23): the Files tab names its rows File and its date Last Run, the Cost tab
        /// its dollars Spent; every other title is the column's own.
        func title(in tab: Tab) -> String {
            switch (self, tab) {
            case (.name, .files): "File"
            case (.started, .files): "Last Run"
            case (.cost, .cost): "Spent"
            default: title
            }
        }

        var title: String {
            switch self {
            case .source: ""
            case .name: "Name"
            case .state: "State"
            case .trail: "Steps"
            case .time: "Time"
            case .cost: "Cost"
            case .model: "Model"
            case .startedBy: "Started By"
            case .started: "Started"
            case .kind: "Kind"
            case .tokens: "Tokens"
            case .toFinish: "To Finish"
            case .runsOn: "Runs On"
            case .lane: "Lane"
            }
        }
    }

    // MARK: - The row's words (the text budget, `activity.pane.text-budget`)

    /// The State cell's words: none for a row its glyph says alone; a failed or held row its line of at most eight words
    /// (the failure kind's own row words, never a sentence cut short).
    /// Pages that failed for the same reason collapse into the one line with their count ("No credit left · 12 pages").
    static func stateLine(_ row: ActivityMonitorRow) -> String {
        guard row.phase == .failed || row.phase == .partial || row.phase == .paused || row.phase == .interrupted else {
            return ""
        }
        let failedPages = row.kind == .page ? [] : leaves(of: row).filter { $0.phase == .failed }
        let pageLines = Set(failedPages.map(ownLine))
        let line = ownLine(row).isEmpty ? (pageLines.count == 1 ? pageLines.first ?? "" : "") : ownLine(row)
        guard !line.isEmpty else { return "" }
        if failedPages.count > 1, pageLines == [line], words(line) + 3 <= wordBudget {
            return "\(line) · \(failedPages.count) pages"
        }
        return line
    }

    /// A row's own line: its failure kind's row words, else a reason short enough to be one.
    private static func ownLine(_ row: ActivityMonitorRow) -> String {
        if let words = row.failure?.rowWords, !words.isEmpty { return trimmed(words) }
        guard let reason = row.reason, !reason.isEmpty else { return "" }
        return words(reason) <= wordBudget ? trimmed(reason) : ""
    }

    /// The Steps cell: the trail of a recipe run, else "12 of 40" while it has counts.
    static func progressLine(_ row: ActivityMonitorRow) -> String {
        if !row.trail.isEmpty { return row.trail }
        // One item counts nothing: "0 of 1" and "1 of 1" only repeat the state glyph (#6588).
        guard row.total > 1, !row.looksWaiting else { return row.ranOnText ?? "" }
        return "\(row.done) of \(row.total)"
    }

    /// The Time cell: the time left while it runs, its duration once ended; never a clock time and never both.
    static func timeLine(_ row: ActivityMonitorRow) -> String {
        if row.phase == .running, let left = row.remainingSeconds { return "\(ActivityMonitorRow.duration(left)) left" }
        return row.secondsText
    }

    /// The Cost cell: "$0.42 · ~$1.10 more" while it runs, "$0.42" once ended; blank for local work (the engine's null);
    /// "Free" for cloud calls priced at $0 (the engine's 0.0, #6598); "Not priced" when a call under it had no price;
    /// never "$0.00" (`activity.pane.row-and-inspector-agree`).
    static func costLine(_ row: ActivityMonitorRow) -> String {
        let text = ActivityTrail.cost(spentUsd: row.costUsd, estimateUsd: row.phase.isLive ? row.costEstimateUsd : nil)
        if !text.isEmpty { return text }
        if row.costUsd == 0 { return "Free" }
        return row.costUsd == nil && row.tokens > 0 ? "Not priced" : ""
    }

    /// Every cell's words a row draws, the name aside (exempt: a name is cut with a middle ellipsis).
    static func cellWords(_ row: ActivityMonitorRow) -> [String] {
        [stateLine(row), timeLine(row), costLine(row)].filter { !$0.isEmpty }
    }

    static let wordBudget = 8

    /// Whitespace tokens, the budget's unit.
    static func words(_ text: String) -> Int { text.split(whereSeparator: \.isWhitespace).count }

    /// A line holds no sentence: a closing full stop is dropped.
    private static func trimmed(_ text: String) -> String {
        var text = text.trimmingCharacters(in: .whitespaces)
        while text.hasSuffix(".") { text.removeLast() }
        return text
    }
}

extension ActivityMonitorRow {
    /// The State column's sort key: the outline's state order.
    var stateRankKey: Int { ActivityPane.stateRank(phase) }
}
