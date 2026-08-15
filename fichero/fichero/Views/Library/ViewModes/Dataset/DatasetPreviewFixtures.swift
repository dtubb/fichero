import Foundation

// MARK: - Preview fixtures (datasets Stage 2)

/// Fixture data for the renderer previews — the REAL diary shape (a
/// transcribed diary book split into dated entries) so the views can be
/// polished visually without the engine (Daniel 2026-08-14: "use xcode
/// preview for the various views so you can get them visually good,
/// without having to work about data layer").
extension DatasetPage {
    static var previewDiary: DatasetPage {
        let weather = ["fair", "rain", "fog", "snow"]
        var rows: [Row] = []
        var binCounts: [String: Int] = [:]
        // Two months of 1942 with realistic gaps: entries on roughly every
        // other day, an occasional two-entry day.
        for (index, day) in [1, 2, 4, 5, 7, 10, 11, 14, 17, 21, 22, 25, 28].enumerated() {
            let date = String(format: "1942-01-%02d", day)
            rows.append(Row(
                id: "jan\(day)",
                name: date,
                prototypeKey: "diary_entry",
                attributes: [
                    "date": date,
                    "weather": weather[index % weather.count],
                    "temperature": Double(28 + index),
                    "place": index % 3 == 0 ? "Quibdó" : "Istmina",
                    "geo": index % 3 == 0 ? "5.69,-76.66" : "5.16,-76.68"
                ],
                excerpt: "Rained in the morning, cleared by noon. Took the canoe "
                    + "downriver with Don Pedro and traded for plantains.",
                parentId: "page-img-\(day)"
            ))
            binCounts[date, default: 0] += 1
        }
        // A second entry on Jan 4 — the calendar's ">1" count chip needs a
        // day to show on.
        rows.append(Row(
            id: "jan4-second",
            name: "1942-01-04 (later)",
            prototypeKey: "diary_entry",
            attributes: ["date": "1942-01-04", "weather": "rain", "place": "Andagoya"],
            excerpt: "Evening: reached Andagoya after dark; the launch was late."
        ))
        binCounts["1942-01-04", default: 0] += 1
        for day in [3, 6, 9, 12, 18, 23] {
            let date = String(format: "1942-02-%02d", day)
            rows.append(Row(
                id: "feb\(day)",
                name: date,
                prototypeKey: "diary_entry",
                attributes: ["date": date, "weather": weather[day % weather.count]]
            ))
            binCounts[date, default: 0] += 1
        }
        // The honesty row every renderer must survive: an entry whose date
        // never parsed (kept, never guessed). No bare page-image row — the
        // engine's attributed_only scope excludes those from data views, so
        // the fixture matches the live feed.
        // An Extract-Dates document: no attributes, no prototype — its date
        // lives on the document's own date columns.
        rows.append(Row(
            id: "dated-scan",
            name: "scan_007.png",
            prototypeKey: nil,
            attributes: [:],
            dateOriginal: "Jan. 30th 1942",
            dateIso: "1942-01-30"
        ))
        binCounts["1942-01-30", default: 0] += 1
        rows.append(Row(
            id: "undated",
            name: "primero de enero (unreadable)",
            prototypeKey: "diary_entry",
            attributes: ["weather": "fair"]
        ))
        var facetCounts: [String: Int] = [:]
        for row in rows {
            if let value = row.attributes["weather"] as? String {
                facetCounts[value, default: 0] += 1
            }
        }
        return DatasetPage(
            total: rows.count,
            offset: 0,
            rows: rows,
            defaultsByPrototype: [
                "diary_entry": [
                    "date": ["type": "date", "role": "date"] as [String: (any Sendable)?],
                    "weather": ["type": "text"] as [String: (any Sendable)?],
                    "temperature": ["type": "number"] as [String: (any Sendable)?],
                    "place": ["type": "text", "role": "title"] as [String: (any Sendable)?],
                    "geo": ["type": "text", "role": "geo"] as [String: (any Sendable)?]
                ]
            ],
            bins: binCounts.keys.sorted().map { .init(bin: $0, count: binCounts[$0] ?? 0) },
            facets: ["weather": facetCounts.keys.sorted().map {
                .init(value: $0, count: facetCounts[$0] ?? 0)
            }]
        )
    }
}

extension DatasetModeStore {
    /// A store preloaded with the diary fixture — previews mount the
    /// renderer views directly against it; `load` is never called.
    static func previewDiary(page: DatasetPage = .previewDiary) -> DatasetModeStore {
        let store = DatasetModeStore()
        store.page = page
        store.attributeForRole = ["date": "date", "geo": "geo", "title": "place"]
        store.declaredAttributes = ["date", "geo", "place", "temperature", "weather"]
        return store
    }
}
