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
}
