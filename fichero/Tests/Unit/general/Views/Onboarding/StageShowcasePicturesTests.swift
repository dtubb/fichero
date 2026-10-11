@testable import Fichero
import Foundation
import Testing

/// Set Up's stage pictures and the A/B/C comparison (#5668, `source.onboard.stages.shows-what-it-does`,
/// `.compares-candidates`), from the spec: every stage has its picture, 3 to 5 seconds long; Reduce Motion shows the
/// last frame still; the candidates' columns, at most three, each with its measures in words and Use This.
@MainActor
struct StageShowcasePicturesTests {
    @Test("every one of Set Up's thirteen stages has a picture and says what it shows")
    func everyStageHasAPicture() {
        #expect(StageShowcaseCatalogue.stageIds == SetupStages.all.map(\.id), "the same stages, in the same order")
        for stage in SetupStages.all {
            #expect(StageShowcaseCatalogue.hasPicture(stage.id), "\(stage.id) has no picture")
            #expect(StageShowcaseCatalogue.description(for: stage.id) != "What this stage does.", "\(stage.id) is described")
            let seconds = StageShowcasePlayback.duration(for: stage.id)
            #expect(seconds >= 3 && seconds <= 5, "\(stage.id) plays 3 to 5 seconds")
        }
    }

    /// WHY: with Reduce Motion the person sees what the stage does without anything moving.
    @Test("Reduce Motion shows the last frame, still; otherwise the picture plays from 0 to 1 and holds")
    func reduceMotionIsTheLastFrame() {
        let start = Date(timeIntervalSince1970: 1_000)
        #expect(StageShowcasePlayback.progress(at: start, startedAt: start, duration: 4, reduceMotion: true) == 1)
        #expect(StageShowcasePlayback.progress(at: start, startedAt: start, duration: 4, reduceMotion: false) == 0)
        #expect(StageShowcasePlayback.progress(at: start.addingTimeInterval(2), startedAt: start, duration: 4,
                                               reduceMotion: false) == 0.5)
        #expect(StageShowcasePlayback.progress(at: start.addingTimeInterval(9), startedAt: start, duration: 4,
                                               reduceMotion: false) == 1, "held at the last frame")
        #expect(StageShowcasePlayback.phase(1, from: 0.2, to: 0.6) == 1)
        #expect(StageShowcasePlayback.phase(0.1, from: 0.2, to: 0.6) == 0)
    }

    @Test("Normalise expands the example's abbreviations: tþo into tiempo, q́ into que")
    func normaliseExpands() throws {
        let example = try #require(StageShowcaseExample.bundled())
        let showcase = example.example.showcase(imageURL: example.imageURL)
        let line = showcase.lines[0].text
        #expect(NormalisePicture.expanded(line, showcase.expansions) == "enel tiempo que el escriuio, yental caso")
    }

    @Test("the text beside a sample page reveals as it is read and lights its marks")
    func textColumnRevealsAndLights() {
        let mark = StageShowcase.Mark(line: 0, start: 4, end: 9, kind: "place")
        let half = ShowcaseTextColumn.line("Cali Popayán", index: 0, revealedBefore: 0, revealed: 6, highlights: [])
        #expect(String(half.characters) == "Cali P")
        let lit = ShowcaseTextColumn.line("vive Cauca", index: 0, revealedBefore: 0, revealed: 99,
                                          highlights: [ShowcaseLit(mark: mark, colour: .green)])
        #expect(String(lit.characters) == "vive Cauca")
        #expect(lit.runs.contains { $0.backgroundColor != nil }, "the mark is lit")
    }

    private static let compared = """
    {"state":"done","candidates":[
      {"card":"kraken-catmus","name":"Kraken (CATMuS Medieval)","runs_on":"this-mac","local":true,"cer":0.041,"seconds":12,
       "per_page":[{"id":"p1","readings":[{"text":"enel tþo q́ el escriuio"}]}]},
      {"card":"apple-vision","name":"Apple Vision","runs_on":"this-mac","local":true,"agreement":0.72,"seconds":3.6,
       "per_page":[{"id":"p1","readings":[{"text":"enel tpo q el escriuio"}]}]},
      {"card":"qwen-vl","name":"Qwen2.5-VL 7B","runs_on":"cloud","local":false,"agreement":0.88,"seconds":30,
       "cost_usd":{"value":0.04,"basis":"estimate"},"per_page":[{"id":"p1","readings":[{"text":"en el tiempo"}]}]},
      {"card":"fourth","name":"A fourth","runs_on":"cloud"}]}
    """

    @Test("each compared candidate is a column, at most three, with its measures in words")
    func columnsAndMeasures() throws {
        let result = try JSONDecoder().decode(SetupStageTryResult.self, from: Data(Self.compared.utf8))
        let columns = StageCandidate.columns(result.candidates)
        #expect(columns.map(\.card) == ["kraken-catmus", "apple-vision", "qwen-vl"], "at most three")
        #expect(columns[0].measures == ["4.1% character errors", "12 s", "free, on this Mac"])
        #expect(columns[1].measures == ["72% agreement", "4 s", "free, on this Mac"])
        #expect(columns[2].measures.last == "about $0.04", "a cloud estimate says so")
        #expect(columns[0].showcase?.lines.map(\.text) == ["enel tþo q́ el escriuio"], "each plays its own result")
        #expect(columns[2].showcase?.picture == .sample(pageId: "p1"), "the same page for every column")
    }

    @Test("one candidate is one picture, on its own result; none plays the try or the example")
    func oneCandidateIsOnePicture() throws {
        let one = try JSONDecoder().decode(StageCandidate.self, from: Data("""
        {"card":"spacy","name":"spaCy","local":true,"per_page":[{"id":"p9","readings":[{"text":"Juan vende"}]}]}
        """.utf8))
        #expect(StageShowcaseSection.showcase(result: nil, single: one)?.picture == .sample(pageId: "p9"))
        #expect(StageShowcaseSection.showcase(result: nil, single: nil)?.isOwnPage == false, "the example")
        #expect(StageComparisonView.pictureSize(columns: 3).width < StageComparisonView.pictureSize(columns: 2).width)
    }
}
