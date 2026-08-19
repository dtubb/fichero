import Foundation
import Observation
import SwiftUI

// MARK: - Dataset mode (datasets Stage 2 — the renderer surface)

/// Which renderer the Data mode shows. Internal to the mode (ONE top-level
/// view mode, dead-simple UX) — cards / timeline / calendar / map.
enum DatasetRenderer: String, CaseIterable, Identifiable {
    case grid = "Sheet"
    case cards = "Cards"
    case timeline = "Timeline"
    case calendar = "Calendar"
    case map = "Map"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .grid: "tablecells.badge.ellipsis"
        case .cards: "rectangle.grid.2x2"
        case .timeline: "chart.bar.xaxis"
        case .calendar: "calendar"
        case .map: "mappin.and.ellipse"
        }
    }
}

/// The date facet over loaded rows (Daniel 2026-08-15: "can we easily
/// filter undated"). Client-side over the page in memory — the engine's
/// typed-filter shape stays available when paging outgrows this.
enum DatasetDateFilter: String, CaseIterable, Identifiable {
    case all = "All"
    case dated = "Dated"
    case undated = "Undated"

    var id: String { rawValue }
}

/// Loads one folder's dataset page + aggregates and derives the ROLE
/// bindings the renderers key on (spec §3.1: renderers read roles, never
/// prototype names).
@MainActor
@Observable
final class DatasetModeStore {
    var page: DatasetPage?

    /// Row facets every renderer shares (via `visibleRows`), so a filter
    /// choice follows the user between cards, timeline and calendar.
    var dateFilter: DatasetDateFilter = .all
    /// nil = every prototype; "pull quotes in a folder" is this facet set
    /// to `pull_quote` — no special casing per prototype.
    var prototypeFilter: String?
    /// Cards' text depth — stored HERE (extensions cannot hold storage);
    /// the TextDetail enum and display helpers live in +Display.swift.
    var textDetail: TextDetail = .excerpt
    var isLoading = false
    var errorText: String?
    /// A failed EDIT, shown transiently in the header — never the full-pane
    /// error state, which would blank rows that are still perfectly valid.
    var editErrorText: String?

    /// role → attribute name, from the page's prototype declarations. When
    /// prototypes disagree, the first (sorted-key) declaration wins — a page
    /// usually shares one prototype; disagreements render per-row anyway.
    var attributeForRole: [String: String] = [:]

    /// Attribute names declared anywhere on this page, sorted — the cards'
    /// caption source and (later) the grid's column source.
    var declaredAttributes: [String] = []

    func load(folderId: String?, service: DocumentService) async {
        isLoading = true
        defer { isLoading = false }
        errorText = nil
        do {
            // First pass without bins: the date attribute is only known after
            // the declarations arrive.
            var request = DatasetRequest(parentId: folderId, recursive: true,
                                         attributedOnly: true, limit: 500)
            var loaded = try await service.datasetQuery(request)
            if loaded.rows.isEmpty, let folderId {
                // A LEAF selection (a diary entry, a single page) scopes to
                // its own children — none. The dataset it BELONGS to is its
                // parent's: re-scope one level up so selecting an entry shows
                // the day's siblings instead of a blank pane
                // (Daniel 2026-08-15: "library is blank").
                let bareId = folderId.hasPrefix("doc:") ? String(folderId.dropFirst(4)) : folderId
                if let selected = try? await service.getDocument(bareId),
                   let parentId = selected.parentId {
                    request.parentId = parentId
                    loaded = try await service.datasetQuery(request)
                }
            }
            deriveRoles(from: loaded)
            if let dateAttr = attributeForRole["date"] {
                request.bins = (attr: dateAttr, granularity: "day")
                loaded = try await service.datasetQuery(request)
            } else if loaded.rows.contains(where: { $0.dateIso != nil }) {
                // Extract Dates writes date COLUMNS, not attributes — the
                // engine's bins are attribute-keyed, so derive day bins
                // locally from the rows' own ISO dates (Daniel 2026-08-15:
                // "I run extract dates … I don't see it").
                loaded = Self.withLocalDayBins(loaded, dateOf: { $0.dateIso })
            }
            page = loaded
        } catch {
            errorText = error.localizedDescription
        }
    }

    /// The rows the renderers draw: the loaded page through the active
    /// facets. Filtering here (not per-renderer) keeps the five renderers
    /// answering the same question the same way.
    var visibleRows: [DatasetPage.Row] {
        guard let page else { return [] }
        return page.rows.filter { row in
            switch dateFilter {
            case .all: break
            case .dated: guard dateValue(of: row) != nil else { return false }
            case .undated: guard dateValue(of: row) == nil else { return false }
            }
            if let prototypeFilter, row.prototypeKey != prototypeFilter {
                return false
            }
            return true
        }
    }

