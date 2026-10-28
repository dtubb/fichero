@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `activity.run.stage-names-each-reader` (#6134): a stage that reads with several readers shows each one's sentence as the
/// engine sent it in the run status; a single reader shows nothing extra.
struct ActivityStageReadersTests {
    private func stage(_ readers: String) throws -> ActivityRecipeStage {
        let json = #"{"steps":["read"],"title":"Read","card":"read","state":"running","readers":\#(readers)}"#
        return ActivityRecipeStage(try JSONDecoder().decode(Components.Schemas.RecipeRunStep.self, from: Data(json.utf8)))
    }

    @Test func severalReadersShowTheirSentencesAsSent() throws {
        let two = try stage(
            #"[{"material":"handwritten","pages":3,"model":"a","state":"running","sentence":"Also reads handwritten pages with A"},"#
                + #"{"material":"print","pages":2,"model":"b","state":"waiting","sentence":"Also reads print pages with Apple Vision"}]"#)
        #expect(two.readerSentences == ["Also reads handwritten pages with A", "Also reads print pages with Apple Vision"])
        #expect(ActivityDetails.readerLines(of: [two, two]) == two.readerSentences, "a sentence is shown once")
    }

    @Test func aSingleReaderShowsNothingExtra() throws {
        let one = try stage(#"[{"material":"handwritten","pages":3,"model":"a","state":"running","sentence":"Also reads x with A"}]"#)
        #expect(one.readerSentences.isEmpty)
        #expect(try stage("[]").readerSentences.isEmpty)
    }

    /// #6091: a stage run on fewer pages than the project has carries Start's own count, as sent.
    @Test func aStageCarriesStartsCountOfWhatWasDone() throws {
        let json = #"{"steps":["read"],"card":"workflow","state":"running","note":"already done on 37 of 95 pages; runs on the other 58"}"#
        let stage = ActivityRecipeStage(try JSONDecoder().decode(Components.Schemas.RecipeRunStep.self, from: Data(json.utf8)))
        #expect(stage.note == "already done on 37 of 95 pages; runs on the other 58")
    }
}
