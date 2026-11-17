//
//  ActivityPane+Row.swift
//  Fichero
//
//  The Activity pane's row pieces, split from ActivityPane.swift for length: the one state glyph
//  (`activity.pane.one-glyph-per-state`), the one column table (`activity.pane.default-columns`) and the row's words
//  (`activity.pane.text-budget`).
//

import Foundation
import SwiftUI

extension ActivityPane {
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
        // Blocked, not waiting: the lock, the blocker named in the tooltip only
        // (`activity.pane.blocked-under-its-blocker`).
        if row.blockedBy != nil, row.phase == .waiting {
            return Glyph(symbol: "lock.circle", word: "Blocked", isFailure: false)
        }
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

    // MARK: - Blocked under its blocker

    /// The rows with blocked work listed UNDER what blocks it (`activity.pane.blocked-under-its-blocker`, #6593): under
    /// the row of the job that blocks it, else under one row for the need ("Search model bge-m3") when no listed job
    /// supplies it. The blocker's words are said once, on the blocker; a blocked row is never a top-level row of its
    /// own.
    static func underBlockers(_ rows: [ActivityMonitorRow]) -> [ActivityMonitorRow] {
        let blocked = rows.filter { $0.blockedBy != nil && $0.phase == .waiting }
        guard !blocked.isEmpty else { return rows }
        var out = rows.filter { !($0.blockedBy != nil && $0.phase == .waiting) }
        var needs: [String: Int] = [:]
        for row in blocked {
            let blocker = row.blockedBy ?? ""
            if let index = out.firstIndex(where: { ($0.ownJobId ?? $0.jobId) == blocker }) {
                out[index].children = (out[index].children ?? []) + [row]
            } else if let index = needs[blocker] {
                out[index].children?.append(row)
            } else {
                var need = ActivityMonitorRow(
                    id: "\(row.libraryId?.uuidString ?? "")|need:\(blocker)", kind: .job, libraryId: row.libraryId,
                    runRowID: nil, runThreadId: nil, jobId: nil, name: needName(blocker), projectName: row.projectName,
                    phase: .waiting, reason: row.reason, workingOn: nil, done: 0, total: 0, started: nil, seconds: nil,
                    costUsd: nil, tokens: 0, errors: 0, model: nil, isLive: false, children: [row])
                need.engineKind = "need"
                needs[blocker] = out.count
                out.append(need)
            }
        }
        return out
    }

    /// A typed need in words: "model:embeddings:bge-m3" is "Search model bge-m3", another runtime's model "Model
    /// <name>", a key "Key for <provider>", a folder "Folder <name>"; anything else as it is.
    static func needName(_ blocker: String) -> String {
        let parts = blocker.split(separator: ":", maxSplits: 2).map(String.init)
        switch (parts.first, parts.count) {
        case ("model", 3): return parts[1] == "embeddings" ? "Search model \(parts[2])" : "Model \(parts[2])"
        case ("model", 2): return "Model \(parts[1])"
        case ("key", 2): return "Key for \(parts[1])"
        case ("folder", 2): return "Folder \((parts[1] as NSString).lastPathComponent)"
        default: return blocker
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
