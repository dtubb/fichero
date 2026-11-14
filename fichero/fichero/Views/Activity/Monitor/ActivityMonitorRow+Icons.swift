//
//  ActivityMonitorRow+Icons.swift
//  Fichero
//
//  Icons say where work came from and what kind of step it is (`activity.pane.icons-say-source-and-kind`, #6441; owner
//  2026-11-13): one small icon column, the word in the tooltip and the accessibility label, never a text column.
//

import Foundation

extension ActivityMonitorRow {
    /// Where the work came from, from the engine's `started_by`.
    enum Source: String {
        case person, automatic, recipe, schedule

        var symbol: String {
            switch self {
            case .person: "person"
            case .automatic: "gearshape.arrow.triangle.2.circlepath"
            case .recipe: "list.bullet.rectangle"
            case .schedule: "clock"
            }
        }

        var word: String {
            switch self {
            case .person: "Started by you"
            case .automatic: "Automatic"
            case .recipe: "A recipe's step"
            case .schedule: "A schedule or trigger"
            }
        }
    }

    /// The source of a row, read from the engine's `started_by` in one place: "automatic", "import" and the derivative
    /// kinds are automatic; "schedule:…" and "trigger:…" a schedule; "workflow" and "read-again:…" a recipe's or run's own
    /// step; anything else named is a person.
    static func source(startedBy: String?) -> Source {
        guard let startedBy, !startedBy.isEmpty else { return .person }
        let lower = startedBy.lowercased()
        if lower == "automatic" || lower == "import" || lower == "derivatives" { return .automatic }
        if lower.hasPrefix("schedule") || lower.hasPrefix("trigger") { return .schedule }
        if lower == "workflow" || lower == "recipe" || lower.hasPrefix("read-again") { return .recipe }
        return .person
    }

    /// The kind of step, from the engine's `task_type`: an SF Symbol and its word; nil for a kind with no glyph.
    static func kindSymbol(engineKind: String?) -> (symbol: String, word: String)? {
        guard let kind = engineKind?.lowercased(), !kind.isEmpty else { return nil }
        if kind.hasPrefix("kraken") { return ("scribble", "Kraken") }
        if kind.hasPrefix("read-") || kind == "ask-a-model" || kind == "transcribe" { return ("text.viewfinder", "Reading") }
        if kind.hasPrefix("find-lines") || kind.hasPrefix("find-regions") || kind == "put-in-order" || kind == "refine-shapes" {
            return ("rectangle.split.3x1", "Segmenting")
        }
        if kind.hasPrefix("find-names") || kind.hasPrefix("find-statements") || kind == "work-out-dates" || kind == "nlp-draft" {
            return ("person.text.rectangle", "Names and statements")
        }
        if kind == "thumbnail" { return ("photo", "Thumbnails") }
        if kind.hasPrefix("embed") { return ("magnifyingglass", "Search") }
        if kind.hasPrefix("download") || kind == "model-download" { return ("arrow.down.circle", "Downloading a model") }
        if kind == "run-a-recipe" || kind == "workflow" || kind == "batch" { return ("list.bullet.rectangle", "A run") }
        return nil
    }

    var source: Source { Self.source(startedBy: startedBy) }
    var kindGlyph: (symbol: String, word: String)? { Self.kindSymbol(engineKind: engineKind) }
}
