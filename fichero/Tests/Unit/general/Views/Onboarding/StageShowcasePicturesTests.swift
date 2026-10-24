@testable import Fichero
import FicheroAPIClient
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
        #expect(columns[0].measureWords == ["4.1% character errors", "12 s", "free, on this Mac"])
        #expect(columns[1].measureWords == ["72% agreement", "4 s", "free, on this Mac"])
        #expect(columns[2].measureWords.last == "about $0.04", "a cloud estimate says so")
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

    /// WHY (8f2635889): the engine measures by what the stage makes; the column says it in words of that kind.
    @Test("measures read in words by kind: text, shapes and items")
    func measuresByKind() throws {
        func candidate(_ measures: String) throws -> StageCandidate {
            try JSONDecoder().decode(StageCandidate.self, from: Data(#"{"card":"c","local":true,"measures":\#(measures)}"#.utf8))
        }
        #expect(try candidate(#"{"kind":"text","agreement":0.8,"cer":0.041}"#).quality == "4.1% character errors",
                "CER on corrected lines first")
        #expect(try candidate(#"{"kind":"text","agreement":0.8}"#).quality == "80% agreement")
        #expect(try candidate(#"{"kind":"shapes","agreement":0.8}"#).quality == "80% overlap")
        #expect(try candidate(#"{"kind":"items","agreement":0.5,"found":12,"only_this_found":3}"#).quality
                == "found 12, 3 only here")
        #expect(try candidate(#"{"kind":"items","found":7}"#).quality == "found 7")
        #expect(try candidate(#"{"kind":"shapes","agreement":0.8}"#).measureWords
                == ["80% overlap", "free, on this Mac"])
    }

    @Test("variant A's price before the Try reads 'up to', and a cost not measured says so")
    func upToAndNotMeasured() throws {
        func words(_ cost: String) throws -> [String] {
            try JSONDecoder().decode(StageCandidate.self, from: Data(
                #"{"card":"variant-a:x","local":false,"cost_usd":\#(cost)}"#.utf8)).measureWords
        }
        #expect(try words(#"{"value":0.05,"basis":"upper bound","measured":false,"from":"up to this"}"#) == ["up to $0.05"])
        #expect(try words(#"{"value":0.05,"basis":"upper bound","measured":false,"why":"no usage record","from":"x"}"#)
                == ["up to $0.05", "no usage record"], "typed flag and reason, not parsed English")
        #expect(try words(#"{"value":0.002,"basis":"measured","measured":true,"from":"run"}"#) == ["< $0.01"],
                "under a cent is not $0.00")
        #expect(try words(#"{"value":0.04,"basis":"measured","measured":true,"from":"run"}"#) == ["$0.04"])
    }

    /// A figure the engine could not work out says why in its words, never 0% or nothing (review 351); the names
    /// only this one found arrive as a list, whose count the column says.
    @Test("a missing figure shows the engine's words")
    func notMeasuredShowsItsWords() throws {
        func candidate(_ measures: String) throws -> StageCandidate {
            try JSONDecoder().decode(StageCandidate.self, from: Data(#"{"card":"c","local":true,"measures":\#(measures)}"#.utf8))
        }
        let words = "nothing to compare with: the other candidates found no lines"
        #expect(try candidate(#"{"kind":"shapes","not_measured":"\#(words)"}"#).quality == words)
        #expect(try candidate(#"{"kind":"text","not_measured":"couldn't measure: an empty reference"}"#).quality
                == "couldn't measure: an empty reference")
        #expect(try candidate(#"{"kind":"items","found":12,"only_this_found":["a","b","c"]}"#).quality
                == "found 12, 3 only here")
    }

    @Test("up to three candidates are chosen; none chosen asks for the engine's own")
    func choosingWhoToCompare() {
        var chosen: [String] = []
        for card in ["a", "b", "c", "d"] { chosen = StageCandidateChoice.toggle(card, in: chosen) }
        #expect(chosen == ["a", "b", "c"], "a fourth is not taken")
        chosen = StageCandidateChoice.toggle("b", in: chosen)
        #expect(chosen == ["a", "c"])
        #expect(StageCandidateChoice.request(chosen) == ["a", "c"])
        #expect(StageCandidateChoice.request([]) == nil, "none: the engine's own choice")
    }

    @Test("Compare on These Pages sends the cards chosen, and none when none are")
    func theTrySendsTheChoice() async throws {
        let store = SetupStageTryStore(client: CompareTryProtocol.client(), stageId: "read")
        store.chosenCandidates = ["kraken-catmus", "apple-vision"]
        await store.tryIt()
        #expect(CompareTryProtocol.bodies.last?["candidates"] as? [String] == ["kraken-catmus", "apple-vision"])
        store.chosenCandidates = []
        await store.tryIt()
        #expect(CompareTryProtocol.bodies.last?["candidates"] == nil)
    }
}

private final class CompareTryProtocol: URLProtocol {
    nonisolated(unsafe) static var bodies: [[String: Any]] = []

    static func client() -> FicheroClient {
        bodies = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CompareTryProtocol.self]
        return FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!, libraryPath: "/tmp/Compare.fichero",
                             session: URLSession(configuration: configuration))
    }

    override static func canInit(with request: URLRequest) -> Bool { true }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        var json = #"{"state":"done"}"#
        if request.httpMethod == "POST" {
            Self.bodies.append((try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:])
        } else {
            json = #"{"detail":"not stubbed"}"#
        }
        let status = request.httpMethod == "POST" ? 200 : 404
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

/// #6015: Compare on These Pages saves the screen's choices before the engine tries (it reads the saved setup).
struct CompareSavesTheScreenFirstTests {
    @Test func theCompareButtonsSaveBeforeTrying() throws {
        let samples = try AppSource.text("Views/Onboarding/Stages/SetupStageSamples.swift")
        #expect(samples.contains("await !saveFirst()"))
        #expect(!samples.contains("{ Task { await store.tryIt("), "a Compare button tries without saving the screen's choices first")
        let page = try AppSource.text("Views/Onboarding/Stages/SetupStagePage.swift")
        #expect(page.contains("saveFirst: { await store.save() }"))
    }
}

/// #6034: Compare on These Pages shows the candidates side by side on each page, then the plain list.
struct CompareSideBySideInlineTests {
    @Test func theSideBySideComesBeforeTheList() throws {
        let samples = try AppSource.text("Views/Onboarding/Stages/SetupStageSamples.swift")
        let columns = try #require(samples.range(of: "StageCompareColumns(pageId:"))
        let list = try #require(samples.range(of: "comparing = ComparedPage(id: pageId)"))
        #expect(columns.lowerBound < list.lowerBound, "the plain list comes after the side-by-side")
        let shared = try AppSource.text("Views/Onboarding/Stages/StageCompareWindow.swift")
        #expect(shared.contains("struct StageCompareColumns"))
        #expect(shared.contains("readings?.first?.text"), "each column shows the model's reading under its picture")
    }
}

/// ## 1033: Set Up's Compare line needs readiness, so its branch loads it.
struct SetUpCompareLineLoadsReadinessTests {
    @Test func theLineBranchLoadsTheStore() throws {
        let steps = try AppSource.text("Views/Onboarding/RecipeStepsView.swift")
        #expect(steps.contains("context.store.loadLatest()"))
    }
}