    /// Distinct prototypes on this page, sorted — the Type facet's options.
    var availablePrototypes: [String] {
        Set((page?.rows ?? []).compactMap(\.prototypeKey)).sorted()
    }

    /// The renderers have a date to work with: a date-role attribute, or
    /// any row carrying its document's own extracted/asserted date.
    var hasDateSource: Bool {
        attributeForRole["date"] != nil
            || page?.rows.contains(where: { $0.dateIso != nil }) == true
    }

    /// A row's date for grouping/binning: the date-role attribute when
    /// declared, else the document's own converted ISO date.
    func dateValue(of row: DatasetPage.Row) -> String? {
        if let dateAttr = attributeForRole["date"], let value = text(dateAttr, of: row) {
            return value
        }
        return row.dateIso
    }

    /// A page with day-granularity bins recomputed from `dateOf` — the same
    /// shape the engine's attribute-keyed bins produce.
    static func withLocalDayBins(
        _ page: DatasetPage,
        dateOf: (DatasetPage.Row) -> String?
    ) -> DatasetPage {
        var counts: [String: Int] = [:]
        for row in page.rows {
            if let date = dateOf(row), date.count >= 10 {
                counts[String(date.prefix(10)), default: 0] += 1
            }
        }
        return DatasetPage(
            total: page.total,
            offset: page.offset,
            rows: page.rows,
            defaultsByPrototype: page.defaultsByPrototype,
            bins: counts.keys.sorted().map { .init(bin: $0, count: counts[$0] ?? 0) },
            facets: page.facets
        )
    }

    private func deriveRoles(from page: DatasetPage) {
        var roles: [String: String] = [:]
        var declared: Set<String> = []
        for key in page.defaultsByPrototype.keys.sorted() {
            for (name, raw) in page.defaultsByPrototype[key] ?? [:] {
                guard name != "_unresolved" else { continue }
                declared.insert(name)
                if let dict = raw as? [String: (any Sendable)?],
                   let role = dict["role"] as? String,
                   roles[role] == nil {
                    roles[role] = name
                }
            }
        }
        attributeForRole = roles
        declaredAttributes = declared.sorted()
    }

    /// Display string for a row's effective value of one attribute.
    func text(_ attr: String, of row: DatasetPage.Row) -> String? {
        guard let page else { return nil }
        guard let value = page.effectiveValue(attr, of: row) else { return nil }
        switch value {
        case let string as String: return string.isEmpty ? nil : string
        case let bool as Bool: return bool ? "Yes" : "No"
        case let int as Int: return String(int)
        case let double as Double:
            return double == double.rounded() ? String(Int(double)) : String(double)
        default: return String(describing: value)
        }
    }

    /// The sentinel month key for rows with no date value — non-optional so
    /// List section ids stay plain Strings (an Optional section id crashed
    /// SwiftUI's outline bookkeeping in the timeline preview, 2026-08-14).
    static let undatedMonthKey = "undated"

    /// Rows grouped by the date-role attribute's month ("1890-01"), sorted,
    /// undated rows last under `undatedMonthKey`.
    func rowsByMonth() -> [(month: String, rows: [DatasetPage.Row])] {
        guard page != nil, hasDateSource else { return [] }
        var grouped: [String: [DatasetPage.Row]] = [:]
        for row in visibleRows {
            let month = dateValue(of: row).map { String($0.prefix(7)) }
                ?? Self.undatedMonthKey
            grouped[month, default: []].append(row)
        }
        let undatedLast = "\u{10FFFF}"
        return grouped
            .map { group in
                // Within a month, entries run chronologically regardless of
                // the feed's order (ISO dates sort lexically).
                (month: group.key, rows: group.value.sorted {
                    (dateValue(of: $0) ?? "", $0.name)
                        < (dateValue(of: $1) ?? "", $1.name)
                })
            }
            .sorted {
                ($0.month == Self.undatedMonthKey ? undatedLast : $0.month)
                    < ($1.month == Self.undatedMonthKey ? undatedLast : $1.month)
            }
    }

    /// Persist one attribute edit through the engine, then apply it in
    /// place. The row only moves when the engine accepted the value.
    func saveAttribute(
        _ attr: String,
        value: (any Sendable)?,
        on row: DatasetPage.Row,
        entityService: EntityService
    ) async {
        editErrorText = nil
        // Re-resolve the row by id: the caller's copy may predate an edit
        // already applied (two grid cells committed back-to-back), and the
        // PUT replaces the WHOLE own-attributes dict — a stale base would
        // silently revert the earlier edit.
        let current = page?.rows.first { $0.id == row.id } ?? row
        var own = current.attributes
        own[attr] = value
        do {
            try await entityService.updateDocumentAttributes(documentId: row.id, attributes: own)
            applyLocalEdit(rowId: row.id, attr: attr, value: value)
        } catch {
            editErrorText = error.localizedDescription
        }
    }

