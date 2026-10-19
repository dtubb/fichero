@testable import Fichero
import Foundation
import Testing

/// What a Set Up stage's picture plays on (#5668, `source.onboard.stages.shows-what-it-does`): the person's own sample
/// page when the stage's try made something, else the example shipped with the app (Diálogo de la Lengua p. 18, BNE,
/// DILE CC BY-SA 4.0), whose data decodes, lies on its picture and carries its credit.
@MainActor
struct StageShowcaseTests {
    private func example() throws -> (example: StageShowcaseExample, imageURL: URL) {
        try #require(StageShowcaseExample.bundled(), "the example page ships in the app bundle")
    }

    @Test("the example's data decodes, and every box and baseline lies on its picture")
    func exampleDecodesAndFits() throws {
        let (example, url) = try example()
        #expect(example.width == 669 && example.height == 994)
        #expect(example.lines.count == 21)
        #expect(example.fitsImage, "a box off the page would be drawn beside it")
        #expect(FileManager.default.fileExists(atPath: url.path))
        let showcase = example.showcase(imageURL: url)
        for mark in showcase.names + showcase.dates + (showcase.search?.matches ?? []) {
            #expect(showcase.text(of: mark) != nil, "every mark points into its line")
        }
        #expect(showcase.text(of: showcase.search!.matches[0])?.lowercased() == "historia")
    }

    /// WHY: the transcription is CC BY-SA 4.0; its licence and credit travel with it and the person sees the credit.
    @Test("the example keeps its licence and credit, and shows a short credit linked to the licence")
    func exampleCarriesItsCredit() throws {
        let (example, url) = try example()
        #expect(example.licence.contains("CC BY-SA 4.0"))
        #expect(example.credit.contains("Biblioteca Nacional de España") && example.credit.contains("DILE"))
        let showcase = example.showcase(imageURL: url)
        #expect(showcase.credit == "Example: BNE · DILE, CC BY-SA 4.0")
        #expect(showcase.licenceURL?.absoluteString == "https://creativecommons.org/licenses/by-sa/4.0/")
        #expect(showcase.sourceURL?.absoluteString == "https://dile.dragoman.org/1/18.pdf")
        let halves = ShowcaseCredit.halves(of: "Example: BNE · DILE, CC BY-SA 4.0")
        #expect(halves.source == "Example: BNE · DILE" && halves.licence == "CC BY-SA 4.0")
        #expect(!showcase.isOwnPage)
    }

    @Test("the person's own sample page is chosen over the example when the stage's try read it")
    func ownPageFirst() throws {
        let json = """
        {"state":"done","per_page":[{"id":"page-7","readings":[{"text":"Juan de la Cruz\\nvende una casa en Istmina"}]}],
         "names":[{"name":"Istmina","type":"place"}]}
        """
        let result = try JSONDecoder().decode(SetupStageTryResult.self, from: Data(json.utf8))
        let chosen = try #require(StageShowcaseSource.showcase(for: result, example: try example()))
        #expect(chosen.picture == .sample(pageId: "page-7"))
        #expect(chosen.isOwnPage && chosen.credit == nil)
        #expect(chosen.lines.map(\.text) == ["Juan de la Cruz", "vende una casa en Istmina"])
        #expect(chosen.names == [StageShowcase.Mark(line: 1, start: 18, end: 25, kind: "place")])
        #expect(chosen.lines.allSatisfy { $0.box == nil }, "a sample's reading has no boxes: none are drawn")
    }

    @Test("with no try, or a try that read nothing, the example plays")
    func exampleOtherwise() throws {
        let example = try example()
        #expect(StageShowcaseSource.showcase(for: nil, example: example)?.isOwnPage == false)
        let empty = try JSONDecoder().decode(SetupStageTryResult.self, from: Data(#"{"state":"done"}"#.utf8))
        #expect(StageShowcaseSource.showcase(for: empty, example: example)?.isOwnPage == false)
    }

    @Test("the page is fitted into the picture's space, centred, and its pixels placed by one scale")
    func geometryFits() {
        let geometry = ShowcaseGeometry(imageSize: CGSize(width: 669, height: 994), in: CGSize(width: 360, height: 220))
        #expect(abs(geometry.drawn.height - 220) < 0.001, "a tall page fills the height")
        #expect(abs(geometry.drawn.midX - 180) < 0.001, "centred")
        let line = geometry.rect(CGRect(x: 0, y: 0, width: 669, height: 994))
        #expect(abs(line.width - geometry.drawn.width) < 0.001)
        #expect(geometry.point(CGPoint(x: 0, y: 0)) == geometry.drawn.origin)
    }
}
