@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The hygiene mandate applied to the annotation read path (2026-09-03).
///
/// An annotation could become a `DocumentAnnotation` three ways: a
/// hand-written `JSONDecoder` route with no callers, and two verbatim copies
/// of the generated-schema mapping that differed only in a guard. That is the
/// exact shape that shipped the 2026-08-23 regression — the engine moved to a
/// typed anchor, the hand-written decoder kept reading the retired field, and
/// every symptom was a valid nil.
///
/// The copy-paste pair had already drifted the same way: `page_index` was
/// mapped by the document converter and dropped by the folder one.
///
/// These tests pin the converged shape: one mapping, no decoder.
@MainActor
struct AnnotationWireMappingTests {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root().appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private func wire(
        id: String = "a-1",
        documentId: String? = nil,
        folderId: String? = nil,
        pageIndex: Int? = nil
    ) -> Components.Schemas.Annotation {
        Components.Schemas.Annotation(
            id: id,
            documentId: documentId,
            folderId: folderId,
            pageIndex: pageIndex,
            kind: .highlight
        )
    }

    // MARK: - The drift that had already happened

    /// The regression in one assertion: a folder-scoped annotation kept its
    /// page index only in one of the two copies.
    @Test("a folder-scoped annotation keeps its page index")
    func folderScopedAnnotationKeepsPageIndex() throws {
        let mapped = try #require(
            AnnotationService.folderScopedAnnotation(from: wire(folderId: "f-1", pageIndex: 7))
        )
        #expect(mapped.pageIndex == 7)
    }

    @Test("a document-scoped annotation keeps its page index")
    func documentScopedAnnotationKeepsPageIndex() throws {
        let mapped = try #require(
            AnnotationService.documentScopedAnnotation(from: wire(documentId: "doc-1", pageIndex: 7))
        )
        #expect(mapped.pageIndex == 7)
    }

    /// Both entry points must produce the SAME value for the same row — the
    /// scope guard is allowed to decide whether a row maps, never what it
    /// maps to.
    @Test("both entry points map an identical row identically")
    func bothEntryPointsAgree() throws {
        let row = wire(documentId: "doc-1", folderId: "f-1", pageIndex: 3)
        let asDocument = try #require(AnnotationService.documentScopedAnnotation(from: row))
        let asFolder = try #require(AnnotationService.folderScopedAnnotation(from: row))
        #expect(asDocument == asFolder)
    }

    // MARK: - The scope guards still guard

    @Test("a folder-only row is not a document annotation")
    func folderOnlyRowIsNotADocumentAnnotation() {
        #expect(AnnotationService.documentScopedAnnotation(from: wire(folderId: "f-1")) == nil)
    }

    @Test("a document-only row is not a folder annotation")
    func documentOnlyRowIsNotAFolderAnnotation() {
        #expect(AnnotationService.folderScopedAnnotation(from: wire(documentId: "doc-1")) == nil)
    }

    @Test("a row with no id maps to nothing on either path")
    func anIdlessRowMapsToNothing() {
        let row = Components.Schemas.Annotation(documentId: "doc-1", kind: .highlight)
        #expect(AnnotationService.documentScopedAnnotation(from: row) == nil)
        #expect(AnnotationService.folderScopedAnnotation(from: row) == nil)
    }

    // MARK: - Defaults the tolerant decoder used to provide

    /// The absent-array defaults were a property of the hand-written decoder;
    /// they must survive on the mapping that replaced it.
    @Test("absent collections arrive empty, not missing")
    func absentCollectionsArriveEmpty() throws {
        let mapped = try #require(
            AnnotationService.documentScopedAnnotation(from: wire(documentId: "doc-1"))
        )
        #expect(mapped.tags.isEmpty)
        #expect(mapped.linkedClaimIds.isEmpty)
        #expect(mapped.linkedEntityIds.isEmpty)
        #expect(mapped.linkedNoteIds.isEmpty)
    }

    /// The retired pre-anchor field must never be repopulated from the wire:
    /// it exists only as read-compat for rows written before the rename.
    @Test("the retired bbox field is never filled from the wire")
    func retiredBboxIsNeverFilled() throws {
        let mapped = try #require(
            AnnotationService.documentScopedAnnotation(from: wire(documentId: "doc-1"))
        )
        #expect(mapped.bbox == nil)
    }

    // MARK: - Guardrails on the shape itself

    /// One mapping. If a third converter appears, this fails before it can
    /// drift.
    @Test("both converters delegate to the single mapping")
    func bothConvertersDelegateToOneMapping() throws {
        let source = try Self.appSource("Services/AnnotationService+Conversions.swift")
        let delegations = source.components(separatedBy: "return mapped(generated, id: id)").count - 1
        #expect(delegations == 2, "the document and folder scope decisions must share one field mapping")
        #expect(!source.contains("JSONDecoder"))
        #expect(!source.contains("OpenAPIValueContainer"))
    }

    /// No decoder on the service: a `JSONDecoder` there is an invitation to
    /// re-hand-roll the wire read, which is the defect that shipped.
    @Test("the service carries no JSON decoder for annotations")
    func theServiceCarriesNoDecoder() throws {
        let source = try Self.appSource("Services/AnnotationService.swift")
        #expect(!source.contains("let decoder = JSONDecoder()"))
    }
}
