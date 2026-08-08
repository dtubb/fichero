//
//  DocumentEqualityTests.swift
//  FicheroTests
//
//  Guards the hand-written Document ==/hash (#4546). The synthesized
//  conformance compared every stored property on every SwiftUI diff; the
//  hand-written one compares the cheap scalars and skips the six
//  collection/blob fields. These tests pin (a) the behavioral contract and
//  (b) the stored-property inventory, so adding a field without classifying
//  it in Document+Equality.swift fails here instead of silently drifting.
//

import Foundation
import Testing
@testable import Fichero

struct DocumentEqualityTests {

    private func makeDocument() -> Document {
        Document(
            id: "doc-1",
            parentId: "parent-1",
            name: "Diary page",
            status: .completed,
            createdAt: Date(timeIntervalSince1970: 1_000),
            updatedAt: Date(timeIntervalSince1970: 2_000)
        )
    }

    @Test("Identical copies compare equal and hash equal")
    func copiesAreEqual() {
        let base = makeDocument()
        let copy = base
        #expect(base == copy)
        #expect(base.hashValue == copy.hashValue)
    }

    @Test("A metadata-only change compares EQUAL — the documented #4546 decision")
    func metadataOnlyChangeIsEqual() {
        // Server-side metadata writes always bump updated_at
        // (db/__init__.py: value.updated_at = utc_now()), so equality reads
        // the bump, not the dictionary. A same-updatedAt metadata divergence
        // is invisible by design; if that trade ever changes, change
        // Document+Equality.swift and THIS test together.
        let base = makeDocument()
        var changed = base
        changed.metadata["transcription_model"] = AnyCodable("test-model")
        #expect(base == changed)
    }

    @Test("pageContent-only change compares EQUAL — covered by updatedAt bumps")
    func pageContentOnlyChangeIsEqual() {
        let base = makeDocument()
        var changed = base
        changed.pageContent = "a fresh transcript"
        #expect(base == changed)
    }

    @Test("The two locally-mutated fields are compared: status and sortOrder")
    func locallyMutatedFieldsAreCompared() {
        let base = makeDocument()

        var statusChanged = base
        statusChanged.status = .processing
        #expect(base != statusChanged)

        var sortChanged = base
        sortChanged.sortOrder = 7
        #expect(base != sortChanged)
    }

    @Test("updatedAt, name, and parentId changes are detected")
    func scalarChangesAreDetected() {
        let base = makeDocument()

        var touched = base
        touched.updatedAt = base.updatedAt.addingTimeInterval(1)
        #expect(base != touched)

        var renamed = base
        renamed.name = "Renamed"
        #expect(base != renamed)

        var moved = base
        moved.parentId = "parent-2"
        #expect(base != moved)
    }

    /// The #4546 ratchet: every stored property of `Document` must be
    /// classified in `Document+Equality.swift` — compared, or knowingly
    /// skipped. A new property changes this inventory and fails here until
    /// the equality decision is made explicitly.
    @Test("Stored-property inventory matches the classified list")
    func storedPropertyInventory() {
        let classified: Set<String> = [
            // compared
            "id", "parentId", "docType", "fileType", "name", "path",
            "sequence", "bbox", "status", "excludeFromProcessing",
            "isWorkspace", "childCount", "dateOriginal", "dateJdn",
            "sortOrder", "prototypeKey", "nodeKind", "aliasTargetId",
            "createdAt", "updatedAt", "expectedThumbnailPath",
            "expectedDisplayPath",
            // knowingly skipped (expensive; server writes bump updatedAt)
            "metadata", "pageContent", "curatedItems", "structure",
            "dateMeta", "attributes"
        ]
        let stored = Set(Mirror(reflecting: makeDocument()).children.compactMap(\.label))
        #expect(
            stored == classified,
            """
            Document's stored properties changed. Unclassified: \
            \(stored.subtracting(classified).sorted()). Removed: \
            \(classified.subtracting(stored).sorted()). Decide whether each \
            participates in == (Document+Equality.swift) and update BOTH files.
            """
        )
    }
}
