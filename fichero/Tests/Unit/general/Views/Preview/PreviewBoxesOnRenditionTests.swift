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
}
