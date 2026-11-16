//
//  ActivityTrail.swift
//  Fichero
//
//  The one progress of a row and the one status bar of the table (`activity.pane.row-says-what-ran-on-what`,
//  `activity.pane.less-is-more-table`, #6441): "Import done → Segment done → Read 34/120 → Names waiting" and
//  "3 running · 12 waiting · $3.20 today". Pure text from the engine's counts; the views draw it.
//

import Foundation

enum ActivityTrail {
    /// One stage as one token: its title and its state in a word, the running one as its fraction.
    static func token(_ stage: ActivityJob.Stage) -> String {
        switch stage.state {
        // Words, not glyph characters (the SF-Symbols rule: the cell draws the state glyph itself, the text says the state).
        case "done", "completed": "\(stage.title) done"
        case "partial": "\(stage.title) done, some failed"
        case "running": stage.total > 0 ? "\(stage.title) \(stage.done)/\(stage.total)" : "\(stage.title) running"
        case "failed": "\(stage.title) failed"
        case "cancelled", "stopped": "\(stage.title) stopped"
        case "skipped", "not run": "\(stage.title) skipped"
        default: "\(stage.title) waiting"
        }
    }

    /// The trail: the stages in order, joined by arrows; empty for a row with no stages (a job of its own).
    static func text(_ stages: [ActivityJob.Stage]) -> String {
        stages.map(token).joined(separator: " → ")
    }

    /// The status bar, Finder style: counts as figures, the day's spend when any; never a sentence.
    static func statusBar(running: Int, waiting: Int, spentTodayUsd: Double?) -> String {
        var parts = ["\(running) running", "\(waiting) waiting"]
        if let spent = spentTodayUsd, spent > 0 { parts.append(String(format: "$%.2f today", spent)) }
        return parts.joined(separator: " · ")
    }

    /// "$0.42 · ~$1.10 more" for a running row; "$0.42" when ended; empty for local work or nothing priced (never "$0").
    static func cost(spentUsd: Double?, estimateUsd: Double?) -> String {
        guard let spent = spentUsd, spent > 0 else { return "" }
        var text = String(format: "$%.2f", spent)
        if let more = estimateUsd, more > 0 { text += String(format: " · ~$%.2f more", more) }
        return text
    }
}
