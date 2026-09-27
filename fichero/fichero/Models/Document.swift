import CoreTransferable
import FicheroAPIClient
import Foundation
import UniformTypeIdentifiers

// MARK: - Document Model

/// Common drag payload for library items. The text file makes each row useful
/// outside Fichero while JSON preserves its identity for in-app destinations.
struct LibraryItemDrag: Codable, Equatable, Transferable {
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

    /// The drag payload for a document row, shared by every surface that drags a
    /// document out (the library table/list/icon rows AND the claims table's
    /// Source cell). Extracted from `LibraryView.libraryItemDrag(for:)` so the
    /// claims Source column drags a document exactly as a library row does
    /// (spec: panes-workspaces panes.claim.source-is-document — a
    /// claim's source IS a document, so it drags like one).
    static func forDocument(_ document: Document, libraryId: UUID?) -> LibraryItemDrag {
        let kind: Kind = switch document.docType {
        case .page: .page
        case .group: .group
        default: .document
        }
        return LibraryItemDrag(
            kind: kind,
            id: document.id,
            documentId: document.id,
            text: document.pageContent?.isEmpty == false ? (document.pageContent ?? document.name) : document.name,
            libraryId: libraryId,
            name: document.name,
            pageIndex: kind == .page ? max(0, (document.sequence ?? 1) - 1) : nil
        )
    }

    /// Real file export applies to rows backed by a source file.
    var exportsSourceFile: Bool {
        documentId != nil && (kind == .document || kind == .page || kind == .group)
    }

