@testable import Fichero
import FicheroAPIClient
import XCTest

/// After an image edit — background removal, a rotate — the library row kept
/// showing the picture from before (Daniel, 2026-09-03). The invalidation
/// hooks were all there and all correct: `onEditApplied` evicts the storage
/// caches and the rendition caches. They just could not reach the one copy
/// that was on screen.
///
/// `LibraryImageView` holds the decoded `Image` in its own `@State` and
/// reloads only when its `.task(id:)` key changes. Emptying a cache the view
/// is no longer consulting is invisible to it — and its very first line,
/// `guard loadedKey != key || image == nil`, returns immediately even if the
/// task did re-run. An invalidation has to be something the VIEW can see.
@MainActor
final class StorageImageEpochTests: XCTestCase {

    private func makeService() -> StorageService {
        StorageService(ficheroClient: FicheroClient(libraryPath: nil))
    }

    func testEpochStartsAtZeroForAnUntouchedDocument() {
        XCTAssertEqual(makeService().imageEpoch(for: "doc-1"), 0)
    }

    func testInvalidatingMovesThatDocumentsEpoch() {
        let service = makeService()
        service.invalidateImageCache(for: "doc-1")
        XCTAssertEqual(service.imageEpoch(for: "doc-1"), 1)
        service.invalidateImageCache(for: "doc-1")
        XCTAssertEqual(service.imageEpoch(for: "doc-1"), 2)
    }

    /// One item updates in place: editing one page must not restart every
    /// thumbnail in the folder.
    func testInvalidatingOneDocumentLeavesItsNeighboursAlone() {
        let service = makeService()
        service.invalidateImageCache(for: "doc-1")
        XCTAssertEqual(service.imageEpoch(for: "doc-2"), 0)
    }

    func testClearAllMovesEveryKnownEpoch() {
        let service = makeService()
        service.invalidateImageCache(for: "doc-1")
        service.invalidateImageCache(for: "doc-2")
        service.clearAll()
        XCTAssertEqual(service.imageEpoch(for: "doc-1"), 2)
        XCTAssertEqual(service.imageEpoch(for: "doc-2"), 2)
    }

    // MARK: - The key the view actually reloads on

    /// The regression in one assertion: same document, same image type, new
    /// epoch — a DIFFERENT key, so `.task(id:)` re-fires and the guard in
    /// `loadImage` no longer short-circuits.
    func testLoadKeyChangesWhenTheEpochMoves() {
        let before = LibraryImageLoadKey(documentId: "doc-1", imageType: .thumbnail, epoch: 0)
        let after = LibraryImageLoadKey(documentId: "doc-1", imageType: .thumbnail, epoch: 1)
        XCTAssertNotEqual(before, after)
    }

    func testLoadKeyIsStableWhileNothingIsInvalidated() {
        XCTAssertEqual(
            LibraryImageLoadKey(documentId: "doc-1", imageType: .thumbnail, epoch: 3),
            LibraryImageLoadKey(documentId: "doc-1", imageType: .thumbnail, epoch: 3)
        )
    }

    /// The thumbnail and the display image are separate caches and separate
    /// keys; one moving must not be read as the other moving.
    func testLoadKeyStillSeparatesThumbnailFromDisplay() {
        XCTAssertNotEqual(
            LibraryImageLoadKey(documentId: "doc-1", imageType: .thumbnail, epoch: 1),
            LibraryImageLoadKey(documentId: "doc-1", imageType: .display, epoch: 1)
        )
    }
}
