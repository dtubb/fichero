@testable import Fichero
import Foundation
import Testing

/// A Preview Delete takes the segment with its box (#6419): boxes that are segments go through the audited `segment.delete`.
struct PreviewRegionDeleteTests {
    @Test("boxes that are all versioned segments are deleted as segments")
    func segmentsGoThroughSegmentDelete() {
        #expect(PreviewRegionDelete.door(selectionCount: 3, segmentCount: 3, versionedCount: 3) == .segments)
    }

    @Test("a box with no segment, or a segment with no version, keeps the artifact route")
    func everythingElseKeepsTheArtifactRoute() {
        #expect(PreviewRegionDelete.door(selectionCount: 3, segmentCount: 2, versionedCount: 2) == .artifact)
        #expect(PreviewRegionDelete.door(selectionCount: 2, segmentCount: 2, versionedCount: 1) == .artifact)
        #expect(PreviewRegionDelete.door(selectionCount: 0, segmentCount: 0, versionedCount: 0) == .artifact)
    }

    /// #6426: a marquee promoted on a segment pass is drawn as a polygon region on that pass.
    @Test("a marquee rect becomes the four corners of a region polygon, clockwise from the top left")
    func marqueeCorners() {
        #expect(SegmentShapes.corners(ofRect: [0.1, 0.2, 0.3, 0.4]) == [[0.1, 0.2], [0.4, 0.2], [0.4, 0.2 + 0.4], [0.1, 0.2 + 0.4]])
        #expect(SegmentShapes.corners(ofRect: [0.1]).isEmpty)
    }

    /// #6426: the `shownArtifactlessPassId` branch of `promoteMarquees` draws on the pass for the whole set only.
    @Test("marquees are drawn on the shown segment pass only for the whole set; otherwise the artifact route stays")
    func marqueesOnASegmentPass() {
        #expect(SegmentShapes.drawsMarqueesOnPass(passShown: true, onlyIndex: nil))
        #expect(!SegmentShapes.drawsMarqueesOnPass(passShown: true, onlyIndex: 1))
        #expect(!SegmentShapes.drawsMarqueesOnPass(passShown: false, onlyIndex: nil))
        #expect(!SegmentShapes.drawsMarqueesOnPass(passShown: false, onlyIndex: 0))
    }
}
