@testable import Fichero
import Foundation
import Testing

/// Where the readers disagree, the app's half (#5665, `source.disagree.*`), written from the spec: the route's
/// pinned shape is read as it stands; each word is tinted plain when unanimous, yellow from 0.6 up to 1, red below;
/// Next and Previous Doubtful Word walk the words below unanimous in reading order and wrap; a word's popover lists
/// its variants most readers first, with the readers by label and how many of how many; fewer than two readings
/// is nothing to compare. Through the real store, over a stubbed source until the engine's route exists.
@MainActor
struct ReadingDisagreementTests {
    /// Two lines read by four readers, as `GET /api/documents/{page_id}/disagreement` answers.
    static let json = """
    {"page_id":"p1","readers":[{"id":"k","label":"Kraken"},{"id":"v","label":"Apple Vision"},
      {"id":"q1","label":"Comma Qwen, run 1"},{"id":"q2","label":"Comma Qwen, run 2"}],
     "page_agreement":0.81,"normalised_as":"as_written",
     "lines":[
      {"segment_id":"l1","reference_reader":"k","text":"vende una casa","agreement":0.75,"words":[
        {"text":"vende","char_start":0,"char_end":5,"bbox":[10,20,60,18],"agreement":1,
         "variants":[{"text":"vende","readers":["k","v","q1","q2"]}]},
        {"text":"una","char_start":6,"char_end":9,"bbox":null,"agreement":0.75,
         "variants":[{"text":"vna","readers":["q2"]},{"text":"una","readers":["k","v","q1"]}]},
        {"text":"casa","char_start":10,"char_end":14,"agreement":0.5,
         "variants":[{"text":"casa","readers":["k","v"]},{"text":"cosa","readers":["q1"]},{"text":"","readers":["q2"]}]}]},
      {"segment_id":"l2","reference_reader":"v","text":"en Istmina","agreement":0.88,"words":[
        {"text":"en","char_start":0,"char_end":2,"agreement":1,"variants":[{"text":"en","readers":["k","v","q1","q2"]}]},
        {"text":"Istmina","char_start":3,"char_end":10,"agreement":0.25,
         "variants":[{"text":"Istmina","readers":["v"]},{"text":"Ystmina","readers":["k","q1","q2"]}]}]}]}
    """

    static func page() throws -> ReadingDisagreement {
        try ReadingDisagreement.decode(Data(json.utf8))
    }

    private typealias Ref = ReadingDisagreement.WordRef

    @Test("the route's shape is read as the spec pins it")
    func readsTheShape() throws {
        let page = try Self.page()
        #expect(page.readers.map(\.label) == ["Kraken", "Apple Vision", "Comma Qwen, run 1", "Comma Qwen, run 2"])
        #expect(page.pageAgreement == 0.81 && page.normalisedAs == "as_written")
        #expect(page.lines.map(\.segmentId) == ["l1", "l2"])
        #expect(page.lines[0].referenceReader == "k" && page.lines[0].text == "vende una casa")
        let first = page.lines[0].words[0]
        #expect(first.charStart == 0 && first.charEnd == 5 && first.bbox == [10, 20, 60, 18])
        #expect(page.lines[0].words[1].bbox == nil, "a word the reading does not place has no box")
        #expect(page.isComparable)
    }

    /// WHY: the tint is the lens. Unanimous must stay plain (a page of agreement is a plain page), and the
    /// boundaries must not drift: 0.6 is still yellow, just under it red.
    @Test("each word is plain when unanimous, yellow from 0.6 up to 1, red below 0.6")
    func tintMapping() {
        #expect(DisagreementTint.of(1) == .unanimous)
        #expect(DisagreementTint.of(0.9999999999) == .unanimous, "a rounding of 1 is unanimous")
        #expect(DisagreementTint.of(0.99) == .some)
        #expect(DisagreementTint.of(0.75) == .some)
        #expect(DisagreementTint.of(0.6) == .some)
        #expect(DisagreementTint.of(0.59) == .most)
        #expect(DisagreementTint.of(0.25) == .most)
        #expect(DisagreementTint.of(0) == .most)
        #expect(DisagreementTint.unanimous.color == .clear, "plain: no tint at all")
    }

