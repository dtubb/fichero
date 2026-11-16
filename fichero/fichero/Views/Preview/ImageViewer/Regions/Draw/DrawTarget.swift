import Foundation

/// Where a finished Preview drawing is sent (#6412). A drawing used to be sent only when the shown boxes came from a pass
/// with no artifact; on every other page it was logged "not sent" and lost. Every drawing now has one engine destination,
/// or is refused out loud.
enum DrawTarget: Equatable {
    /// `segment.create` on this pass.
    case createOnPass(String)
    /// A region on an artifact whose boxes are not segment rows yet: the regions route converts the page and adds it.
    case addRegionToArtifact(artifactId: String, bbox: [Double])
    /// Nothing can take it (no pass shown, or a line on a page whose boxes are not segments yet).
    case refused(String)

    /// - Parameters:
    ///   - passId: the pass the shown boxes came from.
    ///   - artifactId: the artifact that pass came from, nil for an imported pass.
    ///   - passIsProvisional: the shown segments are the seam's view of an unconverted result, not rows.
    static func resolve(
        kind: SegmentShapes.DrawKind, points: [[Double]], passId: String?, artifactId: String?, passIsProvisional: Bool
    ) -> DrawTarget {
        guard let passId else { return .refused("no pass is shown") }
        guard artifactId != nil, passIsProvisional else { return .createOnPass(passId) }
        guard kind == .polygon, let artifactId else { return .refused("a line needs the page's boxes saved as segments first") }
        return .addRegionToArtifact(artifactId: artifactId, bbox: SegmentShapes.bounds(points))
    }
}
