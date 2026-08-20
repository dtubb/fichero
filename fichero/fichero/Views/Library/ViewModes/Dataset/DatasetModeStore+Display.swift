import Foundation

// MARK: - Display shaping (split from DatasetModeStore.swift at the
// 400-line limit, 2026-08-15 night — same members, only the file moved)

extension DatasetModeStore {
    /// How much of a row's text the cards show (Daniel 2026-08-15 night:
    /// "I want to be able to see full diary entry. or at least more of it").
    enum TextDetail: String, CaseIterable, Identifiable {
        case excerpt = "Excerpt"
        case full = "Full Text"

        var id: String { rawValue }
    }

    /// `visibleRows` in DATE-then-name order — the cards/grid feed. The feed
    /// arrives in engine listing order, which is not a promise; a data view
    /// over dated rows reads as broken unless it is chronological (Daniel
    /// 2026-08-15 night: "its not in order though. that's the first thing").
    /// Undated rows sort last, matching the timeline's sections.
    var orderedVisibleRows: [DatasetPage.Row] {
        // Memoized (log audit 2026-08-19: up to 2.1s stalls — this getter is
        // read per body evaluation, and the sort computed dateValue +
        // localizedLowercase PER COMPARISON over 500 rows). Sort keys are
        // precomputed once; the result is cached until the inputs change.
        let key = OrderedRowsCacheKey(
            revision: displayRevision,
            dateFilter: dateFilter,
            prototypeFilter: prototypeFilter
        )
        if let cached = orderedRowsCache, cached.key == key { return cached.rows }
        let undatedLast = "\u{10FFFF}"
        let keyed = visibleRows.map {
            (row: $0, date: dateValue(of: $0) ?? undatedLast, name: $0.name.localizedLowercase)
        }
        let rows = keyed
            .sorted { ($0.date, $0.name) < ($1.date, $1.name) }
            .map(\.row)
        orderedRowsCache = (key, rows)
        return rows
    }

    /// A row's text for display: the excerpt with a LEADING date-heading line
    /// removed when it repeats the date the card already shows ("February 15,
    /// 1914" over a body starting "SATURDAY, FEBRUARY 15"). Display-side so
    /// entries extracted before the engine learned to strip headings stop
    /// repeating too — the stored text is never rewritten.
    func displayExcerpt(of row: DatasetPage.Row) -> String? {
        guard let excerpt = row.excerpt else { return nil }
        guard let date = dateValue(of: row) else { return excerpt }
        let stripped = Self.strippingLeadingDateHeading(excerpt, dateIso: date)
        return stripped.isEmpty ? nil : stripped
    }

    /// Drop the first line when it reads as a date heading for `dateIso`:
    /// it names the entry's month AND either its day number or any weekday —
    /// covering the diaries' printed headers with OCR noise ("TUESDAY,
    /// JANUARY § 7", "MONDAY. JANUARY F. 19186 3"). A first line that is
    /// prose mentioning the month keeps its length; headings are short.
    nonisolated static func strippingLeadingDateHeading(
        _ text: String, dateIso: String
    ) -> String {
        let pieces = dateIso.prefix(10).split(separator: "-")
        guard pieces.count == 3, let month = Int(pieces[1]),
              (1...12).contains(month) else { return text }
        guard !text.isEmpty else { return text }
        let firstNewline = text.firstIndex(of: "\n")
        let firstLine = String(text[..<(firstNewline ?? text.endIndex)])
        guard firstLine.count <= 60 else { return text }
        // Headings are PRINTED — the diaries set them in caps. Prose that
        // happens to name the month and day ("We spent February 15 at the
        // dredge") is mixed-case and stays.
        let letters = firstLine.filter(\.isLetter)
        guard !letters.isEmpty,
              letters.filter(\.isUppercase).count * 10 >= letters.count * 9
        else { return text }
        let tokens = firstLine.lowercased()
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { !$0.isEmpty }
        let monthName = Calendar.current.monthSymbols[month - 1].lowercased()
        guard tokens.contains(monthName) else { return text }
        let weekdays = Set(Calendar.current.weekdaySymbols.map { $0.lowercased() })
        let day = pieces[2].drop(while: { $0 == "0" })
        let namesDay = tokens.contains(String(day))
        let namesWeekday = tokens.contains { weekdays.contains($0) }
        guard namesDay || namesWeekday else { return text }
        guard let firstNewline else { return "" }
        return text[text.index(after: firstNewline)...]
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}


/// Cache key for `orderedVisibleRows` — page revision plus the two facets
/// the visible set depends on.
struct OrderedRowsCacheKey: Equatable {
    let revision: Int
    let dateFilter: DatasetDateFilter
    let prototypeFilter: String?
}
