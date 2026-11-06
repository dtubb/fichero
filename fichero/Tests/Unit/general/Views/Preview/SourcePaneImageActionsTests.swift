//
//  SourcePaneImageActionsTests.swift
//  FicheroTests
//
//  SPEC-BEHAVIOR (Step 4.7, #6362): the Source pane's bottom bar offers Enhance for an image page and Clean up the folder when the
//  page sits in one; a PDF page gets neither; the Prepare Images check list answers a show-through row with Include / Leave out.
//  Never run (no xcodebuild in the builder lane).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

struct SourcePaneImageActionsTests {
    @Test func aPageInAFolderOffersEnhanceAndCleanUpALoosePageOnlyEnhanceAndAPdfPageNeither() {
        #expect(SourcePaneImageActions.items(for: Document(parentId: "f", fileType: .image, name: "a")) == [.enhance, .cleanUpFolder])
        #expect(SourcePaneImageActions.items(for: Document(fileType: .image, name: "b")) == [.enhance])
        #expect(SourcePaneImageActions.items(for: Document(parentId: "f", fileType: .pdf, name: "c")).isEmpty)
    }

    @Test func enhanceWithNothingTouchedIsTheClaheCleanupOnTheEnginesActionNames() throws {
        let sent = try JSONSerialization.jsonObject(
            with: JSONEncoder().encode(ImageEnhanceRequest(documentId: "d1"))) as? [String: Any]
        #expect(sent?["document_id"] as? String == "d1")
        #expect(sent?["method"] as? String == "clahe" && sent?["profile"] as? String == "handwritten")
    }

    @Test func aShowThroughRowIsAnsweredByIncludeOrLeaveOutNotByAccept() {
        let words = "show-through of recto.png, left out"
        let item = Components.Schemas.PrepareCheckItem(id: "p", name: "verso", kinds: ["show_through"], words: [words], sample: false)
        #expect(PrepareCheck.isShowThrough(item))
        #expect(PrepareCheck.acceptKinds(item).isEmpty)
        #expect(PrepareCheck.words(item) == words)
    }
}
