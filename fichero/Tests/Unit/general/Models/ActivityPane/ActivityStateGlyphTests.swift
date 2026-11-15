//
//  ActivityStateGlyphTests.swift — `activity.pane.one-glyph-per-state` and `activity.pane.text-budget` (#6441): one glyph
//  per state with its word for VoiceOver and hover, no state word in the row, no cell over eight words or with a full stop.
//

@testable import Fichero
import Testing

struct ActivityStateGlyphTests {
    typealias Fix = ActivityPaneFixture

    @Test("each state's one glyph: a spinner for running, a hollow circle waiting, a red X failed, its word for VoiceOver")
    func glyphs() {
        #expect(ActivityPane.glyph(Fix.row("r", .running)) == .init(symbol: nil, word: "Running", isFailure: false))
        #expect(ActivityPane.glyph(Fix.row("w", .waiting)).symbol == "circle")
        #expect(ActivityPane.glyph(Fix.row("d", .done)) == .init(symbol: "checkmark.circle.fill", word: "Done", isFailure: false,
                                                              isSuccess: true), "done is green (`activity.pane.done-is-green`)")
        #expect(ActivityPane.glyph(Fix.row("h", .partial)).isSuccess, "partial: the check in green")
        #expect(!ActivityPane.glyph(Fix.row("w2", .waiting)).isSuccess && !ActivityPane.glyph(Fix.row("f2", .failed)).isSuccess)
        #expect(ActivityPane.glyph(Fix.row("f", .failed)) == .init(symbol: "xmark.circle.fill", word: "Failed", isFailure: true))
        #expect(ActivityPane.glyph(Fix.row("p", .paused)).symbol == "pause.circle")
        #expect(ActivityPane.glyph(Fix.row("s", .cancelled)).symbol == "stop.circle")
        #expect(ActivityPane.glyph(Fix.row("k", .notRun)).symbol == "minus")
        var stopping = Fix.row("x", .running)
        stopping.transientState = "Stopping"
        #expect(ActivityPane.glyph(stopping) == .init(symbol: nil, word: "Stopping", isFailure: false))
    }

    @Test("a row that is not failed or held writes no state word; a running row writes no clock time")
    func noStateWord() {
        for phase: ActivityMonitorRow.Phase in [.running, .waiting, .done, .cancelled] {
            #expect(ActivityPane.stateLine(Fix.row("x", phase)).isEmpty)
        }
        let running = Fix.row("r", .running, started: Fix.day, done: 3, total: 10)
        #expect(!ActivityPane.cellWords(running).joined().contains(":"), "no 14:02 on a running row")
    }

    @Test("the text budget: every fixture row's cells hold at most eight words and no full stop")
    func budget() {
        var failed = Fix.row("f", .failed)
        failed.failure = .init(kind: "missing-key", words: "There is no key for OpenRouter.", fix: "Add a key in Settings.",
                               actions: ["open-settings"], rowWords: "No key for OpenRouter.")
        var long = Fix.row("l", .failed)
        long.reason = "The provider refused the page because the request was too large for its context window."
        let rows = ActivityPane.outline([Fix.letters, Fix.names, failed, long]) + ActivityPane.byFile([Fix.letters, Fix.names])
        for row in rows + rows.flatMap { $0.children ?? [] } {
            for words in ActivityPane.cellWords(row) {
                #expect(ActivityPane.words(words) <= ActivityPane.wordBudget, "\(words)")
                #expect(!words.contains(". ") && !words.hasSuffix("."), "\(words)")
            }
        }
        #expect(ActivityPane.stateLine(failed) == "No key for OpenRouter", "the kind's row words, never a cut sentence")
        #expect(ActivityPane.stateLine(long).isEmpty, "a sentence over the budget goes to the Inspector, not cut")
    }
}
