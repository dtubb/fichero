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

enum ActivityPane {
    // MARK: - Grouping

    /// Group by: Run | File, one switch per pane; a new pane opens by Run (decision 4).
    enum Grouping: String, CaseIterable, Identifiable {
        case run, file
        var id: String { rawValue }
        var title: String { self == .run ? "Run" : "File" }
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

    /// The pane's rows by Run: no section rows, sorted by state then start (waiting rows in the lane's order), each run
    /// row's children its FILES (`files(of:)`), never its steps.
    static func outline(_ rows: [ActivityMonitorRow]) -> [ActivityMonitorRow] {
        rows.sorted { lhs, rhs in
            let left = (stateRank(lhs.phase), lhs.queueKey), right = (stateRank(rhs.phase), rhs.queueKey)
            if left != right { return left < right }
            return lhs.startedKey > rhs.startedKey
        }
        .map { row in
            var row = row
            row.children = files(of: row)
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

    // MARK: - One glyph per state

    /// The state's ONE glyph (nil symbol = the system spinner), its word for the tooltip and VoiceOver, and whether it is
    /// drawn red (a failure).
    struct Glyph: Equatable {
        let symbol: String?
        let word: String
        let isFailure: Bool
    }

    static func glyph(_ row: ActivityMonitorRow) -> Glyph {
        if let transient = row.transientState { return Glyph(symbol: nil, word: transient, isFailure: false) }
        switch row.phase {
        case .running: return Glyph(symbol: nil, word: "Running", isFailure: false)
        case .waiting: return Glyph(symbol: "circle", word: "Waiting", isFailure: false)
        case .paused, .interrupted: return Glyph(symbol: "pause.circle", word: "Paused", isFailure: false)
        case .cancelled: return Glyph(symbol: "stop.circle", word: "Stopped", isFailure: false)
        case .done: return Glyph(symbol: "checkmark.circle.fill", word: "Done", isFailure: false)
        case .partial: return Glyph(symbol: "checkmark.circle", word: "Done, some failed", isFailure: false)
        case .failed: return Glyph(symbol: "xmark.circle.fill", word: "Failed", isFailure: true)
        case .notRun: return Glyph(symbol: "minus", word: "Skipped", isFailure: false)
        case .unknown: return Glyph(symbol: "questionmark.circle", word: row.stateText, isFailure: false)
        }
    }

    // MARK: - The one column table

    /// The table's columns, and no others (`activity.pane.default-columns`): the six on by default, the four a person
    /// turns on from the header's menu. The raw value is the column's customization id, remembered per pane.
    enum Column: String, CaseIterable {
        case source, name, state, trail, time, cost, model, startedBy, started, kind

        var isOnByDefault: Bool {
            switch self {
            case .source, .name, .state, .trail, .time, .cost: true
            case .model, .startedBy, .started, .kind: false
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
        guard row.total > 0, !row.looksWaiting else { return row.ranOnText ?? "" }
        return "\(row.done) of \(row.total)"
    }

    /// The Time cell: the time left while it runs, its duration once ended; never a clock time and never both.
    static func timeLine(_ row: ActivityMonitorRow) -> String {
        if row.phase == .running, let left = row.remainingSeconds { return "\(ActivityMonitorRow.duration(left)) left" }
        if row.looksWaiting { return "" }
        if let seconds = row.seconds { return ActivityMonitorRow.duration(seconds) }
        if let start = row.started, let end = row.ended, end > start { return ActivityMonitorRow.duration(end.timeIntervalSince(start)) }
        return ""
    }

    /// The Cost cell: "$0.42 · ~$1.10 more" while it runs, "$0.42" once ended; blank for local work; "Not priced" when a
    /// call under it had no price; never "$0".
    static func costLine(_ row: ActivityMonitorRow) -> String {
        let text = ActivityTrail.cost(spentUsd: row.costUsd, estimateUsd: row.phase.isLive ? row.costEstimateUsd : nil)
        if !text.isEmpty { return text }
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
