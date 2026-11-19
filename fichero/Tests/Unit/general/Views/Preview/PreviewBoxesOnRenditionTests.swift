@testable import Fichero
import Testing

/// #6420, #6448: one mapping of a segment onto the picture shown, and Select All over the page's segments on any rendition.
@Suite("Segments on a rendition (#6420, #6448)")
struct PreviewBoxesOnRenditionTests {
    private let photograph = (width: 2000, height: 3000)
    private let cropped = (width: 800, height: 1200)

    @Test("an edited picture draws frame_bbox at its own size; the original draws bbox at the photograph's")
    func mappingPerPicture() {
        let boxes: (bbox: [Double]?, frame: [Double]?) = ([100, 200, 300, 40], [10, 20, 30, 4])
        let edited = SegmentOnRendition.drawnBox(
            boxes: boxes, readFrom: "edited", followed: true, frameSize: cropped, photograph: photograph
        )
        #expect(edited?.box == [10, 20, 30, 4])
        #expect(edited?.image.width == 800)
        let original = SegmentOnRendition.drawnBox(
            boxes: boxes, readFrom: "original", followed: true, frameSize: cropped, photograph: photograph
        )
        #expect(original?.box == [100, 200, 300, 40])
        #expect(original?.image.width == 2000)
    }

    @Test("a picture whose place on the page is not known draws no box, and says why")
    func framelessDrawsNothing() {
        let boxes: (bbox: [Double]?, frame: [Double]?) = ([100, 200, 300, 40], nil)
        #expect(SegmentOnRendition.drawnBox(
            boxes: boxes, readFrom: "edited", followed: false, frameSize: cropped, photograph: photograph
        ) == nil)
        #expect(SegmentOnRendition.noBoxesNote(readFrom: "edited", followed: false) != nil)
    }

    @Test("Select All on a rendition whose frame is not the geometry's still selects the page's segments (#6448)")
    func selectAllOnARendition() {
        let levels = ["region", "line", "line", "line"]
        #expect(SegmentOnRendition.selectAllIndices(levels: levels, shown: [], frameMatches: false, isTextTool: false) == [0, 1, 2, 3])
        #expect(SegmentOnRendition.selectAllIndices(levels: levels, shown: [1, 2], frameMatches: false, isTextTool: false) == [0, 1, 2, 3])
    }

    @Test("Select All on the original selects what the overlay shows, else every box; the text tool takes the words")
    func selectAllOnTheOriginal() {
        let levels = ["region", "line", "word", "word"]
        #expect(SegmentOnRendition.selectAllIndices(levels: levels, shown: [1], frameMatches: true, isTextTool: false) == [1])
        #expect(SegmentOnRendition.selectAllIndices(levels: levels, shown: [], frameMatches: true, isTextTool: false) == [0, 1, 2, 3])
        #expect(SegmentOnRendition.selectAllIndices(levels: levels, shown: [1], frameMatches: true, isTextTool: true) == [2, 3])
        #expect(SegmentOnRendition.selectAllIndices(levels: ["line"], shown: [], frameMatches: true, isTextTool: true) == [0])
    }

    private func geometry() -> OCRGeometry {
        var region = OCRGeometryBox(text: "", bbox: [0.1, 0.1, 0.5, 0.5], level: "region")
        region.segmentId = "r1"
        var line = OCRGeometryBox(text: "a", bbox: [0.1, 0.1, 0.5, 0.1], level: "line")
        line.segmentId = "l1"
        var stray = OCRGeometryBox(text: "b", bbox: [0.2, 0.2, 0.1, 0.1], level: "line")
        stray.segmentId = "gone"
        return OCRGeometry(text: "", provider: "p", model: nil, boxes: [region, line, stray], renditionId: nil)
    }

    @Test("a followed rendition draws each segment's mapped box, normalised by the rendition's size, in the page's order")
    func mappedGeometryDrawsOnTheRendition() throws {
        let answer = SegmentBoxesOnRendition(
            followed: true, note: nil, size: CGSize(width: 800, height: 1200),
            boxes: ["r1": [80, 120, 400, 600], "l1": [80, 120, 400, 120]]
        )
        let mapped = try #require(SegmentOnRendition.mappedGeometry(geometry(), on: answer))
        #expect(mapped.boxes.count == 3)
        #expect(mapped.boxes[0].bbox == [0.1, 0.1, 0.5, 0.5])
        #expect(mapped.boxes[1].bbox == [0.1, 0.1, 0.5, 0.1])
        #expect(SegmentOnRendition.isDrawn(mapped.boxes[1]))
        #expect(!SegmentOnRendition.isDrawn(mapped.boxes[2]))
    }

    @Test("a rendition whose place on the page is not known maps nothing")
    func unfollowedMapsNothing() {
        let answer = SegmentBoxesOnRendition(followed: false, note: "not known", size: nil, boxes: [:])
        #expect(SegmentOnRendition.mappedGeometry(geometry(), on: answer) == nil)
    }

    @Test("the refusal for a geometry-writing edit on a mapped rendition says what to do")
    func editRefusalIsInWords() {
        #expect(SegmentOnRendition.editRefusal.contains("original"))
    }
}