    static var transferRepresentation: some TransferRepresentation {
        // THE in-app payload (#4401 multi-drag): the same JSON the string
        // path decodes, as a DataRepresentation of the named custom type —
        // multi-item drag sessions drop proxy/visibility-limited flavors but
        // deliver data representations (see UTType.ficheroDragItem). This is
        // also what lets LibraryItemDropDelegate VALIDATE a multi-item
        // library drag at all: its accepted types match by identifier, and a
        // session that only carried undeclared flavors was refused by AppKit
        // before any of our code ran — dead silent (live-repro 2026-08-04).
        DataRepresentation(exportedContentType: .ficheroDragItem) { item in
            try JSONEncoder().encode(item)
        }
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
/// Mirror of the engine's `NodeRegion` (Step 3): a rect that names its
/// coordinate space instead of four bare numbers.
struct DocumentRegion: Codable, Hashable {
    /// `[x, y, width, height]`, fractions of the parent's frame when
    /// `space == "normalized"` (the only space extractions write today).
    var rect: [Double]
    var space: String?
    /// "measured" | "nominal" | "user" — how much the rect is worth (the
    /// Marshall nominal-even-split openings are guesses, not measurements).
    var confidence: String?
    var method: String?
    var note: String?
    /// Which RENDITION of the parent the rect was measured on (2026-08-23).
    /// `nil` — the overwhelmingly common case — means the parent's own frame.
    /// Non-nil means the rect is only valid on that rendition's pixels:
    /// zooming/highlighting on the parent's base image with it would place a
    /// plausible band in the wrong frame, so consumers must treat it like the
    /// engine's `compose` does — refuse, don't approximate.
    var renditionId: String?

    /// True when the rect can be applied directly to the parent's own image —
    /// the only case the preview's zoom/highlight paths may consume.
    var isInParentFrame: Bool { renditionId == nil }

    enum CodingKeys: String, CodingKey {
        case rect, space, confidence, method, note
        case renditionId = "rendition_id"
    }
}

struct Document: Identifiable, Codable, Hashable, @unchecked Sendable {
    let id: String
    var parentId: String?
    var docType: DocType
    var fileType: FileType?
    var name: String
    var path: String?
    var sequence: Int?
    var bbox: [Int]?
    /// WHERE this node sits on its parent, as a typed region (Step 3 of the
    /// bbox program, 2026-08-22). Normalized rect — no page-size dependency.
    /// New extractions write ONLY this; `bbox` remains for pre-rename rows.
    var regionInParent: DocumentRegion?
    var status: Status
    var metadata: [String: AnyCodable]
    var pageContent: String?
    var excludeFromProcessing: Bool
    /// Search must not return this document (#4580) — curation for
    /// structural pages (covers, front matter) that are not content.
    var excludeFromSearch: Bool
    var isWorkspace: Bool
    var curatedItems: [[String: AnyCodable]]
    var structure: [DocumentStructureNode]
    var childCount: Int
    /// The historical date the document was WRITTEN (#3322) — not `createdAt`,
    /// which is import time and is meaningless for a 19th-century diary.
    ///
    /// Three columns and a status, read through `DocumentDateDisplay.resolve`
    /// rather than directly: `dateMeta == nil` is what "extraction never ran"
    /// means, so its absence is an answer and not a value to default away.
    /// `dateJdn` is the sort key; it is deliberately an Int, because a
    /// Foundation `Date` cannot represent a Julian or French-Republican date
    /// and would drag a timezone into a fact that has none.
    var dateOriginal: String?
    var dateJdn: Int?
    var dateMeta: [String: AnyCodable]?
    /// The language the document IS IN (#2092) — what transcription, SVO and
    /// entity extraction must be told, not the language the user wants output
    /// in. Mirrors the date fields' three-way honesty, read through
    /// `DocumentLanguageDisplay.resolve` rather than defaulted:
    /// `languageMeta == nil` means detection never ran (never-determined),
    /// `languageMeta["status"] == "unknown"` means it was examined and cannot
    /// be told, and `"known"` means `language` holds the answer.
    /// `languageMeta["source"] == "user"` marks a human correction that
    /// survives re-extraction — the same rule as `dateMeta["source"]`.
    var language: String?
    var languageMeta: [String: AnyCodable]?
    /// **Not the library's sort setting.** `LibraryView` also has a
    /// `sortOrder` — an array of `KeyPathComparator`s driving the table
    /// header — and `DocumentStore` sits close enough to both that the two
    /// meanings meet. This one is a per-document POSITION among its siblings.
    /// The listing routes' `sort_by` parameter overrides it; absent `sort_by`,
    /// this is what orders a folder (#3322).
    ///
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
    /// Prototype-scoped node attributes written by the engine — `read_only`,
    /// `scope`, `system`, and the saved-search/workflow mirror payloads
    /// (`db/__init__.py`). This is where the engine states that a node is
    /// system-owned, so it is the honest answer to "may the user edit this?"
    /// — see `isReadOnly`. Every mutating route enforces the same flag
    /// server-side (`_reject_if_document_read_only`), so the client reads it
    /// to render the truth, never to invent a rule of its own.
    var attributes: [String: AnyCodable]
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
        case regionInParent = "region_in_parent"
        case status
        case metadata
        case pageContent = "page_content"
        case excludeFromProcessing = "exclude_from_processing"
        case excludeFromSearch = "exclude_from_search"
        case isWorkspace = "is_workspace"
        case curatedItems = "curated_items"
        case structure
        case childCount = "child_count"
        case dateOriginal = "date_original"
        case dateJdn = "date_jdn"
        case dateMeta = "date_meta"
        case language
        case languageMeta = "language_meta"
        case sortOrder = "sort_order"
        case prototypeKey = "prototype_key"
        case nodeKind = "node_kind"
        case aliasTargetId = "alias_target_id"
        case attributes
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
        regionInParent: DocumentRegion? = nil,
        status: Status = .pending,
        metadata: [String: AnyCodable] = [:],
        pageContent: String? = nil,
        excludeFromProcessing: Bool = false,
        excludeFromSearch: Bool = false,
        isWorkspace: Bool = false,
        curatedItems: [[String: AnyCodable]] = [],
        structure: [DocumentStructureNode] = [],
        childCount: Int = 0,
        dateOriginal: String? = nil,
        dateJdn: Int? = nil,
        dateMeta: [String: AnyCodable]? = nil,
        language: String? = nil,
        languageMeta: [String: AnyCodable]? = nil,
        sortOrder: Int = 0,
        prototypeKey: String? = nil,
        nodeKind: String? = nil,
        aliasTargetId: String? = nil,
        attributes: [String: AnyCodable] = [:],
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
        self.regionInParent = regionInParent
        self.status = status
        self.metadata = metadata
        self.pageContent = pageContent
        self.excludeFromProcessing = excludeFromProcessing
        self.excludeFromSearch = excludeFromSearch
        self.isWorkspace = isWorkspace
        self.curatedItems = curatedItems
        self.structure = structure
        self.childCount = childCount
        self.dateOriginal = dateOriginal
        self.dateJdn = dateJdn
        self.dateMeta = dateMeta
        self.language = language
        self.languageMeta = languageMeta
        self.sortOrder = sortOrder
        self.prototypeKey = prototypeKey
        self.nodeKind = nodeKind
        self.aliasTargetId = aliasTargetId
        self.attributes = attributes
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
        self.regionInParent = try container.decodeIfPresent(DocumentRegion.self, forKey: .regionInParent)
        self.status = try container.decode(Status.self, forKey: .status)
        self.metadata = try container.decode([String: AnyCodable].self, forKey: .metadata)
        self.pageContent = try container.decodeIfPresent(String.self, forKey: .pageContent)
        self.excludeFromProcessing = try container.decodeIfPresent(Bool.self, forKey: .excludeFromProcessing) ?? false
        self.excludeFromSearch = try container.decodeIfPresent(Bool.self, forKey: .excludeFromSearch) ?? false
        self.isWorkspace = try container.decodeIfPresent(Bool.self, forKey: .isWorkspace) ?? false
        self.curatedItems = try container.decodeIfPresent([[String: AnyCodable]].self, forKey: .curatedItems) ?? []
        self.structure = try container.decodeIfPresent([DocumentStructureNode].self, forKey: .structure) ?? []
        self.childCount = try container.decodeIfPresent(Int.self, forKey: .childCount) ?? 0
        self.dateOriginal = try container.decodeIfPresent(String.self, forKey: .dateOriginal)
        self.dateJdn = try container.decodeIfPresent(Int.self, forKey: .dateJdn)
        self.dateMeta = try container.decodeIfPresent([String: AnyCodable].self, forKey: .dateMeta)
        self.language = try container.decodeIfPresent(String.self, forKey: .language)
        self.languageMeta = try container.decodeIfPresent([String: AnyCodable].self, forKey: .languageMeta)
        self.sortOrder = try container.decodeIfPresent(Int.self, forKey: .sortOrder) ?? 0
        self.prototypeKey = try container.decodeIfPresent(String.self, forKey: .prototypeKey)
        self.nodeKind = try container.decodeIfPresent(String.self, forKey: .nodeKind)
        self.aliasTargetId = try container.decodeIfPresent(String.self, forKey: .aliasTargetId)
        self.attributes = try container.decodeIfPresent([String: AnyCodable].self, forKey: .attributes) ?? [:]
        self.createdAt = try container.decode(Date.self, forKey: .createdAt)
        self.updatedAt = try container.decode(Date.self, forKey: .updatedAt)
        self.expectedThumbnailPath = try container.decodeIfPresent(String.self, forKey: .expectedThumbnailPath)
        self.expectedDisplayPath = try container.decodeIfPresent(String.self, forKey: .expectedDisplayPath)
    }
}
