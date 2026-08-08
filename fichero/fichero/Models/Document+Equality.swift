import Foundation

// MARK: - Hand-written equality (#4546)
//
// `Document` is a wide struct and SwiftUI calls `==` on every diff to decide
// whether a view updates — `static Document.__derived_struct_equals` burned
// 210 main-thread samples in aug4.trace because the synthesized conformance
// compares every stored property, including six collection/blob fields
// (`metadata`, `pageContent`, `curatedItems`, `structure`, `dateMeta`,
// `attributes`) whose element-wise comparison is the expensive part.
//
// This comparison covers every CHEAP stored property and skips those six.
// Why that is sound:
//   - Every server write bumps `updated_at` (`db/__init__.py`
//     `value.updated_at = utc_now()`), so any server-side change to a skipped
//     field is visible through `updatedAt`.
//   - The only fields client stores mutate IN PLACE without an `updatedAt`
//     bump are `status` and `sortOrder` (DocumentStore+Helpers /
//     DocumentStore+CRUD) — both compared here directly.
//
// A new stored property added to `Document` MUST be classified here (compared
// or knowingly skipped) — `DocumentEqualityTests.storedPropertyInventory`
// fails until it is, so the decision cannot be skipped silently.
extension Document {
    static func == (lhs: Document, rhs: Document) -> Bool {
        lhs.id == rhs.id
            && lhs.updatedAt == rhs.updatedAt
            // The two fields stores mutate in place without an updatedAt bump.
            && lhs.status == rhs.status
            && lhs.sortOrder == rhs.sortOrder
            // Cheap scalars — kept so a same-updatedAt divergence (decoder
            // defaults, optimistic UI copies) can never render stale.
            && lhs.parentId == rhs.parentId
            && lhs.docType == rhs.docType
            && lhs.fileType == rhs.fileType
            && lhs.name == rhs.name
            && lhs.path == rhs.path
            && lhs.sequence == rhs.sequence
            && lhs.bbox == rhs.bbox
            && lhs.excludeFromProcessing == rhs.excludeFromProcessing
            && lhs.isWorkspace == rhs.isWorkspace
            && lhs.childCount == rhs.childCount
            && lhs.dateOriginal == rhs.dateOriginal
            && lhs.dateJdn == rhs.dateJdn
            && lhs.prototypeKey == rhs.prototypeKey
            && lhs.nodeKind == rhs.nodeKind
            && lhs.aliasTargetId == rhs.aliasTargetId
            && lhs.createdAt == rhs.createdAt
            && lhs.expectedThumbnailPath == rhs.expectedThumbnailPath
            && lhs.expectedDisplayPath == rhs.expectedDisplayPath
        // Deliberately NOT compared (expensive; changes arrive with an
        // updatedAt bump): metadata, pageContent, curatedItems, structure,
        // dateMeta, attributes.
    }

    // Equal values must hash equal; hashing a subset of the compared fields
    // is always valid, and `id` + `updatedAt` is the discriminating pair.
    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
        hasher.combine(updatedAt)
    }
}
