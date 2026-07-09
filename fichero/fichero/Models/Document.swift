// swiftlint:disable file_length
import FicheroAPIClient
import Foundation

// MARK: - Document Types

/// Document type enum matching Python DocType
enum DocType: String, Codable, CaseIterable {
    case folder
    case group
    case file
    case page
    case chunk

    var icon: String {
        switch self {
        case .folder: return "folder"
        case .group: return "rectangle.stack"
        case .file: return "doc"
        case .page: return "doc.text"
        case .chunk: return "text.quote"
        }
    }
}

/// File type enum matching Python FileType
enum FileType: String, Codable, CaseIterable {
    case image
    case pdf
    case text
    case json
    case word
    case audio
    case video
    case epub
    case spreadsheet
    case presentation
    case csv
    case rtf
    case mobi
    case other

    var icon: String {
        switch self {
        case .image: return "photo"
        case .pdf: return "doc.richtext"
        case .text: return "doc.plaintext"
        case .json: return "curlybraces"
        case .word: return "doc.text.fill"
        case .audio: return "waveform"
        case .video: return "film"
        case .epub: return "book"
        case .spreadsheet: return "tablecells"
        case .presentation: return "rectangle.on.rectangle"
        case .csv: return "tablecells"
        case .rtf: return "doc.text"
        case .mobi: return "books.vertical"
        case .other: return "doc"
        }
    }
}

/// Programmatic chapter/section/subsection tree persisted on a PDF document.
struct DocumentStructureNode: Identifiable, Codable, Hashable {
    let id: String
    let title: String
    let kind: String
    let level: Int
    let pageRange: PageRange
    let basis: String?
    let confidence: Double?
    let sourcePageLabel: String?
    let children: [DocumentStructureNode]

    struct PageRange: Codable, Hashable {
        let start: Int
        let end: Int
    }

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case kind
        case level
        case pageRange = "page_range"
        case basis
        case confidence
        case sourcePageLabel = "source_page_label"
        case children
    }
}

/// Processing status enum matching Python Status
enum Status: String, Codable, CaseIterable {
    case pending
    case processing
    case completed
    case failed

    var color: String {
        switch self {
        case .pending: return "gray"
        case .processing: return "blue"
        case .completed: return "green"
        case .failed: return "red"
        }
    }
}

// MARK: - Document Model

/// Main document model matching Python Document (Pydantic)
struct Document: Identifiable, Codable, Hashable, @unchecked Sendable {
    let id: String
    var parentId: String?
    var docType: DocType
    var fileType: FileType?
    var name: String
    var path: String?
    var sequence: Int?
    var bbox: [Int]?
    var status: Status
    var metadata: [String: AnyCodable]
    var pageContent: String?
    var excludeFromProcessing: Bool
    var isWorkspace: Bool
    var curatedItems: [[String: AnyCodable]]
    var structure: [DocumentStructureNode]
    var childCount: Int
    /// User-defined order within the document's parent folder. Written by the
    /// backend `/documents/reorder` route (`documents.py:276`) and by the
    /// `move` route when it accepts a position. Defaults to 0 for documents
    /// created before sort persistence landed. See sidebar plan Step 3.
    var sortOrder: Int
    /// Document prototype/class assigned via /api/documents/{id}/prototype (#1377).
    var prototypeKey: String?
    var createdAt: Date
    var updatedAt: Date
    // Computed fields from backend (ignored on encode)
    var expectedThumbnailPath: String?
    var expectedDisplayPath: String?

    enum CodingKeys: String, CodingKey {
        case id
        case parentId = "parent_id"
        case docType = "doc_type"
        case fileType = "file_type"
        case name
        case path
        case sequence
        case bbox
        case status
        case metadata
        case pageContent = "page_content"
        case excludeFromProcessing = "exclude_from_processing"
        case isWorkspace = "is_workspace"
        case curatedItems = "curated_items"
        case structure
        case childCount = "child_count"
        case sortOrder = "sort_order"
        case prototypeKey = "prototype_key"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case expectedThumbnailPath = "expected_thumbnail_path"
        case expectedDisplayPath = "expected_display_path"
    }

