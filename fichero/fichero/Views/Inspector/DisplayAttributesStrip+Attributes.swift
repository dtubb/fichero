import SwiftUI

extension DisplayAttributesStrip {
    /// The fixed document attributes the strip can show. Case order is the
    /// display order. `path` is additionally gated on the document having one.
    enum DisplayAttribute: String, CaseIterable, Identifiable {
        case status, kind, ingest, path, created, modified
        var id: String { rawValue }
        var label: String {
            switch self {
            case .status: return "Status"
            case .kind: return "Kind"
            case .ingest: return "Ingest"
            case .path: return "Path"
            case .created: return "Created"
            case .modified: return "Modified"
            }
        }
    }

    /// Knowledge-graph summaries the strip can surface — peers to artifacts,
    /// each an opt-in count row (#1246).
    enum KGItem: String, CaseIterable, Identifiable {
        case entities, claims
        var id: String { rawValue }
        var label: String {
            switch self {
            case .entities: return "Entities"
            case .claims: return "Claims"
            }
        }
    }

    /// A single rendered line in the strip — a fixed attribute, a KG summary,
    /// a surfaced artifact type, or a document-metadata key. Unifying them lets
    /// one `ForEach` interleave the divider logic without an index-vs-data
    /// mismatch. (#1229, extended for KG + metadata in #1246.)
    enum StripRow: Identifiable {
        case attribute(DisplayAttribute)
        case knowledge(KGItem)
        case artifact(String)
        case metadata(String)
        var id: String {
            switch self {
            case .attribute(let attr): return "attr:\(attr.rawValue)"
            case .knowledge(let item): return "kg:\(item.rawValue)"
            case .artifact(let type): return "art:\(type)"
            case .metadata(let key): return "meta:\(key)"
            }
        }
    }

    var hiddenAttributes: Set<String> {
        csvSet(hiddenRaw)
    }

    var shownArtifactTypes: Set<String> {
        csvSet(shownArtifactsRaw)
    }

    var shownKGItems: Set<String> {
        csvSet(shownKGRaw)
    }

    var shownMetadataKeys: Set<String> {
        csvSet(shownMetadataRaw)
    }

    /// Distinct artifact types available for this document, sorted for a stable
    /// menu + row order.
    var availableArtifactTypes: [String] {
        Array(Set(artifacts.map(\.artifactType))).sorted()
    }

    /// Internal/derived metadata keys that aren't useful as surfaced rows —
    /// hashes, MIME guts, the raw page-content blobs, and the LINK bookmark.
    /// Matches the noise filter the Info tab's Technical Metadata uses.
    private static let noisyMetadataKeys: Set<String> = [
        "checksum", "hash", "md5", "sha256",
        "mime_type", "mimetype", "content_type",
        "page_content", "page_content_rtf",
        "transcription", "bookmark",
        // #1369: internal timeline extraction bucket shouldn't surface as a
        // top-strip facet.
        "dates"
    ]

    /// Document-metadata keys worth surfacing (file metadata/info + any
    /// imported JSON), noise filtered out, sorted for a stable menu order.
    var availableMetadataKeys: [String] {
        document.metadata.keys
            .filter { !Self.noisyMetadataKeys.contains($0.lowercased()) }
            .sorted()
    }

    /// The ordered rows to render: visible fixed attributes, then the
    /// knowledge-graph summaries, artifact types, and metadata keys the user
    /// has switched on. Every source is opt-in past the fixed attributes, so
    /// the Content tab can surface *everything* available for the selection
    /// without crowding the default view (#1246).
    var rows: [StripRow] {
        var result = DisplayAttribute.allCases
            .filter { shouldRender($0) }
            .map { StripRow.attribute($0) }
        result += KGItem.allCases
            .filter { shownKGItems.contains($0.rawValue) }
            // Entities surface "as they're added" — only when the page actually
            // has some — so a fresh/empty page isn't cluttered with "Entities —"
            // (#2696). Claims (opt-in) keep their explicit count/dash.
            .filter { $0 != .entities || (entityCount ?? 0) > 0 }
            .map { StripRow.knowledge($0) }
        result += availableArtifactTypes
            .filter { shownArtifactTypes.contains($0) }
            .map { StripRow.artifact($0) }
        result += availableMetadataKeys
            .filter { shownMetadataKeys.contains($0) }
            .map { StripRow.metadata($0) }
        return result
    }
}
