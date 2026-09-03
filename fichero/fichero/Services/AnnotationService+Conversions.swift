import FicheroAPIClient
import Foundation

// MARK: - Generated schema → app model
//
// ONE mapping (2026-09-03). There used to be three ways an annotation could
// become a `DocumentAnnotation`:
//
//   1. `annotation(from: OpenAPIValueContainer)`, which serialized a loose
//      container back to JSON and ran it through the hand-written
//      `DocumentAnnotation.init(from:)`. It had NO callers.
//   2. `annotation(from: Components.Schemas.Annotation)`.
//   3. `folderAnnotation(from:)` — a verbatim copy of (2) with one guard
//      changed.
//
// That shape is what shipped the 2026-08-23 regression `AnnotationService`
// still carries a comment about: the engine moved to a typed anchor and the
// hand-written decoder, invisible to the OpenAPI regen, kept reading the
// retired field. Annotations were written with anchors and read back without
// them, and every symptom was a valid nil.
//
// The copy-paste pair had already drifted the same way, quietly: `pageIndex`
// was mapped in (2) and dropped in (3), so a folder-scoped annotation lost
// its page index on every read.
//
// Now the scope guard is the ONLY difference between the two entry points,
// and every field is mapped in one place. A new field on the generated schema
// is added there or not at all.

extension AnnotationService {
    /// A document-scoped annotation, or nil when the row is not one.
    ///
    /// `documentId` is optional on the wire since #1759 — folder-scoped
    /// annotations carry `folder_id` instead — so this converter surfaces
    /// only annotations bound to a document.
    func annotation(from generated: Components.Schemas.Annotation) -> DocumentAnnotation? {
        Self.documentScopedAnnotation(from: generated)
    }

    /// A folder-scoped annotation, or nil when the row is not one.
    func folderAnnotation(from generated: Components.Schemas.Annotation) -> DocumentAnnotation? {
        Self.folderScopedAnnotation(from: generated)
    }

    /// The document-scope decision, free of the service so the mapping can be
    /// exercised without standing up a client (the instance methods above are
    /// forwarders; the call sites keep their existing spelling).
    static func documentScopedAnnotation(
        from generated: Components.Schemas.Annotation
    ) -> DocumentAnnotation? {
        guard let id = generated.id, generated.documentId != nil else { return nil }
        return mapped(generated, id: id)
    }

    /// The folder-scope decision, likewise.
    static func folderScopedAnnotation(
        from generated: Components.Schemas.Annotation
    ) -> DocumentAnnotation? {
        guard let id = generated.id, generated.folderId != nil else { return nil }
        return mapped(generated, id: id)
    }

    /// Every field, once. The guards above decide WHETHER a row maps; this
    /// decides WHAT it maps to, and there is only one answer.
    ///
    /// `static` so the mapping can be exercised without a live service — the
    /// field-completeness guardrail is the point of having one copy.
    static func mapped(
        _ generated: Components.Schemas.Annotation, id: String
    ) -> DocumentAnnotation {
        DocumentAnnotation(
            id: id,
            documentId: generated.documentId,
            pageId: generated.pageId,
            folderId: generated.folderId,
            pageIndex: generated.pageIndex,
            pageLabel: generated.pageLabel,
            charStart: generated.charStart,
            charEnd: generated.charEnd,
            // `bbox` is the retired pre-anchor field: the wire no longer
            // carries it and nothing may reintroduce it here. It survives on
            // the model as read-compat for rows written before the rename.
            bbox: nil,
            // The anchor as the app reads it. Deliberately partial, and the
            // omissions are named so they stay decisions rather than
            // oversights: `document_id`/`page_id` duplicate the annotation's
            // own scope, and `polygon`, `rotation`, `granularity` and
            // `refines` have no consumer on any surface yet.
            anchor: generated.anchor.map { anchor in
                AnnotationAnchor(
                    rect: anchor.rect,
                    space: anchor.space?.rawValue,
                    renditionId: anchor.renditionId,
                    charStart: anchor.charStart,
                    charEnd: anchor.charEnd
                )
            },
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
