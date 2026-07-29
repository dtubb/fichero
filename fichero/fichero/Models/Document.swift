import CoreTransferable
import FicheroAPIClient
import Foundation
import UniformTypeIdentifiers

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

/// Common drag payload for library items. The text file makes each row useful
/// outside Fichero while JSON preserves its identity for in-app destinations.
struct LibraryItemDrag: Codable, Transferable {
    enum Kind: String, Codable {
        case document
        case page
        case group
        case artifact
        case note
        case annotation
    }

    let kind: Kind
    let id: String
    let documentId: String?
    let text: String
    /// Library context for cross-app file export (#4123); nil = no file
    /// promise (artifacts/notes keep the text-file fallback below).
    var libraryId: UUID?
    /// Display name for the exported file's fallback filename — `text` can
    /// be a whole transcript, which must never become a filename.
    var name: String = ""
    /// 0-based PDF page index for page rows (#4123): the file export trims
    /// the parent's multi-page PDF to just this page.
    var pageIndex: Int?

    var exportText: String { "\(kind.rawValue.capitalized): \(text)" }

    /// Real file export applies to rows backed by a source file.
    var exportsSourceFile: Bool {
        documentId != nil && (kind == .document || kind == .page || kind == .group)
    }

    static var transferRepresentation: some TransferRepresentation {
        CodableRepresentation(contentType: .json)
        // Cross-app (#4123): a COPY of the source file, fetched through the
        // library's storage HTTP endpoint at export time — same path the
        // sidebar's SidebarDragID uses. Never a local engine path.
        FileRepresentation(exportedContentType: .data) { item in
            var drag = SidebarDragID(id: item.id)
            drag.documentId = item.documentId
            drag.libraryId = item.libraryId
            drag.name = item.name
            drag.pageIndex = item.pageIndex
            return SentTransferredFile(try await SidebarDragID.exportSourceFile(for: drag))
        }
        .exportingCondition { $0.exportsSourceFile }
        .suggestedFileName(\.name)
        ProxyRepresentation(exporting: \.text)
        FileRepresentation(exportedContentType: .plainText) { item in
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("fichero-\(item.kind.rawValue)-\(UUID().uuidString).txt")
            try item.exportText.write(to: url, atomically: true, encoding: .utf8)
            return SentTransferredFile(url)
        }
    }
}

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
    /// Node-model kind (#2591): "alias" marks a reference node whose reads
    /// resolve to `aliasTargetId` (engine `node_aliases.py`).
    var nodeKind: String?
    /// Target node id when `nodeKind == "alias"` — stable across target
    /// renames/moves; a deleted target makes the alias dangling.
    var aliasTargetId: String?
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
        case nodeKind = "node_kind"
        case aliasTargetId = "alias_target_id"
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
        nodeKind: String? = nil,
        aliasTargetId: String? = nil,
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
        self.nodeKind = nodeKind
        self.aliasTargetId = aliasTargetId
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
        self.nodeKind = try container.decodeIfPresent(String.self, forKey: .nodeKind)
        self.aliasTargetId = try container.decodeIfPresent(String.self, forKey: .aliasTargetId)
        self.createdAt = try container.decode(Date.self, forKey: .createdAt)
        self.updatedAt = try container.decode(Date.self, forKey: .updatedAt)
        self.expectedThumbnailPath = try container.decodeIfPresent(String.self, forKey: .expectedThumbnailPath)
        self.expectedDisplayPath = try container.decodeIfPresent(String.self, forKey: .expectedDisplayPath)
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

    /// Reference (alias) node, Finder-style (#2591): renders with an alias
    /// badge and selection resolves to `aliasTargetId` instead of itself.
    var isAlias: Bool {
        nodeKind == "alias" && !(aliasTargetId ?? "").isEmpty
    }

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

    /// True for the workflow rows the engine MIRRORS into the document tree to
    /// sit under the seeded "Default Workflows" folder (#11 Phase 1 — the
    /// `workflows` table stays source of truth). A mirror is a plain `.file`
    /// doc with NO `fileType` — see `SidebarItemBuilder.isSidebarVisible`.
    var isWorkflowNode: Bool { prototypeKey == "workflow" }
}

// MARK: - Default Workflows

extension Document {
    /// Stable id of the engine's locked "Default Workflows" container folder;
    /// its system subfolders are ids in the `"\(id):…"` namespace. Mirrors
    /// `_DEFAULT_WORKFLOWS_CONTAINER_ID` in `fichero-server/src/fichero_server/db/__init__.py`.
    static let defaultWorkflowsContainerID = "system-default-workflows"

    /// The container itself, or a subfolder the engine SEEDED into its id
    /// namespace. A fast path only: it says where a row's id came from, not
    /// where the row currently lives.
    var hasDefaultWorkflowContainerID: Bool {
        id == Self.defaultWorkflowsContainerID
            || id.hasPrefix("\(Self.defaultWorkflowsContainerID):")
    }

    /// True for the locked "Default Workflows" container folder or ANY folder
    /// beneath it. These are read-only, non-editable nodes, so the sidebar
    /// marks them with a distinct icon and a lock badge (see
    /// `SidebarItem.fromDocument` and `SidebarItemRow.iconView`).
    ///
    /// Parentage, not id structure, decides this (#4200). `heal_default_workflow_tree`
    /// RE-PARENTS legacy preset folders under the container without RE-IDing
    /// them (b2b9f6899), so a re-homed "Books" keeps its legacy id and the
    /// namespace test alone misses it — it renders unlocked inside a locked
    /// container. Encoding hierarchy in identifiers is what broke here; any
    /// future reparent would break it again.
    ///
    /// Only `parentId` is followed, so a document that merely REFERENCES the
    /// container (alias target, prototype key) is not treated as inside it.
    /// `resolveParent` returns nil for an ancestor the caller hasn't loaded —
    /// the row then falls back to the id fast path rather than claiming to
    /// know it is unlocked.
    func isDefaultWorkflowFolder(resolveParent: (String) -> Document?) -> Bool {
        guard docType == .folder else { return false }
        if hasDefaultWorkflowContainerID { return true }

        // Walk to the root. `visited` guards against a parent cycle: a bad
        // heal or a hand-edited row must not spin the sidebar build.
        var visited: Set<String> = [id]
        var currentParentId = parentId
        while let ancestorId = currentParentId, visited.insert(ancestorId).inserted {
            if ancestorId == Self.defaultWorkflowsContainerID { return true }
            guard let ancestor = resolveParent(ancestorId) else { return false }
            if ancestor.hasDefaultWorkflowContainerID { return true }
            currentParentId = ancestor.parentId
        }
        return false
    }
}
