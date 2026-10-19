@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `source.onboard.stages.page-lists-found-models` and `compare-names-its-models` (#5808): the stage page lists the
/// engine's one candidate list, readers made for another period apart, and Compare names its models.
struct StageFoundModelsTests {
    private func candidates() throws -> [Components.Schemas.ModelCandidate] {
        try JSONDecoder().decode([Components.Schemas.ModelCandidate].self, from: Data("""
        [{"id":"k:20th","name":"CATMuS Print 20th century, a long full name that must wrap","source":"kraken-repository",
          "offered_because":"","pin":{},"jobs":["read-a-line"],"open_licence":true,"size":"16 MB","measured":"",
          "in_recipe_rules":true,"runs_where":"this_mac","availability":"installed","availability_words":"On this Mac",
          "link":"https://doi.org/10.5281/zenodo.2","other_period":false,"compared_by_default":true},
         {"id":"k:11th","name":"Model trained on 11th century manuscripts","source":"hugging-face",
          "offered_because":"","pin":{},"jobs":["read-a-line"],"open_licence":true,"size":"1 GB","measured":"",
          "in_recipe_rules":true,"runs_where":"this_mac","availability":"download","availability_words":"Download",
          "link":"https://huggingface.co/Org/Model","other_period":true,"compared_by_default":false}]
        """.utf8))
    }

    @Test("a reader made for another period is listed apart, and each candidate keeps its link and whole name")
    func otherPeriodsApart() throws {
        let list = try candidates()
        let groups = StageCandidateChooser.split(list)
        #expect(groups.fitting.map(\.id) == ["k:20th"])
        #expect(groups.otherPeriods.map(\.id) == ["k:11th"])
        #expect(list[0].link == "https://doi.org/10.5281/zenodo.2")
        #expect(list[0].name.hasSuffix("must wrap"), "the name arrives whole")
    }

    @Test("Compare names the models it runs when none is ticked, as the engine chose them")
    func comparesByName() throws {
        #expect(StageCandidateChooser.defaultNames(try candidates()) == ["CATMuS Print 20th century, a long full name that must wrap"])
        #expect(StageCandidateChooser.defaultNames([]).isEmpty)
    }

    @Test("a sample page is marked as the person's own and says whether its thumbnail is made")
    func samplesAreHis() throws {
        let page = try JSONDecoder().decode(Components.Schemas.SamplePage.self, from: Data(
            #"{"id":"a","name":"f. 1r","why":"your first page","yours":true,"thumbnail":false}"#.utf8))
        #expect(page.yours == true)
        #expect(page.thumbnail == false)
    }
}
