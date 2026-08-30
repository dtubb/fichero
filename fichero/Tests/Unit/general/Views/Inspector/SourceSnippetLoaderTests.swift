@testable import Fichero
import XCTest

/// SourceSnippetLoader — the phase machine behind the reusable "show me the
/// source" component (#2105). A crop fetch resolves to an image, a text span,
/// nothing (empty), or an error; a cancellation must NOT flash a spurious
/// failure. These lock those transitions with stub fetches (no network).
@MainActor
final class SourceSnippetLoaderTests: XCTestCase {

    private let request = SourceCropRequest(documentId: "doc-1", bbox: [0, 0, 1, 1])

    func testLoadsImageCrop() async {
        let loader = SourceSnippetLoader()
        await loader.load(request) { _ in .image(PlatformImage()) }
        guard case .loaded(.image) = loader.phase else {
            return XCTFail("expected loaded image, got \(loader.phase)")
        }
    }

    func testLoadsTextCrop() async {
        let loader = SourceSnippetLoader()
        await loader.load(request) { _ in .text("Person P says XYZ") }
        guard case .loaded(.text(let text)) = loader.phase else {
            return XCTFail("expected loaded text, got \(loader.phase)")
        }
        XCTAssertEqual(text, "Person P says XYZ")
    }

    func testNilResultIsEmpty() async {
        let loader = SourceSnippetLoader()
        await loader.load(request) { _ in nil }
        guard case .empty = loader.phase else {
            return XCTFail("expected empty, got \(loader.phase)")
        }
    }

    func testThrownErrorIsFailed() async {
        struct Boom: Error {}
        let loader = SourceSnippetLoader()
        await loader.load(request) { _ in throw Boom() }
        guard case .failed = loader.phase else {
            return XCTFail("expected failed, got \(loader.phase)")
        }
    }

    func testCancellationDoesNotFlashFailure() async {
        let loader = SourceSnippetLoader()
        await loader.load(request) { _ in throw CancellationError() }
        // A superseded request must not surface as an error to the user.
        if case .failed = loader.phase {
            XCTFail("cancellation should not become a failure phase")
        }
    }

    func testForwardsRequestToFetch() async {
        let loader = SourceSnippetLoader()
        var seen: SourceCropRequest?
        await loader.load(request) { req in
            seen = req
            return .text("ok")
        }
        XCTAssertEqual(seen, request)
    }
}
