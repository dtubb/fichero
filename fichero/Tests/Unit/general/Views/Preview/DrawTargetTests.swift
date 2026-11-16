@testable import Fichero
import Foundation
import Testing

/// #6412: a drawing made in the Preview is always sent to the engine or refused out loud, never dropped. What breaks
/// without these: a region or line drawn on a page whose shown pass has an artifact is logged "not sent" and is gone
/// after the page reloads.
@MainActor
@Suite(.tags(.paleography))
struct DrawTargetTests {
    private let square: [[Double]] = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.4], [0.1, 0.4]]
    private let stroke: [[Double]] = [[0.1, 0.2], [0.5, 0.2]]

    @Test("a pass with no artifact takes the drawing as one segment.create")
    func importedPass() {
        #expect(DrawTarget.resolve(kind: .polygon, points: square, passId: "p", artifactId: nil, passIsProvisional: false)
            == .createOnPass("p"))
    }

    @Test("a pass with an artifact whose boxes are segment rows takes segment.create too")
    func convertedArtifactPass() {
        #expect(DrawTarget.resolve(kind: .baseline, points: stroke, passId: "p", artifactId: "a", passIsProvisional: false)
            == .createOnPass("p"))
    }

    @Test("an unconverted artifact takes a region through the regions route, with the polygon's bounds")
    func unconvertedRegion() {
        #expect(DrawTarget.resolve(kind: .polygon, points: square, passId: "legacy:a", artifactId: "a", passIsProvisional: true)
            == .addRegionToArtifact(artifactId: "a", bbox: SegmentShapes.bounds(square)))
    }

    @Test("a line on an unconverted artifact, or with no pass shown, is refused, not dropped")
    func refused() {
        for target in [
            DrawTarget.resolve(kind: .baseline, points: stroke, passId: "legacy:a", artifactId: "a", passIsProvisional: true),
            DrawTarget.resolve(kind: .polygon, points: square, passId: nil, artifactId: nil, passIsProvisional: false)
        ] {
            guard case .refused = target else { Issue.record("expected a refusal, got \(target)"); continue }
        }
    }
}
