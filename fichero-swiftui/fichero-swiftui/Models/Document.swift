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
struct Document: Identifiable, Codable, Hashable {
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
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.expectedThumbnailPath = expectedThumbnailPath
        self.expectedDisplayPath = expectedDisplayPath
    }

    /// Non-optional file type string for sorting (empty string for nil)
    var sortableFileType: String {
        fileType?.rawValue ?? ""
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

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id"
        case score
        case contentPreview = "content_preview"
        case metadata
        case highlights
    }
}

// MARK: - API Response Types

struct SearchResponse: Codable {
    let results: [SearchResult]
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
        case count
        case totalResults = "total_results"
        case query
        case searchType = "search_type"
        case executionTimeMs = "execution_time_ms"
        case hasMore = "has_more"
        case filtersApplied = "filters_applied"
        case suggestions
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

// MARK: - Health

struct HealthResponse: Codable {
    let status: String
    let backendVersion: String
    let activeLibraries: Int

    enum CodingKeys: String, CodingKey {
        case status
        case backendVersion = "backend_version"
        case activeLibraries = "active_libraries"
    }
}
