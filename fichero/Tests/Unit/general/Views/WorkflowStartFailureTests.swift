@testable import Fichero
import Foundation
import Testing

/// `runner.hand-run.same-contract`: a workflow or chain that cannot start is titled for a run, never "Import Error", and its
/// words are the engine's.
@Suite("Workflow start failure")
struct WorkflowStartFailureTests {
    private struct Refused: LocalizedError {
        var errorDescription: String? { "cannot apply the requested provider/model override" }
    }

    @Test("a workflow that did not start says so and carries the engine's words")
    func workflowStart() {
        let words = RunStartWords.workflowStartFailure(Refused())
        #expect(words == "Workflow failed to start: cannot apply the requested provider/model override")
        #expect(RunStartWords.alertTitle(for: words) == "Couldn't Start the Run")
    }

    @Test("nothing selected and a chain that cannot start are start failures too")
    func otherStarts() {
        #expect(RunStartWords.alertTitle(for: RunStartWords.noSelection) == "Couldn't Start the Run")
        #expect(RunStartWords.alertTitle(for: ChainRunWords.startFailure(Refused())) == "Couldn't Start the Run")
        #expect(RunStartWords.alertTitle(for: ChainRunWords.noProject) == "Couldn't Start the Run")
    }

    @Test("an import's failure keeps the import title")
    func importStays() {
        #expect(RunStartWords.alertTitle(for: "Import failed: disk full") == "Import Error")
        #expect(RunStartWords.alertTitle(for: nil) == "Import Error")
    }
}

@Suite("Chain run lost track")
struct ChainLostTrackTests {
    @Test("a chain the app cannot follow says so, in its own title, and says it may still be running")
    func lostTrack() {
        for words in [ChainRunWords.lostTrack(afterFailedPolls: 3), ChainRunWords.stoppedWatching] {
            #expect(RunStartWords.alertTitle(for: words) == "Chain Run")
            #expect(words.contains("may still be running"))
        }
    }
}