    /// Apply one row's attribute edit IN PLACE: replace that row, and when
    /// the edited attribute carries the date role, re-derive the day bins
    /// locally so the calendar/timeline move the entry without a reload
    /// (project rule: no wholesale list re-render).
    ///
    /// Pure local mutation — callers persist through
    /// `EntityService.updateDocumentAttributes` FIRST and only apply on
    /// success, so the UI never shows a value the engine rejected.
    func applyLocalEdit(rowId: String, attr: String, value: (any Sendable)?) {
        guard let page, let index = page.rows.firstIndex(where: { $0.id == rowId }) else {
            return
        }
        var attributes = page.rows[index].attributes
        attributes[attr] = value
        var rows = page.rows
        let old = rows[index]
        rows[index] = DatasetPage.Row(
            id: old.id,
            name: old.name,
            prototypeKey: old.prototypeKey,
            attributes: attributes,
            excerpt: old.excerpt,
            dateOriginal: old.dateOriginal,
            dateIso: old.dateIso,
            // Optional vars default to nil in the memberwise init — omitting
            // this silently severed an edited row's source reference
            // (found in the 2026-08-15 filter review).
            parentId: old.parentId
        )
        let updated = DatasetPage(
            total: page.total,
            offset: page.offset,
            rows: rows,
            defaultsByPrototype: page.defaultsByPrototype,
            bins: page.bins,
            facets: page.facets
        )
        if attr == attributeForRole["date"] {
            // Re-derive day bins from EVERY date source — the edited
            // attribute AND rows carrying their document's own ISO date
            // (dropping the latter would empty their calendar days).
            self.page = Self.withLocalDayBins(updated) { row in
                if let value = self.text(attr, of: row) { return value }
                return row.dateIso
            }
        } else {
            self.page = updated
        }
    }

    /// Persist a TEXT edit through the engine, then apply it in place.
    ///
    /// The update route stamps ``page_content_user_edited_at`` on every
    /// page_content write (#672), so a sheet-cell edit gets the same
    /// machine-rerun protection as the reader's editor — the curation guard
    /// will never let a re-transcription clobber it.
    func saveText(_ text: String, on row: DatasetPage.Row, service: DocumentService) async {
        editErrorText = nil
        do {
            _ = try await service.updateDocument(row.id, pageContent: text)
            applyLocalText(rowId: row.id, text: text)
        } catch {
            editErrorText = error.localizedDescription
        }
    }

    /// In-place excerpt swap after a persisted text edit — one row, no
    /// wholesale re-render, source reference intact.
    func applyLocalText(rowId: String, text: String) {
        guard let page, let index = page.rows.firstIndex(where: { $0.id == rowId }) else {
            return
        }
        var rows = page.rows
        let old = rows[index]
        rows[index] = DatasetPage.Row(
            id: old.id,
            name: old.name,
            prototypeKey: old.prototypeKey,
            attributes: old.attributes,
            excerpt: String(text.prefix(800)),
            dateOriginal: old.dateOriginal,
            dateIso: old.dateIso,
            parentId: old.parentId
        )
        self.page = DatasetPage(
            total: page.total,
            offset: page.offset,
            rows: rows,
            defaultsByPrototype: page.defaultsByPrototype,
            bins: page.bins,
            facets: page.facets
        )
    }

    /// "January 4, 1942" from a "YYYY-MM-DD" (or longer ISO) string —
    /// the renderers' shared date presentation. Nil when unparseable so
    /// callers fall back to the raw text, never hide it.
    nonisolated static func longDate(_ raw: String) -> String? {
        let pieces = raw.prefix(10).split(separator: "-")
        guard pieces.count == 3, let month = Int(pieces[1]),
              (1...12).contains(month), let day = Int(pieces[2]) else { return nil }
        return "\(Calendar.current.monthSymbols[month - 1]) \(day), \(pieces[0])"
    }

    /// "lat,lon" (or "lat, lon") parse of the geo-role attribute.
    func coordinate(of row: DatasetPage.Row) -> (lat: Double, lon: Double)? {
        guard let geoAttr = attributeForRole["geo"],
              let raw = text(geoAttr, of: row) else { return nil }
        let parts = raw.split(separator: ",").map {
            Double($0.trimmingCharacters(in: .whitespaces))
        }
        guard parts.count == 2, let lat = parts[0], let lon = parts[1],
              abs(lat) <= 90, abs(lon) <= 180 else { return nil }
        return (lat, lon)
    }
}