    init(
        id: String = UUID().uuidString,
        parentId: String? = nil,
        docType: DocType = .file,
        fileType: FileType? = nil,
        name: String,
        path: String? = nil,
        sequence: Int? = nil,
        bbox: [Int]? = nil,
        status: Status = .pending,
        metadata: [String: AnyCodable] = [:],
        pageContent: String? = nil,
        excludeFromProcessing: Bool = false,
        isWorkspace: Bool = false,
        curatedItems: [[String: AnyCodable]] = [],
        structure: [DocumentStructureNode] = [],
        childCount: Int = 0,
        sortOrder: Int = 0,
        prototypeKey: String? = nil,
        createdAt: Date = Date(),
        updatedAt: Date = Date(),
        expectedThumbnailPath: String? = nil,
        expectedDisplayPath: String? = nil
    ) {
        self.id = id
        self.parentId = parentId
        self.docType = docType
        self.fileType = fileType
        self.name = name
        self.path = path
        self.sequence = sequence
        self.bbox = bbox
        self.status = status
        self.metadata = metadata
        self.pageContent = pageContent
        self.excludeFromProcessing = excludeFromProcessing
        self.isWorkspace = isWorkspace
        self.curatedItems = curatedItems
        self.structure = structure
        self.childCount = childCount
        self.sortOrder = sortOrder
        self.prototypeKey = prototypeKey
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.expectedThumbnailPath = expectedThumbnailPath
        self.expectedDisplayPath = expectedDisplayPath
    }

    /// Fallback decoder for legacy JSON responses that predate the
    /// `sort_order` field. Missing values default to 0 (matching the
    /// Python model default) so existing payloads continue to decode.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decode(String.self, forKey: .id)
        self.parentId = try container.decodeIfPresent(String.self, forKey: .parentId)
        self.docType = try container.decode(DocType.self, forKey: .docType)
        self.fileType = try container.decodeIfPresent(FileType.self, forKey: .fileType)
        self.name = try container.decode(String.self, forKey: .name)
        self.path = try container.decodeIfPresent(String.self, forKey: .path)
        self.sequence = try container.decodeIfPresent(Int.self, forKey: .sequence)
        self.bbox = try container.decodeIfPresent([Int].self, forKey: .bbox)
        self.status = try container.decode(Status.self, forKey: .status)
        self.metadata = try container.decode([String: AnyCodable].self, forKey: .metadata)
        self.pageContent = try container.decodeIfPresent(String.self, forKey: .pageContent)
        self.excludeFromProcessing = try container.decodeIfPresent(Bool.self, forKey: .excludeFromProcessing) ?? false
        self.isWorkspace = try container.decodeIfPresent(Bool.self, forKey: .isWorkspace) ?? false
        self.curatedItems = try container.decodeIfPresent([[String: AnyCodable]].self, forKey: .curatedItems) ?? []
        self.structure = try container.decodeIfPresent([DocumentStructureNode].self, forKey: .structure) ?? []
        self.childCount = try container.decodeIfPresent(Int.self, forKey: .childCount) ?? 0
        self.sortOrder = try container.decodeIfPresent(Int.self, forKey: .sortOrder) ?? 0
        self.prototypeKey = try container.decodeIfPresent(String.self, forKey: .prototypeKey)
        self.createdAt = try container.decode(Date.self, forKey: .createdAt)
        self.updatedAt = try container.decode(Date.self, forKey: .updatedAt)
        self.expectedThumbnailPath = try container.decodeIfPresent(String.self, forKey: .expectedThumbnailPath)
        self.expectedDisplayPath = try container.decodeIfPresent(String.self, forKey: .expectedDisplayPath)
    }

    /// Non-optional file type string for sorting (empty string for nil)
    var sortableFileType: String {
        fileType?.rawValue ?? ""
    }

    /// Label to show beneath a PDF page thumbnail / as a page row's title.
    ///
    /// A page child document's `name` is an internal id / source filename
    /// ("page_0003", a hash), not something a reader recognizes — so for
    /// page rows we show the human **page number** instead: the 1-based
    /// `sequence` the backend stamps on each child. When the backend later
    /// exposes an extracted `page_label` (e.g. "iv", "Plate 3") we prefer
    /// that over the raw number — that field is added to the page model by
    /// #2080; until it lands this resolves to the numeric page only.
    ///
    /// Returns `nil` for non-page documents so callers fall back to `name`.
    /// Scoped to `docType == .page` so top-level documents and non-PDF
    /// items are never relabeled.
    var pageThumbnailLabel: String? {
        guard docType == .page, let pageNumber = sequence else { return nil }
        // #2080: prefer a non-empty extracted `page_label` here, i.e.
        //   `pageLabel?.nonEmpty ?? "\(pageNumber)"`
        return "\(pageNumber)"
    }
}

