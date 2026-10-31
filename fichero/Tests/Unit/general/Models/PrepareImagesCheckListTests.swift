//
//  PrepareImagesCheckListTests.swift
//  FicheroTests
//
//  SPEC-BEHAVIOR (`prep.check.worklist-of-proposals-and-a-sample`, `prep.check.blank-mark-is-a-correction`, #5382): the
//  Pages to check line and rows say what the engine said; Accept answers each proposal open on the page, Mark blank is
//  offered where blank is in question or on a sample page; the requests use the actions' parameter names. Written
//  2026-10-30, never run (no xcodebuild in the builder lane).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

struct PrepareImagesCheckListTests {
    private func item(kinds: [String], sample: Bool = false) -> Components.Schemas.PrepareCheckItem {
        .init(id: "d1", name: "IMG_0001", kinds: kinds, words: ["the page edge is faint", "the box covers 64%"], sample: sample)
    }

    @Test func theLineSaysTheCount() {
        #expect(PrepareCheck.line(4) == "Pages to check: 4")
    }

    @Test func aRowSaysInWordsWhatIsUnsure() {
        #expect(PrepareCheck.words(item(kinds: ["page_box"])) == "the page edge is faint; the box covers 64%")
    }

    @Test func acceptAnswersEveryProposalOpenOnThePage() {
        #expect(PrepareCheck.acceptKinds(item(kinds: ["page_box", "turn"])) == ["page_box", "turn"])
        #expect(PrepareCheck.acceptKinds(item(kinds: [], sample: true)).isEmpty)
    }

    @Test func markBlankIsOfferedForABlankProposalOrASamplePageOnly() {
        #expect(PrepareCheck.canMarkBlank(item(kinds: ["blank"])))
        #expect(PrepareCheck.canMarkBlank(item(kinds: [], sample: true)))
        #expect(!PrepareCheck.canMarkBlank(item(kinds: ["page_box"])))
    }

    @Test func acceptUsesTheActionsParameterNames() throws {
        let body = try JSONSerialization.jsonObject(
            with: JSONEncoder().encode(ImageAcceptProposalRequest(documentId: "d1", kind: "turn"))) as? [String: Any]
        #expect(body?["document_id"] as? String == "d1" && body?["kind"] as? String == "turn")
    }
}
