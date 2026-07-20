import FicheroAPIClient
import Foundation
import OpenAPIRuntime

extension AnnotationService {
    func annotation(from value: OpenAPIValueContainer) throws -> DocumentAnnotation {
        guard let object = value.value else { throw AnnotationServiceError.emptyContainer }
        let data = try JSONSerialization.data(withJSONObject: object)
        return try decoder.decode(DocumentAnnotation.self, from: data)
    }

    func annotation(from generated: Components.Schemas.Annotation) -> DocumentAnnotation? {
        // documentId is optional on the wire since #1759 (folder-scoped
        // annotations carry folder_id, not document_id). This per-document
        // converter only surfaces annotations bound to a document.
        guard let id = generated.id, let documentId = generated.documentId else { return nil }
        return DocumentAnnotation(
            id: id,
            documentId: documentId,
            pageId: generated.pageId,
            folderId: generated.folderId,
            pageIndex: generated.pageIndex,
            pageLabel: generated.pageLabel,
            charStart: generated.charStart,
            charEnd: generated.charEnd,
            bbox: generated.bbox,
            kind: AnnotationKind(rawValue: generated.kind.rawValue) ?? .unknown,
            text: generated.text,
            rating: generated.rating,
            color: generated.color,
            tags: generated.tags ?? [],
            linkedClaimIds: generated.linkedClaimIds ?? [],
            linkedEntityIds: generated.linkedEntityIds ?? [],
            linkedNoteIds: generated.linkedNoteIds ?? [],
            createdBy: generated.createdBy,
            createdAt: generated.createdAt?.ISO8601Format(),
            updatedAt: generated.updatedAt?.ISO8601Format()
        )
    }

    func folderAnnotation(from generated: Components.Schemas.Annotation) -> DocumentAnnotation? {
        guard let id = generated.id, let folderId = generated.folderId else { return nil }
        return DocumentAnnotation(
            id: id,
            documentId: generated.documentId,
            pageId: generated.pageId,
            folderId: folderId,
            pageLabel: generated.pageLabel,
            charStart: generated.charStart,
            charEnd: generated.charEnd,
            bbox: generated.bbox,
            kind: AnnotationKind(rawValue: generated.kind.rawValue) ?? .unknown,
            text: generated.text,
            rating: generated.rating,
            color: generated.color,
            tags: generated.tags ?? [],
            linkedClaimIds: generated.linkedClaimIds ?? [],
            linkedEntityIds: generated.linkedEntityIds ?? [],
            linkedNoteIds: generated.linkedNoteIds ?? [],
            createdBy: generated.createdBy,
            createdAt: generated.createdAt?.ISO8601Format(),
            updatedAt: generated.updatedAt?.ISO8601Format()
        )
    }
}