// MARK: - AnyCodable for flexible metadata

/// Type-erased Codable wrapper for metadata dictionary
struct AnyCodable: Codable, Hashable, @unchecked Sendable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()

        if let bool = try? container.decode(Bool.self) {
            value = bool
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let string = try? container.decode(String.self) {
            value = string
        } else if let array = try? container.decode([AnyCodable].self) {
            value = array.map { $0.value }
        } else if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues { $0.value }
        } else {
            value = NSNull()
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()

        switch value {
        case let bool as Bool:
            try container.encode(bool)
        case let int as Int:
            try container.encode(int)
        case let double as Double:
            try container.encode(double)
        case let string as String:
            try container.encode(string)
        case let array as [Any]:
            try container.encode(array.map { AnyCodable($0) })
        case let dict as [String: Any]:
            try container.encode(dict.mapValues { AnyCodable($0) })
        default:
            try container.encodeNil()
        }
    }

    static func == (lhs: AnyCodable, rhs: AnyCodable) -> Bool {
        // Simple equality for basic types
        switch (lhs.value, rhs.value) {
        case let (left as Bool, right as Bool): return left == right
        case let (left as Int, right as Int): return left == right
        case let (left as Double, right as Double): return left == right
        case let (left as String, right as String): return left == right
        default: return false
        }
    }

    func hash(into hasher: inout Hasher) {
        switch value {
        case let bool as Bool: hasher.combine(bool)
        case let int as Int: hasher.combine(int)
        case let double as Double: hasher.combine(double)
        case let string as String: hasher.combine(string)
        default: hasher.combine(0)
        }
    }
}

// MARK: - Search Result

/// Search result from semantic search
struct SearchResult: Identifiable, Codable {
    var id: String { documentId }
    let documentId: String
    let score: Double
    let contentPreview: String?
    let metadata: [String: AnyCodable]
    let highlights: [String]?  // Highlighted text snippets
    let transcriptExcerpts: [Components.Schemas.SearchExcerpt]

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id"
        case score
        case contentPreview = "content_preview"
        case metadata
        case highlights
        case transcriptExcerpts = "transcript_excerpts"
    }

    init(
        documentId: String,
        score: Double,
        contentPreview: String?,
        metadata: [String: AnyCodable],
        highlights: [String]?,
        transcriptExcerpts: [Components.Schemas.SearchExcerpt] = []
    ) {
        self.documentId = documentId
        self.score = score
        self.contentPreview = contentPreview
        self.metadata = metadata
        self.highlights = highlights
        self.transcriptExcerpts = transcriptExcerpts
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        documentId = try container.decode(String.self, forKey: .documentId)
        score = try container.decode(Double.self, forKey: .score)
        contentPreview = try container.decodeIfPresent(String.self, forKey: .contentPreview)
        metadata = try container.decode([String: AnyCodable].self, forKey: .metadata)
        highlights = try container.decodeIfPresent([String].self, forKey: .highlights)
        transcriptExcerpts = try container.decodeIfPresent(
            [Components.Schemas.SearchExcerpt].self,
            forKey: .transcriptExcerpts
        ) ?? []
    }
}

// MARK: - API Response Types

struct SearchResponse: Codable {
    let results: [SearchResult]
    let entityHits: [Components.Schemas.SearchEntityHit]
    let claimHits: [Components.Schemas.SearchClaimHit]
    let count: Int
    let totalResults: Int
    let query: String
    let searchType: String
    let executionTimeMs: Double
    let hasMore: Bool
    let filtersApplied: [String: String]?
    let suggestions: [String]?

