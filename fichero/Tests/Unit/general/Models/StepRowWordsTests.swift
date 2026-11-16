@testable import Fichero
import Foundation
import Testing

/// The step rows' words (`wide.nomodel.*`, `wide.picker.empty-says-why`, `wide.faded.line-counts-before-and-after`).
struct StepRowWordsTests {
    @Test("a job with no model says Fichero does it and how; a model job says nothing")
    func ficheroDoesThisOne() {
        #expect(StepRowWords.ficheroDoesThisOne(howItWorks: "How it works: it cuts at the gutter.") == "Fichero does this one: How it works: it cuts at the gutter.")
        #expect(StepRowWords.ficheroDoesThisOne(howItWorks: nil) == nil)
        #expect(StepRowWords.ficheroDoesThisOne(howItWorks: "  ") == nil)
    }

    @Test("an empty picker says why and the one fix")
    func emptyPicker() {
        #expect(StepRowWords.emptyPicker(why: "No model on this Mac does this yet", fix: "download Qwen3 4B (2.1 GB) or add a cloud key")
                == "No model on this Mac does this yet: download Qwen3 4B (2.1 GB) or add a cloud key")
        #expect(StepRowWords.emptyPicker(why: "No model does this step yet: Fichero has no card for it", fix: nil)
                == "No model does this step yet: Fichero has no card for it")
        #expect(StepRowWords.emptyPicker(why: nil, fix: "x") == nil)
    }

    @Test("the tie's figures, singular and plural, with the draft pages and the link only when there is something to show")
    func tieFigures() throws {
        let counts = try JSONDecoder().decode(SetupStageTryResult.Tie.Counts.self,
                                              from: Data(#"{"tied":9,"doubtful":2,"untied":1,"drafts":1}"#.utf8))
        #expect(StepRowWords.tieFigures(counts) == "9 lines tied, 2 doubtful, 1 could not be tied; 1 page left as a draft")
        #expect(StepRowWords.offersUntied(counts))
        let clean = try JSONDecoder().decode(SetupStageTryResult.Tie.Counts.self, from: Data(#"{"tied":1}"#.utf8))
        #expect(StepRowWords.tieFigures(clean) == "1 line tied, 0 doubtful, 0 could not be tied")
        #expect(!StepRowWords.offersUntied(clean))
        #expect(StepRowWords.tieFigures(nil) == nil)
    }

    @Test("the two line counts side by side")
    func lineCounts() throws {
        let both = try JSONDecoder().decode(SetupStageTryResult.LineCounts.Both.self, from: Data(#"{"photograph":5,"clarified":12}"#.utf8))
        #expect(StepRowWords.lineCounts(both) == "5 lines on the photograph, 12 on the clarified copy")
    }
}
