import XCTest

@testable import Fichero

/// Unit tests for the chat composer's attach-target context (#2449 step 2):
/// the pure flags that decide which paperclip menu items the host offers.
final class ChatAttachContextTests: XCTestCase {

    func testEmptyContextHasNoHostTargets() {
        let context = ChatAttachContext.empty
        XCTAssertFalse(context.hasOpenDocument)
        XCTAssertFalse(context.hasCurrentView)
        XCTAssertFalse(context.hasHostTargets)
    }

    func testOpenDocumentIsAHostTarget() {
        let context = ChatAttachContext(openDocumentId: "doc-1", openDocumentName: "Letter")
        XCTAssertTrue(context.hasOpenDocument)
        XCTAssertFalse(context.hasCurrentView)
        XCTAssertTrue(context.hasHostTargets)
    }

    func testCurrentViewWithDocumentsIsAHostTarget() {
        let context = ChatAttachContext(currentViewDocumentIds: ["a", "b"])
        XCTAssertFalse(context.hasOpenDocument)
        XCTAssertTrue(context.hasCurrentView)
        XCTAssertTrue(context.hasHostTargets)
    }

    func testEmptyCurrentViewIsNotATarget() {
        let context = ChatAttachContext(currentViewLabel: "Current View", currentViewDocumentIds: [])
        XCTAssertFalse(context.hasCurrentView)
        XCTAssertFalse(context.hasHostTargets)
    }

    func testBothTargetsPresent() {
        let context = ChatAttachContext(
            openDocumentId: "doc-1",
            currentViewDocumentIds: ["a"]
        )
        XCTAssertTrue(context.hasOpenDocument)
        XCTAssertTrue(context.hasCurrentView)
        XCTAssertTrue(context.hasHostTargets)
    }
}
