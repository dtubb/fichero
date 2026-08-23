import FicheroAPIClient
import Foundation
import OSLog

extension AnnotationService {
    /// Create a note annotation (`kind: note`) and prepend it to `annotations`.
    /// Returns the created annotation, or `nil` on failure (with `error` set).
    @discardableResult
    func addNote(
        scope: AnnotationScope,
        text: String,
        pageLabel: String? = nil,
        bbox: [Double]? = nil,
        charStart: Int? = nil,
        charEnd: Int? = nil,
        pageIndex: Int? = nil,
        kind: AnnotationKind = .note,
        color: String? = nil,
        tags: [String] = [],
        linkedClaimIds: [String] = []
    ) async -> DocumentAnnotation? {
        syncLibraryPath()
        do {
            let ids = Self.scopeIds(scope)
            let documentId = ids.documentId
            let pageId = ids.pageId
            let folderId = ids.folderId
            let request = Components.Schemas.AnnotationCreateRequest(
                documentId: documentId,
                pageId: pageId,
                folderId: folderId,
                kind: Components.Schemas.AnnotationKind(rawValue: (kind == .unknown ? AnnotationKind.note : kind).rawValue) ?? .note,
                pageIndex: pageIndex,
                pageLabel: pageLabel,
                charStart: charStart,
                charEnd: charEnd,
                anchor: Self.wireAnchor(
                    bbox: bbox, documentId: documentId, pageId: pageId, folderId: folderId
                ),

                text: text.isEmpty ? nil : text,
                color: color,
                tags: tags,
                linkedClaimIds: linkedClaimIds.isEmpty ? nil : linkedClaimIds
            )
            let response = try await client.api.createAnnotationApiAnnotationsPost(.init(
                body: .json(request)
            ))
            guard case .ok(let okResponse) = response,
                  let created = createdAnnotation(from: try okResponse.body.json, scope: scope) else {
                error = "Could not save annotation"
                return nil
            }
            annotations.insert(created, at: 0)
            error = nil
            return created
        } catch {
            if error.isCancellationError { return nil }   // superseded — not a failure
            logger.warning("Failed to create annotation: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not save annotation"
            return nil
        }
    }

    private func createdAnnotation(
        from generated: Components.Schemas.Annotation,
        scope: AnnotationScope
    ) -> DocumentAnnotation? {
        switch scope {
        case .folder:
            return folderAnnotation(from: generated)
        case .document, .page:
            return annotation(from: generated)
        }
    }
}

extension AnnotationService {
    /// The three mutually-exclusive wire ids an `AnnotationScope` maps to.
    struct ScopeIds {
        let documentId: String?
        let pageId: String?
        let folderId: String?
    }

    static func scopeIds(_ scope: AnnotationScope) -> ScopeIds {
        switch scope {
        case .document(let id): return ScopeIds(documentId: id, pageId: nil, folderId: nil)
        case .page(let id): return ScopeIds(documentId: nil, pageId: id, folderId: nil)
        case .folder(let id): return ScopeIds(documentId: nil, pageId: nil, folderId: id)
        }
    }

    /// Step 3 (bbox retirement): the wire takes a typed SourceAnchor. The one
    /// region-drawing caller (the PDF reader's drawn highlight) hands
    /// NORMALIZED page fractions on a document scope, so the anchor names the
    /// document and the space instead of shipping bare numbers.
    static func wireAnchor(
        bbox: [Double]?, documentId: String?, pageId: String?, folderId: String?
    ) -> Components.Schemas.SourceAnchorInput? {
        bbox.map { rect in
            .init(
                documentId: documentId ?? pageId ?? folderId ?? "",
                pageId: pageId,
                space: .normalized,
                rect: rect
            )
        }
    }
}
