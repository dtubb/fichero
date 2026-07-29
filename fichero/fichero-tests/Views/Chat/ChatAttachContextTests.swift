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

    // MARK: - Implicit grounding (#2449 hybrid)

    func testImplicitScopeIsOpenDocumentWhenFocused() {
        let context = ChatAttachContext(
            openDocumentId: "doc-1",
            openDocumentName: "Letter",
            currentViewLabel: "Box 3",
            currentViewDocumentIds: ["a", "b", "c"]
        )
        // A focused document wins — the user is looking at that document.
        XCTAssertEqual(context.implicitScopeIds, ["doc-1"])
        XCTAssertEqual(context.implicitScopeLabel, "Letter")
        XCTAssertTrue(context.hasImplicitScope)
    }

    func testImplicitScopeFallsBackToCurrentViewWhenNoOpenDocument() {
        let context = ChatAttachContext(
            currentViewLabel: "Box 3",
            currentViewDocumentIds: ["a", "b"]
        )
        XCTAssertEqual(context.implicitScopeIds, ["a", "b"])
        XCTAssertEqual(context.implicitScopeLabel, "Box 3")
        XCTAssertTrue(context.hasImplicitScope)
    }

    func testOpenDocumentWithoutNameLabelsGenerically() {
        let context = ChatAttachContext(openDocumentId: "doc-1")
        XCTAssertEqual(context.implicitScopeIds, ["doc-1"])
        XCTAssertEqual(context.implicitScopeLabel, "This document")
    }

    func testEmptyContextHasNoImplicitScope() {
        let context = ChatAttachContext.empty
        XCTAssertTrue(context.implicitScopeIds.isEmpty)
        XCTAssertNil(context.implicitScopeLabel)
        XCTAssertFalse(context.hasImplicitScope)
    }
}
