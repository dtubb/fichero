@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The compare view's model (`wide.compare.*`): modes, the legend, the wipe handle, rows and the one-sentence states.
struct CompareViewTests {
    private func answer(readers: [String] = ["a", "b"], lines: String? = nil) throws -> Components.Schemas.CompareReadersResponse {
        let readerJSON = readers.map { #"{"id":"\#($0)","label":"Reader \#($0)","kind":"candidate"}"# }.joined(separator: ",")
        let linesJSON = lines ?? """
        {"order":0,"differs":true,"picked_by_person":false,"readings":[{"reader_id":"a","text":"Yten dixo"},{"reader_id":"b","text":"Item dixo"}],
         "words":[{"text":"Yten","char_start":0,"char_end":4,"agreement":0.5,"variants":[{"text":"Item","readers":["b"]}]},
                  {"text":"dixo","char_start":5,"char_end":9,"agreement":1,"variants":[]}]},
        {"order":1,"differs":false,"picked_by_person":false,"readings":[{"reader_id":"a","text":"que"},{"reader_id":"b","text":"que"}],"words":[]}
        """
        let json = #"{"page_id":"p1","readers":[\#(readerJSON)],"lines":[\#(linesJSON)]}"#
        return try JSONDecoder().decode(Components.Schemas.CompareReadersResponse.self, from: Data(json.utf8))
    }

    @Test("Side by side is the Mac's default and Overlay the iPhone's")
    func defaultModes() throws {
        #expect(CompareViewModel(answer: try answer(), platform: .mac).mode == .sideBySide)
        #expect(CompareViewModel(answer: try answer(), platform: .iPad).mode == .sideBySide)
        #expect(CompareViewModel(answer: try answer(), platform: .iPhone).mode == .overlay)
    }

    @Test("Overlay's legend hides and shows a reader's boxes")
    func legend() throws {
        var model = CompareViewModel(answer: try answer(), platform: .mac)
        #expect(model.drawn.map(\.id) == ["a", "b"])
        model.toggle(reader: "a")
        #expect(model.drawn.map(\.id) == ["b"])
        model.toggle(reader: "a")
        #expect(model.drawn.map(\.id) == ["a", "b"])
    }

    @Test("Wipe: A left, B right, the handle kept inside the picture, the text wiping with it")
    func wipe() throws {
        var model = CompareViewModel(answer: try answer(), platform: .mac)
        #expect(model.wipePair?.a.id == "a" && model.wipePair?.b.id == "b")
        model.moveHandle(to: 1.7)
        #expect(model.handle == 1)
        model.moveHandle(to: -3)
        #expect(model.handle == 0)
        model.moveHandle(to: 0.5)
        #expect(model.charactersOnA(of: "Yten dixo") == 4)
    }

    @Test("rows carry one text per reader, the differing words, and the filter keeps the lines that differ")
    func rows() throws {
        var model = CompareViewModel(answer: try answer(), platform: .mac)
        #expect(model.rows.count == 2)
        #expect(model.rows[0].texts == ["Yten dixo", "Item dixo"] && model.rows[0].differingWords == ["Yten"])
        #expect(model.rows[1].differs == false && model.rows[1].differingWords.isEmpty)
        model.onlyDiffering = true
        #expect(model.rows.map(\.id) == [0])
    }

    @Test("one candidate, no readers or no lines each say one sentence; a candidate that did not read says why")
    func states() throws {
        #expect(CompareViewModel(answer: try answer(), platform: .mac).emptyState == nil)
        #expect(CompareViewModel(answer: try answer(readers: []), platform: .mac).emptyState == "Nothing has read this page yet.")
        #expect(CompareViewModel(answer: try answer(readers: ["a"]), platform: .mac).emptyState?.hasPrefix("Only one reader") == true)
        #expect(CompareViewModel(answer: try answer(lines: ""), platform: .mac).emptyState?.hasPrefix("No reader has lines") == true)
        let silent = try answer(lines: #"{"order":0,"differs":false,"picked_by_person":false,"readings":[{"reader_id":"a","text":"x"}],"words":[]}"#)
        let model = CompareViewModel(answer: silent, platform: .mac)
        #expect(model.notReadBecause(reader: "b") == "Reader b did not read this page.")
        #expect(model.notReadBecause(reader: "a") == nil)
    }

    @Test("Use This sends the representation of the reading that counted, never a reader id")
    func pickExpectsARepresentation() throws {
        let lines = """
        {"order":0,"segment_id":"s1","counting_reader_id":"a","differs":true,"picked_by_person":false,
         "readings":[{"reader_id":"a","text":"Yten","representation_id":"rep-a"},{"reader_id":"b","text":"Item","representation_id":"rep-b"}],"words":[]}
        """
        let model = CompareViewModel(answer: try answer(lines: lines), platform: .mac)
        #expect(model.pick(readerId: "b", onLine: 0) == .init(segmentId: "s1", representationId: "rep-b", expectedCountingId: "rep-a"))
        #expect(model.pick(readerId: "c", onLine: 0) == nil)
    }

    @Test("a line with no counting reading sends no expectation; a try's line (no segment) cannot be picked")
    func pickEdges() throws {
        let lines = """
        {"order":0,"segment_id":"s1","differs":true,"picked_by_person":false,
         "readings":[{"reader_id":"a","text":"x","representation_id":"rep-a"}],"words":[]},
        {"order":1,"differs":true,"picked_by_person":false,
         "readings":[{"reader_id":"a","text":"y","representation_id":"rep-a2"}],"words":[]}
        """
        let model = CompareViewModel(answer: try answer(lines: lines), platform: .mac)
        #expect(model.pick(readerId: "a", onLine: 0)?.expectedCountingId == nil)
        #expect(model.pick(readerId: "a", onLine: 1) == nil)
        #expect(model.rows.map(\.canPick) == [true, false])
    }

    @Test("a line box in image pixels is scaled to the canvas, not multiplied by it")
    func boxScalesFromImagePixels() {
        let rect = CompareViewModel.boxRect([100, 50, 200, 20], image: (1000, 500), canvas: CGSize(width: 500, height: 250))
        #expect(rect == CGRect(x: 50, y: 25, width: 100, height: 10))
        #expect(CompareViewModel.boxRect([1, 2, 3, 4], image: nil, canvas: CGSize(width: 10, height: 10)) == nil)
        #expect(CompareViewModel.boxRect([1, 2, 3], image: (10, 10), canvas: CGSize(width: 10, height: 10)) == nil)
    }

    @Test("the box drawn follows the picture shown: the edited image's frame_bbox, or the photograph's bbox")
    func drawnBoxFollowsThePicture() {
        let bbox: [Double] = [100, 50, 200, 20], frameBbox: [Double] = [10, 5, 20, 2]
        let photo = (width: 1000, height: 500), edited = (width: 400, height: 300)
        // No edits (a rendition is not what the picture shows): the photograph's bbox and size.
        let plain = CompareViewModel.drawnBox(boxes: (bbox, frameBbox), readFrom: "rendition", followed: true,
                                              frameSize: edited, photograph: photo)
        #expect(plain?.box == bbox && plain?.image.width == 1000)
        let original = CompareViewModel.drawnBox(boxes: (bbox, nil), readFrom: "original", followed: false,
                                                 frameSize: nil, photograph: photo)
        #expect(original?.box == bbox)
        // Saved edits and the lines' place known: the frame's box in the edited image's size.
        let followed = CompareViewModel.drawnBox(boxes: (bbox, frameBbox), readFrom: "edited", followed: true,
                                                 frameSize: edited, photograph: photo)
        #expect(followed?.box == frameBbox && followed?.image.width == 400 && followed?.image.height == 300)
        // Saved edits and the place unknown: no box rather than a wrong one.
        #expect(CompareViewModel.drawnBox(boxes: (bbox, nil), readFrom: "edited", followed: false,
                                          frameSize: edited, photograph: photo) == nil)
    }

    @Test("a page with saved edits and unknown lines says why it has no boxes; other pages say nothing")
    func noBoxesSaysWhy() {
        #expect(CompareViewModel.noBoxesNote(readFrom: "edited", followed: false) != nil)
        #expect(CompareViewModel.noBoxesNote(readFrom: "edited", followed: true) == nil)
        #expect(CompareViewModel.noBoxesNote(readFrom: "original", followed: false) == nil)
        #expect(CompareViewModel.noBoxesNote(readFrom: nil, followed: false) == nil)
    }
}
