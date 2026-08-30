// Preload-window neighbor selection for folder image navigation (#2469).
// Verifies that ZoomableImagePreview.preloadIds returns the correct ±radius
// document ids for all boundary conditions (start, middle, end of list).

@testable import Fichero
import Foundation
import Testing

@MainActor
struct FolderImagePreloadTests {

    private func makeDoc(id: String) -> Document {
        Document(
            id: id,
            parentId: nil,
            docType: .file,
            fileType: .image,
            name: id,
            path: nil,
            sequence: nil,
            bbox: nil,
            status: .completed,
            metadata: [:],
            pageContent: nil,
            excludeFromProcessing: false,
            isWorkspace: false,
            curatedItems: [],
            structure: [],
            sortOrder: 0,
            prototypeKey: nil,
            createdAt: Date.distantPast,
            updatedAt: Date.distantPast,
            expectedThumbnailPath: nil,
            expectedDisplayPath: nil
        )
    }

    private func docs(_ count: Int) -> [Document] {
        (0..<count).map { idx in makeDoc(id: "doc-\(idx)") }
    }

    @Test("returns ±3 neighbors around a middle index")
    func neighborsAroundMiddle() {
        let list = docs(10)
        let result = ZoomableImagePreview.preloadIds(from: list, currentId: "doc-5", radius: 3)
        let expected = ["doc-2", "doc-3", "doc-4", "doc-6", "doc-7", "doc-8"]
        #expect(result == expected)
    }

    @Test("clips to start of list — no negative indices")
    func neighborsAtStart() {
        let list = docs(10)
        let result = ZoomableImagePreview.preloadIds(from: list, currentId: "doc-1", radius: 3)
        // Only doc-0 is before; doc-2, doc-3, doc-4 are after.
        #expect(result.contains("doc-0"))
        #expect(result.contains("doc-2"))
        #expect(!result.contains("doc-1"))
        #expect(result.count == 4)
    }

    @Test("clips to end of list — no out-of-bounds indices")
    func neighborsAtEnd() {
        let list = docs(10)
        let result = ZoomableImagePreview.preloadIds(from: list, currentId: "doc-8", radius: 3)
        // doc-5, doc-6, doc-7 before; doc-9 after.
        #expect(result.contains("doc-5"))
        #expect(result.contains("doc-9"))
        #expect(!result.contains("doc-8"))
        #expect(result.count == 4)
    }

    @Test("current id is excluded from the result")
    func currentIdExcluded() {
        let list = docs(7)
        let result = ZoomableImagePreview.preloadIds(from: list, currentId: "doc-3", radius: 3)
        #expect(!result.contains("doc-3"))
    }

    @Test("returns empty for unrecognised current id")
    func unknownIdReturnsEmpty() {
        let list = docs(5)
        let result = ZoomableImagePreview.preloadIds(from: list, currentId: "missing", radius: 3)
        #expect(result.isEmpty)
    }

    @Test("single-element list returns empty")
    func singleElementList() {
        let list = docs(1)
        let result = ZoomableImagePreview.preloadIds(from: list, currentId: "doc-0", radius: 3)
        #expect(result.isEmpty)
    }

    @Test("radius=1 returns only immediate neighbors")
    func radiusOneNeighbors() {
        let list = docs(5)
        let result = ZoomableImagePreview.preloadIds(from: list, currentId: "doc-2", radius: 1)
        #expect(result == ["doc-1", "doc-3"])
    }
}
