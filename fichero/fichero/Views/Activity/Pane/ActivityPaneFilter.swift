//
//  ActivityPaneFilter.swift
//  Fichero
//
//  The Activity pane's one filter field (`activity.pane.history-kept-and-filterable`, #6441): tokens typed as
//  `key: value`, ANDed, over both groupings, remembered per pane. Pure, so the grammar is tested without a view.
//

import Foundation

struct ActivityPaneFilter: Equatable {
    enum Key: String, CaseIterable {
        case recipe, step, model, state, date, file
        case startedBy = "started by"
    }

    struct Token: Equatable {
        /// nil: plain text, matched against the name.
        let key: Key?
        let value: String
    }

    let tokens: [Token]

    var isEmpty: Bool { tokens.isEmpty }

    /// "model: Kraken state: failed letters" → model Kraken, state failed, text "letters". A key the grammar does not
    /// know is plain text; an empty value is dropped.
    init(_ text: String) {
        var tokens: [Token] = []
        var rest = Substring(text)
        var plain: [String] = []
        while !rest.isEmpty {
            rest = rest.drop(while: \.isWhitespace)
            if let (key, after) = Self.leadingKey(rest) {
                let value = after.drop(while: \.isWhitespace)
                let end = Self.nextKeyStart(value) ?? value.endIndex
                let words = value[..<end].trimmingCharacters(in: .whitespaces)
                if !words.isEmpty { tokens.append(Token(key: key, value: words)) }
                rest = value[end...]
            } else {
                let word = rest.prefix(while: { !$0.isWhitespace })
                if !word.isEmpty { plain.append(String(word)) }
                rest = rest.dropFirst(word.count)
            }
        }
        if !plain.isEmpty { tokens.append(Token(key: nil, value: plain.joined(separator: " "))) }
        self.tokens = tokens
    }

    private static func leadingKey(_ text: Substring) -> (Key, Substring)? {
        let lower = text.lowercased()
        for key in Key.allCases where lower.hasPrefix(key.rawValue + ":") {
            return (key, text.dropFirst(key.rawValue.count + 1))
        }
        return nil
    }

    private static func nextKeyStart(_ text: Substring) -> Substring.Index? {
        var index = text.startIndex
        while index < text.endIndex {
            if text[index].isWhitespace {
                let after = text[text.index(after: index)...]
                if leadingKey(after) != nil { return index }
            }
            index = text.index(after: index)
        }
        return nil
    }

    // MARK: - Matching

    /// A row matches when every token does; a row whose children match is kept for them (the outline shows the way in).
    func apply(_ rows: [ActivityMonitorRow], now: Date = Date(), calendar: Calendar = .current) -> [ActivityMonitorRow] {
        guard !isEmpty else { return rows }
        return rows.compactMap { row in
            if matches(row, now: now, calendar: calendar) { return row }
            let kept = apply(row.children ?? [], now: now, calendar: calendar)
            guard !kept.isEmpty else { return nil }
            var row = row
            row.children = kept
            return row
        }
    }

    func matches(_ row: ActivityMonitorRow, now: Date = Date(), calendar: Calendar = .current) -> Bool {
        tokens.allSatisfy { token in Self.matches(token, row, now: now, calendar: calendar) }
    }

    private static func matches(_ token: Token, _ row: ActivityMonitorRow, now: Date, calendar: Calendar) -> Bool {
        let value = token.value
        func has(_ text: String?) -> Bool { text?.localizedCaseInsensitiveContains(value) ?? false }
        switch token.key {
        case nil, .recipe: return has(row.name)
        case .step: return has(row.trail) || has(row.workingOn) || has(row.name)
        case .model: return has(row.model)
        case .state: return has(ActivityPane.glyph(row).word) || has(row.phase.word) || has(row.stateText)
        case .file: return has(row.name) || ActivityPane.leaves(of: row).contains { has($0.name) } || has(row.ranOnText)
        case .startedBy: return has(row.source.word) || has(row.startedBy)
        case .date: return dateMatches(value, row.started ?? row.ended, now: now, calendar: calendar)
        }
    }

    /// `today`, `YYYY-MM-DD`, or `YYYY-MM-DD..YYYY-MM-DD` (both days included) against when the row started.
    static func dateMatches(_ value: String, _ date: Date?, now: Date, calendar: Calendar) -> Bool {
        guard let date else { return false }
        if value.lowercased() == "today" { return calendar.isDate(date, inSameDayAs: now) }
        let parts = value.components(separatedBy: "..").map { $0.trimmingCharacters(in: .whitespaces) }
        // The day in the person's own calendar (an ISO parse is a GMT midnight, a day early west of Greenwich).
        let days = parts.compactMap { part -> Date? in
            let numbers = part.split(separator: "-").compactMap { Int($0) }
            guard numbers.count == 3 else { return nil }
            return calendar.date(from: DateComponents(year: numbers[0], month: numbers[1], day: numbers[2]))
        }
        guard days.count == parts.count, let first = days.first, let last = days.last else { return false }
        let start = calendar.startOfDay(for: first)
        guard let end = calendar.date(byAdding: .day, value: 1, to: calendar.startOfDay(for: last)) else { return false }
        return date >= start && date < end
    }
}
