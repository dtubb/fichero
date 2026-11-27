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

    /// The window's sidebar items, one table (`activity.window.sidebar`, decision 32; were the toolbar's tabs, decision 23):
    /// each a grouping and a column set over the same rows. Runs: what is working and what needs me; Files: what happened to
    /// my pages; Cost: what it spends; Where: where it runs; Archived: the rows put away, and only those.
    enum Tab: String, CaseIterable, Identifiable, Codable {
        case runs, files, recipes, cost, place = "where", archived

        var id: String { rawValue }

        var title: String {
            switch self {
            case .runs: "Runs"
            case .files: "Files"
            case .recipes: "Recipes"
            case .cost: "Cost"
            case .place: "Where"
            case .archived: "Archived"
            }
        }

        var icon: String {
            switch self {
            case .runs: "list.bullet.indent"
            case .files: "doc.on.doc"
            case .recipes: "list.bullet.rectangle"
            case .cost: "dollarsign.circle"
            case .place: "desktopcomputer"
            case .archived: "archivebox"
            }
        }

        var grouping: Grouping { self == .files ? .file : .run }

        /// The columns the tab shows until a person changes them.
        var columns: [Column] {
            switch self {
            case .runs: [.source, .name, .state, .trail, .time, .cost]
            case .files: [.name, .state, .trail, .started]
            case .recipes: [.name, .state, .model, .time, .cost]
            case .cost: [.source, .name, .model, .tokens, .time, .cost, .toFinish]
            case .place: [.source, .name, .runsOn, .lane, .state]
            case .archived: [.source, .name, .state, .started, .time, .cost]
            }
        }

        /// The sidebar's sections (`activity.window.sidebar`): the work, then the resources it uses; Archived below them.
        static let sidebarWork: [Tab] = [.runs, .files, .recipes]
        static let sidebarResources: [Tab] = [.cost, .place]

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

    /// How many rows need the person (`needsYouRank` 0): the Runs item's badge in the sidebar.
    static func needsYouCount(_ rows: [ActivityMonitorRow]) -> Int {
        rows.filter { !$0.isArchived && needsYouRank($0) == 0 }.count
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
}

// Versions of a step, for the Inspector.
extension ActivityPane {
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

    /// The row with this id among `rows` and the rows under them.
    static func row(_ id: ActivityMonitorRow.ID, in rows: [ActivityMonitorRow]) -> ActivityMonitorRow? {
        for row in rows {
            if row.id == id { return row }
            if let found = self.row(id, in: row.children ?? []) { return found }
        }
        return nil
    }

    /// What the Inspector's Activity section is given for the pane's selection: the ONE selected row's details and its
    /// run's versions; nil with none or several selected, or a row with no job behind it.
    static func pick(_ ids: Set<ActivityMonitorRow.ID>, shown: [ActivityMonitorRow],
                     all: [ActivityMonitorRow]) -> ActivityPaneSelection? {
        guard ids.count == 1, let id = ids.first, let found = row(id, in: shown), let picked = found.selection else { return nil }
        return ActivityPaneSelection(selection: picked, versions: versions(for: found, in: all))
    }
}

extension ActivityMonitorRow {
    /// The State column's sort key: the outline's state order.
    var stateRankKey: Int { ActivityPane.stateRank(phase) }
}
