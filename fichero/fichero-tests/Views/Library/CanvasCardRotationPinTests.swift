//
//  CanvasCardRotationPinTests.swift
//  FicheroTests
//
//  §18.1 defect 2 — per-card tilt. At a dozen cards a slight rotation reads as
//  scattered papers on a desk; at 2,228 it breaks the alignment the eye needs to
//  scan a grid and makes every card a subtly different shape, so none can be
//  compared. Per §13.5, a channel carrying no data should be zero.
//
//  Surveying the live path first turned up that there is nothing to fix and
//  something to KEEP: the engine 3D renderer (`CanvasScene3DRenderer`, the path
//  behind the default-on `canvasRealityKit3D` flag) applies no orientation to a
//  card at all, and `CanvasItemLayout.angle` already defaults to 0 on both
//  sides of the wire. So this file is a PIN, not a change — the zero is easy to
//  lose to one decorative line in `makeCard`, and these tests are what would
//  catch that.
//
//  KNOWN EXCEPTION, deliberately not covered: the legacy `SpaceSceneView`
//  (~line 743) applies `node.rotationY` from the backend node. That is the
//  flag-OFF renderer and the canvas fold-in program deletes it rather than
//  fixing it, so pinning it here would pin code that is on its way out.
//
//  The other half of the ruling is that angle stays USER-SETTABLE: a
//  hand-arranged panel should be able to be deliberately casual (the
//  Warburg/pile affordance). What changes is the DEFAULT, never the capability.
//

import Foundation
@testable import Fichero
import Testing

@Suite("Card rotation stays zero by default (§18.1 defect 2)")
struct CanvasCardRotationPinTests {

    @Test("a layout row is unrotated unless something asks for an angle")
    func angleDefaultsToZero() {
        #expect(CanvasItemLayout(itemId: "n0").angle == 0)
        #expect(CanvasItemLayout(itemId: "n0", x: 3, y: -2, z: 1).angle == 0)
    }

    @Test("but the angle is still settable, and survives a round-trip")
    func angleRemainsUserSettable() throws {
        let tilted = CanvasItemLayout(itemId: "n0", angle: 0.21)
        #expect(tilted.angle == 0.21)
        // Through the save body the store actually sends…
        #expect(tilted.asSaveItem.angle == 0.21)
        // …and through Codable, which is how a row survives a restart.
        let decoded = try JSONDecoder().decode(
            CanvasItemLayout.self, from: try JSONEncoder().encode(tilted)
        )
        #expect(decoded.angle == 0.21)
    }

    @Test("a default row round-trips as unrotated")
    func defaultRowRoundTripsUnrotated() throws {
        // Codable is synthesized here, so `angle` is carried explicitly rather
        // than defaulted on the way in — which is what makes the zero worth
        // pinning: it travels, it is not re-derived.
        let row = CanvasItemLayout(itemId: "n0", x: 1, y: 2, z: 0)
        let decoded = try JSONDecoder().decode(
            CanvasItemLayout.self, from: try JSONEncoder().encode(row)
        )
        #expect(decoded.angle == 0)
        #expect(row.asSaveItem.angle == 0)
    }
}

// MARK: - The renderer applies no decorative tilt

/// Only a source scan can see a card being rotated: the tilt was decoration
/// applied at build time, invisible to every pure layer.
struct CanvasCardRotationGuardTests {
    private func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    /// The body of `makeCard` — where a decorative rotation would be added.
    private func makeCardBody() throws -> String {
        let source = try appSource("Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer.swift")
        guard let start = source.range(of: "private func makeCard(") else {
            Issue.record("makeCard has been renamed — re-point this guard")
            return ""
        }
        let rest = source[start.lowerBound...]
        guard let end = rest.range(of: "\n    private func ", range: rest.index(rest.startIndex, offsetBy: 1)..<rest.endIndex) else {
            return String(rest)
        }
        return String(rest[..<end.lowerBound])
    }

    @Test("no card is built with an orientation")
    func cardsAreBuiltUnrotated() throws {
        let body = try makeCardBody()
        #expect(!body.isEmpty)
        #expect(!body.contains("orientation"))
        #expect(!body.contains("simd_quatf"))
        // The channel must not be re-opened through the layout row either: a
        // tilt driven by `angle` would be legitimate, but it is not what this
        // renderer does today and the pin should notice it arriving.
        #expect(!body.contains("angle"))
    }

    @Test("the only rotation in the 3D renderer is a connector aiming itself")
    func onlyConnectorsRotate() throws {
        let source = try appSource("Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer.swift")
        let rotations = source.components(separatedBy: "entity.orientation").count - 1
        // Exactly one: makeConnector points a cylinder along its own span.
        #expect(rotations == 1)
        #expect(source.contains("entity.orientation = simd_quatf(from: SIMD3<Float>(0, 1, 0), to: delta / length)"))
    }

    @Test("nothing seeds a per-card angle when a board is projected")
    func theProjectorSeedsNoTilt() throws {
        // SpatialLibraryProjector is where 2,228 row-less cards get their
        // defaults; a golden-angle phyllotaxis is a POSITION rule, and it must
        // not grow a rotation rule.
        let source = try appSource("Services/SpatialLibraryProjector.swift")
        #expect(!source.contains("rotationX:"))
        #expect(!source.contains("rotationY:"))
        #expect(!source.contains("rotationZ:"))
    }
}
