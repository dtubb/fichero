import Foundation
import SwiftUI

// A step's versions, the state glyph, the one column table and the row's words, split out of ActivityPane.swift
// (SwiftLint's size limits).

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