    /// WHY: correcting goes doubtful word by doubtful word, in the order the page reads, never skipping one and
    /// never stopping on a word everyone agreed on.
    @Test("Next Doubtful Word walks the words below unanimous in reading order and wraps; Previous goes back")
    func navigationOrder() throws {
        let page = try Self.page()
        #expect(page.doubtfulRefs == [Ref(line: 0, word: 1), Ref(line: 0, word: 2), Ref(line: 1, word: 1)])

        var cursor: Ref?
        var walked: [Ref] = []
        for _ in 0..<4 {
            cursor = page.doubtful(after: cursor)
            walked.append(try #require(cursor))
        }
        #expect(walked == [Ref(line: 0, word: 1), Ref(line: 0, word: 2), Ref(line: 1, word: 1), Ref(line: 0, word: 1)],
                "wraps at the page's end")

        #expect(page.doubtful(before: nil) == Ref(line: 1, word: 1), "Previous with nothing selected starts at the end")
        #expect(page.doubtful(before: Ref(line: 1, word: 1)) == Ref(line: 0, word: 2))
        #expect(page.doubtful(before: Ref(line: 0, word: 1)) == Ref(line: 1, word: 1), "wraps at the page's start")
        #expect(page.doubtful(after: Ref(line: 1, word: 0)) == Ref(line: 1, word: 1),
                "from a unanimous word, the next doubtful one")
    }

    @Test("with every word unanimous there is no doubtful word, and the commands have nowhere to go")
    func noDoubtfulWords() throws {
        let unanimous = Self.json
            .replacingOccurrences(of: #""agreement":0.75,"#, with: #""agreement":1,"#)
            .replacingOccurrences(of: #""agreement":0.5,"#, with: #""agreement":1,"#)
            .replacingOccurrences(of: #""agreement":0.25,"#, with: #""agreement":1,"#)
        let page = try ReadingDisagreement.decode(Data(unanimous.utf8))
        #expect(page.doubtfulRefs.isEmpty)
        #expect(page.doubtful(after: nil) == nil && page.doubtful(before: nil) == nil)
    }

    /// WHY: the popover answers "who read it otherwise?": the reading most readers gave first, each reader by
    /// name, and a reader that read nothing there said so rather than shown as a blank row.
    @Test("a word's popover lists its variants most readers first, with the readers and how many of how many")
    func popoverContents() throws {
        let page = try Self.page()
        let una = try #require(page.word(Ref(line: 0, word: 1)))
        #expect(page.variantRows(for: una) == [
            .init(text: "una", readers: "Kraken, Apple Vision, Comma Qwen, run 1", count: "3 of 4"),
            .init(text: "vna", readers: "Comma Qwen, run 2", count: "1 of 4")
        ], "most readers first, whatever order the engine sent")
        let casa = try #require(page.word(Ref(line: 0, word: 2)))
        #expect(page.variantRows(for: casa).map(\.text) == ["casa", "cosa", "(nothing)"],
                "equal counts keep the engine's order; a reader with nothing there says so")
        #expect(page.variantRows(for: casa).last?.readers == "Comma Qwen, run 2")
    }

    @Test("the Inspector's figures are the page's and each line's, labelled agreement")
    func inspectorFigures() throws {
        let page = try Self.page()
        #expect(ReadingDisagreement.percent(0.81) == "81% agreement")
        let rows = ReadingAgreementFigures.lineRows(page)
        #expect(rows.map(\.title) == ["Line 1", "Line 2"])
        #expect(rows.map(\.figure) == ["75% agreement", "88% agreement"])
    }

    @Test("with fewer than two readings there is nothing to compare")
    func fewerThanTwo() throws {
        let one = #"{"page_id":"p1","readers":[{"id":"k","label":"Kraken"}],"page_agreement":null,"lines":[]}"#
        let page = try ReadingDisagreement.decode(Data(one.utf8))
        #expect(!page.isComparable)
        #expect(page.pageAgreement == nil && page.lines.isEmpty)
    }

    @Test("the store reads a page once from its source and walks the selection through the doubtful words")
    func storeWalksTheSelection() async throws {
        var asked: [String] = []
        let store = ReadingDisagreementStore(source: { pageId in
            asked.append(pageId)
            return try Self.page()
        })
        await store.load(pageId: "p1")
        #expect(asked == ["p1"])
        #expect(store.disagreement(of: "p1")?.lines.count == 2)

        #expect(store.selectNextDoubtful(on: "p1"))
        #expect(store.selected["p1"] == Ref(line: 0, word: 1))
        #expect(store.selectNextDoubtful(on: "p1"))
        #expect(store.selected["p1"] == Ref(line: 0, word: 2))
        #expect(store.selectPreviousDoubtful(on: "p1"))
        #expect(store.selected["p1"] == Ref(line: 0, word: 1))
        #expect(!store.selectNextDoubtful(on: "unread"), "a page not read has nowhere to go")
    }

    @Test("until the engine has the route, the lens says so in words")
    func notYetBuilt() async {
        let store = ReadingDisagreementStore()
        await store.load(pageId: "p1")
        #expect(store.pages["p1"] == .unavailable("Fichero cannot compare this page's readers yet."))
    }

    @Test("the lens is a Reader lens of its own, named for what it shows")
    func theLens() {
        #expect(ReaderLens.disagreement.title == "Where the Readers Disagree")
        #expect(ReaderLens.disagreement.tab == .disagreement)
        #expect(ReaderLens.lens(for: .disagreement, representation: .entities) == .disagreement)
    }
}
