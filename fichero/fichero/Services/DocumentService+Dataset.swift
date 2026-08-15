import FicheroAPIClient
import Foundation
import OpenAPIRuntime

// MARK: - Dataset query (datasets Stage 2 — the renderer feed)

/// One page of a folder's attribute-bearing rows plus the aggregate shapes
/// the renderers key on. Decoded from the open-schema response of
/// POST /api/documents/dataset/query.
struct DatasetPage {
    struct Row: Identifiable {
        let id: String
        let name: String
        let prototypeKey: String?
        let attributes: [String: (any Sendable)?]
        /// The row's own text, page-sized by the engine (280 chars) — the
        /// entry's transcript, so data views never show "just dates".
        var excerpt: String?
        /// The document's OWN date (Extract Dates / user assertion): the
        /// text as written, and the converted Gregorian ISO the renderers
        /// bin on when no date-role attribute exists.
        var dateOriginal: String?
        var dateIso: String?
        /// The REFERENCE (Daniel 2026-08-15 ruling): an extracted node
        /// always points back at its source page — one click away.
        var parentId: String?
    }

    struct Bin: Identifiable {
        let bin: String
        let count: Int
        var id: String { bin }
    }

    struct FacetValue: Identifiable {
        let value: String
        let count: Int
        var id: String { value }
    }

    let total: Int
    let offset: Int
    let rows: [Row]
    /// Chain-merged prototype attributes (typed declarations AND legacy plain
    /// defaults) per prototype on this page — the client-side overlay source.
    /// A prototype that no longer resolves carries `_unresolved` (a String).
    let defaultsByPrototype: [String: [String: (any Sendable)?]]
    let bins: [Bin]
    let facets: [String: [FacetValue]]

    /// A row's effective value: its own, else the prototype default (which
    /// for a typed declaration dict is its "default" field).
    func effectiveValue(_ attr: String, of row: Row) -> (any Sendable)? {
        if let own = row.attributes[attr], own != nil { return own }
        guard let key = row.prototypeKey,
              let declared = defaultsByPrototype[key]?[attr] else { return nil }
        if let dict = declared as? [String: (any Sendable)?] {
            return dict["default"] ?? nil
        }
        return declared
    }
}

/// One typed filter, mirrored onto the engine's DatasetFilter model.
struct DatasetFilterSpec {
    var attr: String
    var operation: String
    var value: (any Sendable)?
    var type = "text"
}

/// The request, mirrored 1:1 onto the engine's DatasetQuery model.
struct DatasetRequest {
    var parentId: String?
    var recursive = false
    var prototypeKey: String?
    /// Only rows that CARRY data (a prototype or attributes) — the data
    /// views' scope; bare page images stay in the Browse modes.
    var attributedOnly = false
    var filters: [DatasetFilterSpec] = []
    var sortAttr: String?
    var sortDescending = false
    var sortType = "text"
    var limit = 100
    var offset = 0
    /// Non-nil requests date bins: ("date", "month"|"year"|"day").
    var bins: (attr: String, granularity: String)?
    var facets: [String] = []
}

extension DocumentService {
    /// POST /api/documents/dataset/query — server-side sort/filter/paging,
    /// date bins and facet counts over attribute JSON (Stage 2 ruling: plain
    /// json_extract, no promotion).
    private static func wireFilters(
        _ specs: [DatasetFilterSpec]
    ) throws -> [Components.Schemas.DatasetFilter]? {
        guard !specs.isEmpty else { return nil }
        return try specs.map { spec in
            guard let operation = Components.Schemas.DatasetFilter.OpPayload(rawValue: spec.operation) else {
                throw DocumentServiceError.serverError("Unknown filter op: \(spec.operation)")
            }
            return Components.Schemas.DatasetFilter(
                attr: spec.attr,
                op: operation,
                value: try spec.value.map { try OpenAPIValueContainer(unvalidatedValue: $0) },
                _type: spec.type
            )
        }
    }

