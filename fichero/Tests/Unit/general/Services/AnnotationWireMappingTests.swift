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

    /// The READ shape (#4990): what a list or a GET actually carries now.
    /// Create still answers the plain `Annotation`, and both go through the
    /// one mapping -- `theTwoWireShapesMapIdentically` below is what holds
    /// that true.
    private func wire(
        id: String = "a-1",
        documentId: String? = nil,
        folderId: String? = nil,
        pageIndex: Int? = nil
    ) -> Components.Schemas.AnnotationRead {
        Components.Schemas.AnnotationRead(
            id: id,
            documentId: documentId,
            folderId: folderId,
            pageIndex: pageIndex,
            kind: .highlight
        )
    }

    /// A stored anchor: the rectangle the line had when the mark was made.
    private func storedAnchor(
        rect: [Double] = [0.1, 0.1, 0.2, 0.05],
        renditionId: String? = nil,
        space: Components.Schemas.AnchorSpace? = nil
    ) -> Components.Schemas.SourceAnchorOutput {
        Components.Schemas.SourceAnchorOutput(
            documentId: "doc-1", renditionId: renditionId, space: space, rect: rect
        )
    }

    private func createWire(
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
        let row = Components.Schemas.AnnotationRead(documentId: "doc-1", kind: .highlight)
        #expect(AnnotationService.documentScopedAnnotation(from: row) == nil)
        #expect(AnnotationService.folderScopedAnnotation(from: row) == nil)
    }

    // MARK: - Two wire shapes, one mapping (#4990)

    /// The reads answer `AnnotationRead` and create answers `Annotation`.
    /// Two wire types for one row is exactly the shape that drifted before,
    /// so this pins that they map IDENTICALLY -- a field added to one
    /// converter and not the other would fail here.
    @Test("the two wire shapes map identically when nothing is resolved")
    func theTwoWireShapesMapIdentically() throws {
        let fromRead = try #require(
            AnnotationService.documentScopedAnnotation(
                from: wire(documentId: "doc-1", pageIndex: 3)
            )
        )
        let fromCreate = try #require(
            AnnotationService.documentScopedAnnotation(
                from: createWire(documentId: "doc-1", pageIndex: 3)
            )
        )
        #expect(fromRead == fromCreate)
    }

    /// A read with no `resolved_anchor` -- every read until the app half of
    /// #4990 lands, and every read of a mark that matched no box -- maps
    /// exactly as it always did. The field is carried, not consumed.
    @Test("a nil resolved anchor maps exactly as before")
    func aNilResolvedAnchorMapsAsBefore() throws {
        var read = wire(documentId: "doc-1", pageIndex: 3)
        read.resolvedAnchor = nil
        let mapped = try #require(AnnotationService.documentScopedAnnotation(from: read))
        let baseline = try #require(
            AnnotationService.documentScopedAnnotation(
                from: createWire(documentId: "doc-1", pageIndex: 3)
            )
        )
        #expect(mapped == baseline)
    }

    // MARK: - A mark follows its line when the line moves (#4990)
    //
    // SPEC: `source.builds-on-the-anchor`, slice 6b under #4990 -- "Does the
    // interim rescue marks? The engine half does; the app must ask" in
    // `build-notes-identity-and-storage.md`. The engine works out where the
    // anchor points now and sends it beside the stored one; the app's ONE
    // accessor draws it. These assert on the value every mark is drawn from,
    // not on the source of the accessor.

    /// The behaviour in one assertion: mark a line, convert, move the line,
    /// and the mark is drawn at the NEW place -- while the stored anchor,
    /// which the engine never rewrites, still remembers the old one.
    @Test("a moved line takes its mark with it")
    func aMovedLineTakesItsMarkWithIt() throws {
        var read = wire(documentId: "doc-1")
        read.anchor = storedAnchor(rect: [0.1, 0.1, 0.2, 0.05])
        read.resolvedAnchor = Components.Schemas.ResolvedAnchor(
            anchor: storedAnchor(rect: [0.1, 0.4, 0.2, 0.05]),
            basis: .segment,
            segmentId: "seg-7"
        )
        let mapped = try #require(AnnotationService.documentScopedAnnotation(from: read))
        #expect(mapped.regionRect == [0.1, 0.4, 0.2, 0.05])
        #expect(mapped.anchor?.rect == [0.1, 0.1, 0.2, 0.05])
        #expect(mapped.resolvedAnchor?.segmentId == "seg-7")
    }

    /// The mark layer is where a wash, underline, strike or star gets its
    /// rectangle, and the PDF renderer reads the same value type. So the
    /// wash IS drawn at the new place, not merely available there.
    @Test("the drawn mark carries the new place")
    func theDrawnMarkCarriesTheNewPlace() throws {
        var read = wire(documentId: "doc-1")
        read.anchor = storedAnchor(rect: [0.1, 0.1, 0.2, 0.05])
        read.resolvedAnchor = Components.Schemas.ResolvedAnchor(
            anchor: storedAnchor(rect: [0.1, 0.4, 0.2, 0.05]), basis: .segment
        )
        let mapped = try #require(AnnotationService.documentScopedAnnotation(from: read))
        #expect(AnnotationMark(annotation: mapped).rect == [0.1, 0.4, 0.2, 0.05])
    }

    /// A mark somebody drew free matched no box, so the engine answers
    /// `stored` with the stored place. It stays exactly where they drew it:
    /// it was about a place, not about a line.
    @Test("a mark drawn free stays where it was drawn")
    func aMarkDrawnFreeStaysPut() throws {
        var read = wire(documentId: "doc-1")
        read.anchor = storedAnchor(rect: [0.5, 0.5, 0.1, 0.1])
        read.resolvedAnchor = Components.Schemas.ResolvedAnchor(
            anchor: storedAnchor(rect: [0.5, 0.5, 0.1, 0.1]), basis: .stored
        )
        let mapped = try #require(AnnotationService.documentScopedAnnotation(from: read))
        #expect(mapped.regionRect == [0.5, 0.5, 0.1, 0.1])
    }

    /// A mark on a line that has since been deleted: the engine answers the
    /// stored place and says the line is gone. The mark is still drawn --
    /// nothing vanishes from the page because a box was removed -- and the
    /// app has what it needs to say so later.
    @Test("a mark on a deleted line keeps its place and knows it is gone")
    func aMarkOnADeletedLineKeepsItsPlace() throws {
        var read = wire(documentId: "doc-1")
        read.anchor = storedAnchor(rect: [0.1, 0.1, 0.2, 0.05])
        read.resolvedAnchor = Components.Schemas.ResolvedAnchor(
            anchor: storedAnchor(rect: [0.1, 0.1, 0.2, 0.05]),
            basis: .segmentDeleted,
            segmentId: "seg-7"
        )
        let mapped = try #require(AnnotationService.documentScopedAnnotation(from: read))
        #expect(mapped.regionRect == [0.1, 0.1, 0.2, 0.05])
        #expect(mapped.resolvedAnchor?.basis == "segment-deleted")
    }

    /// The frame gate (2026-09-03) compares a mark's rendition against the
    /// overlay's. It has to read the SAME anchor the rectangle came from, or
    /// a correctly resolved rect would be hidden on the very page it is on.
    @Test("the drawn frame follows the drawn rectangle")
    func theDrawnFrameFollowsTheDrawnRectangle() throws {
        var read = wire(documentId: "doc-1")
        read.anchor = storedAnchor(rect: [0.1, 0.1, 0.2, 0.05], renditionId: "old-frame")
        read.resolvedAnchor = Components.Schemas.ResolvedAnchor(
            anchor: storedAnchor(rect: [0.1, 0.4, 0.2, 0.05], renditionId: "page-frame"),
            basis: .segment
        )
        let mapped = try #require(AnnotationService.documentScopedAnnotation(from: read))
        #expect(mapped.renditionId == "page-frame")
        #expect(AnnotationMark(annotation: mapped).renditionId == "page-frame")
    }

    /// A resolved rect that does not name normalized space is not drawable as
    /// fractions, so the stored place is drawn rather than a rect scaled
    /// thousands of points off the page. Today's engine never sends one; the
    /// accessor must not depend on that.
    @Test("a resolved rect in pixel space does not displace the stored one")
    func aPixelResolvedRectDoesNotDisplaceTheStoredOne() throws {
        var read = wire(documentId: "doc-1")
        read.anchor = storedAnchor(rect: [0.1, 0.1, 0.2, 0.05])
        read.resolvedAnchor = Components.Schemas.ResolvedAnchor(
            anchor: storedAnchor(rect: [120, 480, 240, 60], space: .pixel), basis: .segment
        )
        let mapped = try #require(AnnotationService.documentScopedAnnotation(from: read))
        #expect(mapped.regionRect == [0.1, 0.1, 0.2, 0.05])
    }

    /// Create answers the plain row, which has nothing resolved. A mark being
    /// drawn the moment it is made must read its own stored place.
    @Test("a freshly created mark has nothing resolved and draws its own place")
    func aFreshlyCreatedMarkDrawsItsOwnPlace() throws {
        var row = createWire(documentId: "doc-1")
        row.anchor = storedAnchor(rect: [0.2, 0.3, 0.1, 0.1])
        let mapped = try #require(AnnotationService.documentScopedAnnotation(from: row))
        #expect(mapped.resolvedAnchor == nil)
        #expect(mapped.regionRect == [0.2, 0.3, 0.1, 0.1])
    }

    /// The resolved anchor survives the round trip through
    /// `DocumentAnnotation`'s own Codable conformance, which the list read
    /// still uses. A `resolved_anchor` that decoded to nil is how the
    /// 2026-08-23 regression looked from the outside.
    @Test("a resolved anchor survives the annotation's own decode")
    func aResolvedAnchorSurvivesTheDecode() throws {
        let json = Data("""
        {"id": "a-1", "document_id": "doc-1", "kind": "highlight",
         "anchor": {"rect": [0.1, 0.1, 0.2, 0.05]},
         "resolved_anchor": {"anchor": {"rect": [0.1, 0.4, 0.2, 0.05]},
                             "basis": "segment", "segment_id": "seg-7"}}
        """.utf8)
        let decoded = try JSONDecoder().decode(DocumentAnnotation.self, from: json)
        #expect(decoded.regionRect == [0.1, 0.4, 0.2, 0.05])
        #expect(decoded.resolvedAnchor?.segmentId == "seg-7")
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
