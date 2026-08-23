import FicheroAPIClient
import Foundation
import OpenAPIRuntime

// MARK: - Wire → app Document conversion (split from DocumentService.swift
// 2026-08-23: the file crossed its 1000-line hard ceiling when the
// region_in_parent mapping landed; same members, only the file moved).
//
// `DocumentService+Roots.swift` now calls `convertToDocument` too, so these are
// internal — still confined to the app target. The split was always for the
// lint budget, never for encapsulation.
extension DocumentService {
    /// Convert generated Document to local Document
    func convertToDocument(_ doc: Components.Schemas.Document) throws -> Document {
        // A field this converter forgets is a field the whole app does not have.
        //
        // Every key TYPED on the schema decodes into its typed property and
        // NEVER into `additionalProperties` — the generated decoder strips
        // known keys first — so the `?? extras[…]` fallbacks that used to sit
        // on these lines were dead code, not defence. They read as
        // belt-and-braces and hid the neighbours with no read at all: #4515
        // child_count, #4516 prototype_key/node_kind/alias_target_id, #4514
        // attributes, plus sort_order and is_workspace.
        // `DocumentConverterFieldSourceTests` fails if a typed key is read
        // from extras here again.
        //
        // fileType is a typed enum; take its raw value so the local FileType
        // can decode it.
        let fileType = doc.fileType?.rawValue
        let childCount = doc.childCount ?? 0
        // `date_meta`'s ABSENCE is the "never extracted" state, so this stays
        // nil when the server sent nothing. Defaulting it to [:] would read as
        // "extraction ran and found nothing" — a different fact.
        let dateMeta = doc.dateMeta.map { payload in
            payload.additionalProperties.value.mapValues { AnyCodable($0 ?? "") }
        }
        // bbox is OpenAPIArrayContainer — extract its inner [Int] payload.
        let bbox = doc.bbox?.value as? [Int]
        // Step 3 (bbox retirement): the typed region every NEW extraction
        // writes. Forgetting it here is what made the entry-source preview
        // lose its highlight on 2026-08-23 — the decoder-side support was
        // dead code because everything flows through this converter.
        let regionInParent = doc.regionInParent.map { region in
            DocumentRegion(
                rect: region.rect,
                space: region.space?.rawValue,
                confidence: region.confidence?.rawValue,
                method: region.method,
                note: region.note
            )
        }

        return Document(
            id: doc.id ?? UUID().uuidString,
            parentId: doc.parentId,
            docType: convertFromGeneratedDocType(doc.docType),
            fileType: fileType.flatMap { FileType(rawValue: $0) },
            name: doc.name,
            path: doc.path,
            sequence: doc.sequence,
            bbox: bbox,
            regionInParent: regionInParent,
            status: convertFromGeneratedStatus(doc.status),
            metadata: convertMetadata(doc.metadata),
            pageContent: doc.pageContent,
            excludeFromProcessing: doc.excludeFromProcessing ?? false,
            isWorkspace: doc.isWorkspace ?? false,
            childCount: childCount,
            dateOriginal: doc.dateOriginal,   // #3322
            dateJdn: doc.dateJdn,
            dateMeta: dateMeta,
            sortOrder: doc.sortOrder ?? 0,
            // #4516: `prototypeKey` is what `isWorkflowNode` reads; dropping
            // it made the workflow icon, the mirror lock badge, the running
            // spinner and mirror selection routing dead code at once. #2591's
            // alias fields died the same way. #4514: `attributes` carries the
            // engine's `read_only`.
            prototypeKey: doc.prototypeKey,
            nodeKind: doc.nodeKind,
            aliasTargetId: doc.aliasTargetId,
            attributes: convertAttributes(doc.attributes),
            createdAt: doc.createdAt ?? Date(),
            updatedAt: doc.updatedAt ?? Date(),
            expectedThumbnailPath: doc.expectedThumbnailPath,
            expectedDisplayPath: doc.expectedDisplayPath
        )
    }

    /// Convert local DocType to generated DocType
    // internal: called from DocumentService.swift — `private` is FILE-scoped
    // and the 2026-08-23 file_length split moved the declaration here.
    func convertToGeneratedDocType(_ docType: DocType) -> Components.Schemas.DocType {
        switch docType {
        case .folder: return .folder
        case .group: return .group
        case .file: return .file
        case .page: return .page
        case .chunk: return .chunk
        }
    }

    /// Convert generated DocType to local DocType
    private func convertFromGeneratedDocType(_ docType: Components.Schemas.DocType?) -> DocType {
        guard let docType = docType else { return .file }
        switch docType {
        case .folder: return .folder
        case .group: return .group
        case .file: return .file
        case .page: return .page
        case .chunk: return .chunk
        }
    }

    /// Generated FileType → local FileType. A TABLE, not a switch: the
    /// mapping is data (docx folds into word), and the cyclomatic rule is
    /// right that a 12-way switch reads as logic it isn't.
    private static let fileTypeMap: [Components.Schemas.FileType: FileType] = [
        .image: .image, .pdf: .pdf, .text: .text, .word: .word,
        .docx: .word, .audio: .audio, .video: .video, .epub: .epub,
        .spreadsheet: .spreadsheet, .presentation: .presentation,
        .other: .other
    ]

    private func convertFromGeneratedFileType(_ fileType: Components.Schemas.FileType?) -> FileType? {
        fileType.flatMap { Self.fileTypeMap[$0] }
    }

    /// Convert generated Status to local Status
    private func convertFromGeneratedStatus(_ status: Components.Schemas.Status?) -> Status {
        guard let status = status else { return .pending }
        switch status {
        case .pending: return .pending
        case .processing: return .processing
        case .active: return .processing  // active is an in-progress state
        case .completed: return .completed
        case .failed: return .failed
        }
    }

    /// Convert bbox from OpenAPIArrayContainer to [Int]
    private func convertBbox(_ bbox: OpenAPIRuntime.OpenAPIArrayContainer?) -> [Int]? {
        guard let bbox = bbox else { return nil }
        // Extract array values - bbox should be an array of integers
        return bbox.value.compactMap { item -> Int? in
            if let intValue = item as? Int {
                return intValue
            }
            if let doubleValue = item as? Double {
                return Int(doubleValue)
            }
            return nil
        }
    }

    /// Convert metadata from generated type to local type
    private func convertMetadata(_ metadata: Components.Schemas.Document.MetadataPayload?) -> [String: AnyCodable] {
        guard let metadata = metadata else { return [:] }
        var result: [String: AnyCodable] = [:]
        for (key, value) in metadata.additionalProperties.value {
            result[key] = AnyCodable(value ?? "")
        }
        return result
    }

    /// Prototype-scoped node attributes (`read_only`, `scope`, …). Same shape
    /// as `convertMetadata`, distinct generated payload type (#4514).
    private func convertAttributes(
        _ attributes: Components.Schemas.Document.AttributesPayload?
    ) -> [String: AnyCodable] {
        guard let attributes = attributes else { return [:] }
        var result: [String: AnyCodable] = [:]
        for (key, value) in attributes.additionalProperties.value {
            result[key] = AnyCodable(value ?? "")
        }
        return result
    }
}
