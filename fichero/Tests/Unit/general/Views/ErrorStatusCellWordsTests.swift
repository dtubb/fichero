//
//  ErrorStatusCellWordsTests.swift
//  FicheroTests
//
//  ai.where.dead-provider-says-why (## 950): a dead provider's cause (no credit, a refused key, a rate limit) shows in the
//  engine's words as sent, never in a label the app made up.
//

@testable import Fichero
import Testing

struct ErrorStatusCellWordsTests {
    @Test("no credit, a refused key and a rate limit show the engine's first sentence as sent")
    func engineWordsAsSent() {
        let noCredit = "Openrouter has no credit left for this key. Add credit at Openrouter, or choose another model in Settings."
        let refused = "Anthropic refused the API key. Check the key in Settings › AI, or choose another model."
        let slow = "Gemini is asking us to slow down, so this step stopped for now. Run it again in a few minutes."
        #expect(ErrorStatusCell.simplifyError(noCredit) == "Openrouter has no credit left for this key.")
        #expect(ErrorStatusCell.simplifyError(refused) == "Anthropic refused the API key.")
        #expect(ErrorStatusCell.simplifyError(slow) == "Gemini is asking us to slow down, so this step stopped for now.")
    }

    @Test("the vision tool's own sentence for a kind is shown as sent too")
    func visionSentence() {
        let words = "the provider has no credit left for this key — add credit there, or choose another model"
        #expect(ErrorStatusCell.simplifyError(words) == words)
    }

    @Test("the other errors keep their short labels")
    func others() {
        #expect(ErrorStatusCell.simplifyError("HTTP 500 internal server error") == "Server error")
        #expect(ErrorStatusCell.simplifyError("timed out after 30 s") == "Timeout")
    }
}
