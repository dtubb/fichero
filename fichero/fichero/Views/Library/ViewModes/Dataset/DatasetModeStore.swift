import Foundation
import Observation
import SwiftUI

// MARK: - Dataset mode (datasets Stage 2 — the renderer surface)

/// Which renderer the Data mode shows. Internal to the mode (ONE top-level
/// view mode, dead-simple UX) — cards / timeline / calendar / map.
enum DatasetRenderer: String, CaseIterable, Identifiable {
    case cards = "Cards"
    case timeline = "Timeline"
    case calendar = "Calendar"
    case map = "Map"

    var id: String { rawValue }

    var icon: String {
        switch self {
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

    /// Rows grouped by the date-role attribute's month ("1890-01"), sorted.
    /// Undated rows group under nil.
    func rowsByMonth() -> [(month: String?, rows: [DatasetPage.Row])] {
        guard let page, let dateAttr = attributeForRole["date"] else { return [] }
        var grouped: [String?: [DatasetPage.Row]] = [:]
        for row in page.rows {
            let date = text(dateAttr, of: row)
            let month = date.map { String($0.prefix(7)) }
            grouped[month, default: []].append(row)
        }
        return grouped
            .map { (month: $0.key, rows: $0.value) }
            .sorted { ($0.month ?? "\u{10FFFF}") < ($1.month ?? "\u{10FFFF}") }
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
