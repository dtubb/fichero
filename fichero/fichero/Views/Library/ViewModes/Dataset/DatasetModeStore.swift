import Foundation
import Observation
import SwiftUI

// MARK: - Dataset mode (datasets Stage 2 — the renderer surface)

/// Which renderer the Data mode shows. Internal to the mode (ONE top-level
/// view mode, dead-simple UX) — cards / timeline / calendar / map.
enum DatasetRenderer: String, CaseIterable, Identifiable {
    case grid = "Grid"
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

/// Loads one folder's dataset page + aggregates and derives the ROLE
/// bindings the renderers key on (spec §3.1: renderers read roles, never
/// prototype names).
@MainActor
@Observable
final class DatasetModeStore {
    var page: DatasetPage?
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
            var request = DatasetRequest(parentId: folderId, recursive: true, limit: 500)
            var loaded = try await service.datasetQuery(request)
            deriveRoles(from: loaded)
            if let dateAttr = attributeForRole["date"] {
                request.bins = (attr: dateAttr, granularity: "day")
                loaded = try await service.datasetQuery(request)
            }
            page = loaded
        } catch {
            errorText = error.localizedDescription
        }
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
        guard let page, let dateAttr = attributeForRole["date"] else { return [] }
        var grouped: [String: [DatasetPage.Row]] = [:]
        for row in page.rows {
            let month = text(dateAttr, of: row).map { String($0.prefix(7)) }
                ?? Self.undatedMonthKey
            grouped[month, default: []].append(row)
        }
        let undatedLast = "\u{10FFFF}"
        return grouped
            .map { group in
                // Within a month, entries run chronologically regardless of
                // the feed's order (ISO dates sort lexically).
                (month: group.key, rows: group.value.sorted {
                    (text(dateAttr, of: $0) ?? "", $0.name)
                        < (text(dateAttr, of: $1) ?? "", $1.name)
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
        var own = row.attributes
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
            attributes: attributes
        )
        var bins = page.bins
        if attr == attributeForRole["date"] {
            // Same shape the engine's day-granularity bins produce.
            var counts: [String: Int] = [:]
            for row in rows {
                if let date = text(attr, of: row), date.count >= 10 {
                    counts[String(date.prefix(10)), default: 0] += 1
                }
            }
            bins = counts.keys.sorted().map { .init(bin: $0, count: counts[$0] ?? 0) }
        }
        self.page = DatasetPage(
            total: page.total,
            offset: page.offset,
            rows: rows,
            defaultsByPrototype: page.defaultsByPrototype,
            bins: bins,
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