    enum CodingKeys: String, CodingKey {
        case results
        case entityHits = "entity_hits"
        case claimHits = "claim_hits"
        case count
        case totalResults = "total_results"
        case query
        case searchType = "search_type"
        case executionTimeMs = "execution_time_ms"
        case hasMore = "has_more"
        case filtersApplied = "filters_applied"
        case suggestions
    }

    init(
        results: [SearchResult],
        entityHits: [Components.Schemas.SearchEntityHit] = [],
        claimHits: [Components.Schemas.SearchClaimHit] = [],
        count: Int,
        totalResults: Int,
        query: String,
        searchType: String,
        executionTimeMs: Double,
        hasMore: Bool,
        filtersApplied: [String: String]?,
        suggestions: [String]?
    ) {
        self.results = results
        self.entityHits = entityHits
        self.claimHits = claimHits
        self.count = count
        self.totalResults = totalResults
        self.query = query
        self.searchType = searchType
        self.executionTimeMs = executionTimeMs
        self.hasMore = hasMore
        self.filtersApplied = filtersApplied
        self.suggestions = suggestions
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        results = try container.decode([SearchResult].self, forKey: .results)
        entityHits = try container.decodeIfPresent(
            [Components.Schemas.SearchEntityHit].self,
            forKey: .entityHits
        ) ?? []
        claimHits = try container.decodeIfPresent(
            [Components.Schemas.SearchClaimHit].self,
            forKey: .claimHits
        ) ?? []
        count = try container.decode(Int.self, forKey: .count)
        totalResults = try container.decode(Int.self, forKey: .totalResults)
        query = try container.decode(String.self, forKey: .query)
        searchType = try container.decode(String.self, forKey: .searchType)
        executionTimeMs = try container.decode(Double.self, forKey: .executionTimeMs)
        hasMore = try container.decode(Bool.self, forKey: .hasMore)
        filtersApplied = try container.decodeIfPresent([String: String].self, forKey: .filtersApplied)
        suggestions = try container.decodeIfPresent([String].self, forKey: .suggestions)
    }
}

struct StatsResponse: Codable {
    let documents: Int
    let artifacts: Int
    let embeddingStats: EmbeddingStats

    enum CodingKeys: String, CodingKey {
        case documents
        case artifacts
        case embeddingStats = "embedding_stats"
    }
}

struct EmbeddingStats: Codable {
    let indexedCount: Int
    let tableExists: Bool

    enum CodingKeys: String, CodingKey {
        case indexedCount = "indexed_count"
        case tableExists = "table_exists"
    }
}

// MARK: - Ingest Mode

extension Document {
    enum IngestMode: String {
        case link
        case copy
        case move
    }

    /// Resolved ingest mode for this document. Backend now writes the
    /// explicit `metadata.ingest_mode` ("link"/"copy"/"move") since #603
    /// Part 2; for older docs without that key we fall back to the legacy
    /// heuristic: bookmark presence → LINK, otherwise COPY.
    var ingestMode: IngestMode {
        if let raw = metadata["ingest_mode"]?.value as? String,
           let mode = IngestMode(rawValue: raw) {
            return mode
        }
        return metadata["bookmark"]?.value != nil ? .link : .copy
    }

    /// True when this document was imported via LINK mode (bookmark reference; original stays on disk).
    var isLinked: Bool { ingestMode == .link }

    /// True when this document was imported via MOVE mode (relocated; original deleted).
    /// MOVE deletes are terminal; the delete-confirmation should reflect that.
    var isMoved: Bool { ingestMode == .move }
}

// MARK: - Navigation

extension Document {
    /// True if double-clicking should navigate *into* this document
    /// (show its children) rather than preview it.
    ///
    /// Containers in 0.0.2:
    ///   - Folders — children are the folder's contents
    ///   - PDFs — children are one `Document` per page (see #568)
    var isNavigableContainer: Bool {
        if docType == .folder { return true }
        if fileType == .pdf { return true }
        return false
    }
}
