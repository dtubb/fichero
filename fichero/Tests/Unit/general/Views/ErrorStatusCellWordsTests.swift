//
//  ErrorStatusCellWordsTests.swift
//  FicheroTests
//
//  ai.where.dead-provider-says-why (## 950, ## 972): the error cell says the engine's first sentence as sent, for every
//  error; the app keeps no labels of its own.
//

@testable import Fichero
import Testing

struct ErrorStatusCellWordsTests {
    @Test("no credit, a refused key and a rate limit show the engine's first sentence as sent")
    func engineWordsAsSent() {
        let noCredit = "Openrouter has no credit left for this key. Add credit at Openrouter, or choose another model in Settings."
        let refused = "Anthropic refused the API key. Check the key in Settings › AI, or choose another model."
        let slow = "Gemini is asking us to slow down, so this step stopped for now. Run it again in a few minutes."
        #expect(ErrorStatusCell.cellText(noCredit) == "Openrouter has no credit left for this key.")
        #expect(ErrorStatusCell.cellText(refused) == "Anthropic refused the API key.")
        #expect(ErrorStatusCell.cellText(slow) == "Gemini is asking us to slow down, so this step stopped for now.")
    }

    @Test("a reworded engine message is still shown as sent: no substring guess to break")
    func rewordsAreSafe() {
        #expect(ErrorStatusCell.cellText("Your balance is empty. Top it up.") == "Your balance is empty.")
    }

    @Test("every error is the engine's words, never an app label")
    func noAppLabels() {
        for error in ["HTTP 402 insufficient credits", "401 unauthorized", "timed out after 30 s", "429 rate limit", "500 internal server error"] {
            #expect(ErrorStatusCell.cellText(error) == error, "\(error)")
        }
    }

    @Test("a file path in the error never reaches the cell")
    func noPaths() {
        let error = "Could not read /Users/maya/Marshall Diaries/p12.jpg. The model returned nothing."
        let cell = ErrorStatusCell.cellText(error)
        #expect(cell == "Could not read a page.")
        #expect(!cell.contains("/Users"))
    }
}
