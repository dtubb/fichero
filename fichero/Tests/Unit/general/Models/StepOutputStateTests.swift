@testable import Fichero
import Foundation
import Testing

/// The four states of a stage page's output column, and the dimmed stale result (`wide.output.four-states`,
/// `wide.output.stale-says-so`). The state comes from the engine's try result, never from the app's guess.
@MainActor
struct StepOutputStateTests {
    private func result(_ json: String) throws -> SetupStageTryResult {
        try JSONDecoder().decode(SetupStageTryResult.self, from: Data(json.utf8))
    }

    private func state(_ result: SetupStageTryResult?, refusal: String? = nil, cost: String? = nil, trying: Bool = false,
                       revision: String? = "r1") -> StepOutputState {
        StepOutputState.of(StepOutputInputs(result: result, refusal: refusal, costQuestion: cost, isTrying: trying,
                                            currentRevision: revision, pages: 5, estimate: "about 2 minutes, free on this Mac"))
    }

    @Test("no result is the not-tried state with the engine's time and cost, and one page is said in the singular")
    func notTried() {
        #expect(state(nil) == .notTried(line: "Try on these 5 pages, about 2 minutes, free on this Mac"))
        #expect(StepOutputState.notTriedLine(pages: 1, estimate: nil) == "Try on this page")
    }

    @Test("a waiting or running try is running, with the engine's reason; a try just pressed is running too")
    func running() throws {
        let waiting = try result(#"{"state":"waiting","waiting_for":"the lane"}"#)
        #expect(state(waiting) == .running(words: "the lane"))
        #expect(state(nil, trying: true) == .running(words: "Starting the try."))
    }

    @Test("pressing Try again over a finished result is running, never done, until the new try is under way")
    func pressedAgain() throws {
        let done = try result(#"{"state":"done","answers_revision":"r1"}"#)
        #expect(state(done, trying: true) == .running(words: "Starting the try."))
    }

    @Test("a failed try or a refusal says the engine's sentence, never blank")
    func failed() throws {
        let failed = try result(#"{"state":"failed","error":"No page image"}"#)
        #expect(state(failed) == .failed(words: "No page image"))
        #expect(state(nil, refusal: "Too many pages") == .failed(words: "Too many pages"))
        #expect(state(try result(#"{"state":"failed"}"#)) == .failed(words: "The try did not finish. Try it again."))
    }

    @Test("a cost question is asked before a try that uses the cloud")
    func costFirst() {
        #expect(state(nil, cost: "About $0.12") == .notTried(line: "About $0.12"))
    }

    @Test("a stale result dims only with the wide Set Up on (release shows today's window)")
    func staleDimsOnlyOnTheFlag() {
        #expect(StepOutputStateView.opacity(of: .done(stale: true), wideSetUp: true) == 0.5)
        #expect(StepOutputStateView.opacity(of: .done(stale: true), wideSetUp: false) == 1)
        #expect(StepOutputStateView.opacity(of: .done(stale: false), wideSetUp: true) == 1)
    }

    @Test("a finished try is done, and stale when the answers have changed since")
    func doneAndStale() throws {
        let done = try result(#"{"state":"done","answers_revision":"r1"}"#)
        #expect(state(done) == .done(stale: false))
        #expect(state(done, revision: "r2") == .done(stale: true))
        let older = try result(#"{"state":"done"}"#)
        #expect(state(older, revision: "r2") == .done(stale: false), "a result that names no revision is not called stale")
    }

    @Test("the tie figures and the two line counts decode from the try result")
    func figuresDecode() throws {
        let made = try result("""
        {"state":"done","tie":{"counts":{"tied":9,"doubtful":2,"untied":1,"drafts":1},
          "pages":{"p1":{"tied":9,"doubtful":2,"untied":1,"draft":false}}},
         "line_counts":{"pages":{"p1":{"photograph":5,"clarified":12}},"not_clarified":["p2"]}}
        """)
        #expect(made.tie?.counts?.doubtful == 2 && made.tie?.pages?["p1"]?.tied == 9)
        #expect(made.lineCounts?.pages?["p1"]?.clarified == 12 && made.lineCounts?.notClarified == ["p2"])
    }
}
