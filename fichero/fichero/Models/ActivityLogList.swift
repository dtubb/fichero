import Foundation
import SwiftUI

/// The rules of the Inspector's log drawn as Xcode draws one (`activity.log.like-xcode`, decision 36, #6588): each level's
/// glyph, the lines a person selects, what Copy copies, and find. Pure, so each rule is tested without a view. The log is a
/// record: nothing here edits a line.
enum ActivityLogList {
    /// A level's glyph and its colour.
    struct Glyph: Equatable {
        let symbol: String
        let color: Color
    }

    static func glyph(_ level: String) -> Glyph {
        switch level.lowercased() {
        case "error", "critical": Glyph(symbol: "xmark.octagon.fill", color: .red)
        case "warning", "warn": Glyph(symbol: "exclamationmark.triangle.fill", color: .yellow)
        case "debug": Glyph(symbol: "ladybug", color: .secondary)
        default: Glyph(symbol: "info.circle", color: .secondary)
        }
    }

    /// The lines selected, as a list selects them: a click picks one, shift extends from the last click, command adds or
    /// removes one.
    struct Selection: Equatable {
        private(set) var lines: Set<Int> = []
        private var anchor: Int?

        mutating func click(_ line: Int, shift: Bool, command: Bool) {
            if shift, let anchor {
                lines = Set(min(anchor, line)...max(anchor, line))
            } else if command {
                if lines.contains(line) { lines.remove(line) } else { lines.insert(line) }
                anchor = line
            } else {
                lines = [line]
                anchor = line
            }
        }

        mutating func clear() {
            lines = []
            anchor = nil
        }
    }

    /// What Copy copies: the selected lines in the log's order, or the whole log when none is selected.
    static func copyText(_ lines: [ActivityJobLogLine], selected: Set<Int>) -> String {
        let chosen = selected.isEmpty ? lines : lines.filter { selected.contains($0.id) }
        return chosen.map(\.plainText).joined(separator: "\n")
    }

    /// A line's time as the person's log reads it (`activity.log.person-reads-like-a-copy-history`): local time with no date, and the
    /// date only on the first line of a new day; "now" for a line with no time.
    static func timeWords(_ date: Date?, after previous: Date?, calendar: Calendar = .current) -> String {
        guard let date else { return "now" }
        let time = date.formatted(date: .omitted, time: .standard)
        guard let previous, !calendar.isDate(date, inSameDayAs: previous) else { return time }
        return "\(date.formatted(.dateTime.day().month(.abbreviated))), \(time)"
    }

    /// The lines whose text holds the query, whatever its case; none for a blank query.
    static func matches(_ lines: [ActivityJobLogLine], query: String) -> [Int] {
        let wanted = query.trimmingCharacters(in: .whitespaces)
        guard !wanted.isEmpty else { return [] }
        return lines.filter { $0.message.localizedCaseInsensitiveContains(wanted) }.map(\.id)
    }

    /// "2 of 5", or "No match".
    static func matchWords(current: Int, of count: Int) -> String {
        count == 0 ? "No match" : "\(current + 1) of \(count)"
    }

    /// The next (or previous) match, round from the last to the first.
    static func step(_ current: Int, of count: Int, forward: Bool) -> Int {
        guard count > 0 else { return 0 }
        return (current + (forward ? 1 : count - 1)) % count
    }

    /// The line's text with every occurrence of the query marked, as Xcode's find marks it.
    static func highlighted(_ text: String, query: String) -> AttributedString {
        var marked = AttributedString(text)
        let wanted = query.trimmingCharacters(in: .whitespaces)
        guard !wanted.isEmpty else { return marked }
        var searchFrom = marked.startIndex
        while searchFrom < marked.endIndex,
              let range = marked[searchFrom...].range(of: wanted, options: .caseInsensitive) {
            marked[range].backgroundColor = .yellow.opacity(0.45)
            searchFrom = range.upperBound
        }
        return marked
    }
}