    func datasetQuery(_ request: DatasetRequest) async throws -> DatasetPage {
        let filters = try Self.wireFilters(request.filters)
        let sort: Components.Schemas.DatasetSort? = request.sortAttr.map { attr in
            .init(
                attr: attr,
                direction: request.sortDescending ? .desc : .asc,
                _type: request.sortType
            )
        }
        let bins: Components.Schemas.DatasetBins? = request.bins.map { spec in
            .init(
                attr: spec.attr,
                granularity: .init(rawValue: spec.granularity) ?? .month
            )
        }
        let response = try await client.api.datasetQueryApiDocumentsDatasetQueryPost(
            body: .json(.init(
                parentId: request.parentId,
                recursive: request.recursive,
                prototypeKey: request.prototypeKey,
                attributedOnly: request.attributedOnly,
                filters: filters,
                sort: sort,
                limit: request.limit,
                offset: request.offset,
                bins: bins,
                facets: request.facets.isEmpty ? nil : request.facets
            ))
        )
        switch response {
        case .ok(let okResponse):
            return Self.datasetPage(
                from: try okResponse.body.json.additionalProperties.value
            )
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw DocumentServiceError.httpStatus(operation: "dataset query", code: statusCode)
        }
    }

    /// A container number regardless of how OpenAPIRuntime decoded it —
    /// JSON integers can surface as Int, Int64 or Double, and a bare
    /// `as? Int` silently drops them (live failure shape: "0 items" over a
    /// folder of entries).
    static func containerInt(_ value: (any Sendable)?) -> Int? {
        switch value {
        case let int as Int: return int
        case let int64 as Int64: return Int(int64)
        case let double as Double: return Int(double)
        default: return nil
        }
    }

    /// Lenient open-schema decode — pinned by shape, loud only through the
    /// totals (a malformed row drops; the count mismatch is the signal).
    static func datasetPage(from payload: [String: (any Sendable)?]) -> DatasetPage {
        let rawRows = payload["rows"] as? [(any Sendable)?] ?? []
        let rows: [DatasetPage.Row] = rawRows.compactMap { entry in
            guard let dict = entry as? [String: (any Sendable)?],
                  let id = dict["id"] as? String,
                  let name = dict["name"] as? String else { return nil }
            return DatasetPage.Row(
                id: id,
                name: name,
                prototypeKey: dict["prototype_key"] as? String,
                attributes: dict["attributes"] as? [String: (any Sendable)?] ?? [:],
                excerpt: (dict["excerpt"] as? String).flatMap { $0.isEmpty ? nil : $0 },
                dateOriginal: dict["date_original"] as? String,
                dateIso: dict["date_iso"] as? String,
                parentId: dict["parent_id"] as? String
            )
        }
        var defaults: [String: [String: (any Sendable)?]] = [:]
        if let raw = payload["defaults_by_prototype"] as? [String: (any Sendable)?] {
            for (key, value) in raw {
                defaults[key] = value as? [String: (any Sendable)?] ?? [:]
            }
        }
        let bins: [DatasetPage.Bin] = (payload["bins"] as? [(any Sendable)?] ?? [])
            .compactMap { entry in
                guard let dict = entry as? [String: (any Sendable)?],
                      let bin = dict["bin"] as? String,
                      let count = containerInt(dict["count"]) else { return nil }
                return DatasetPage.Bin(bin: bin, count: count)
            }
        var facets: [String: [DatasetPage.FacetValue]] = [:]
        if let raw = payload["facets"] as? [String: (any Sendable)?] {
            for (attr, entries) in raw {
                facets[attr] = (entries as? [(any Sendable)?] ?? []).compactMap { entry in
                    guard let dict = entry as? [String: (any Sendable)?],
                          let value = dict["value"] as? String,
                          let count = containerInt(dict["count"]) else { return nil }
                    return DatasetPage.FacetValue(value: value, count: count)
                }
            }
        }
        return DatasetPage(
            total: containerInt(payload["total"]) ?? rows.count,
            offset: containerInt(payload["offset"]) ?? 0,
            rows: rows,
            defaultsByPrototype: defaults,
            bins: bins,
            facets: facets
        )
    }
}
