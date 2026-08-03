@testable import Fichero
import XCTest

/// Both canvases pan, on both platforms, through one camera model each (#4408).
///
/// The issue was reported as "two-finger scroll does not pan the canvas". The
/// first fix wired scroll on macOS for the 2D canvas and left two halves:
///
///   * the overlay was `#if os(macOS)`, so on iPad there was no pan at ALL —
///     touch has no scroll event and no Space key, and one finger was already
///     the marquee;
///   * the 3D/spatial view the issue explicitly also names had no scroll
///     handler of any kind, exactly the state 2D was in before.
///
/// These assert the STRUCTURE, because a gesture cannot be unit-tested: a real
/// `NSEvent` scroll and a real two-finger `UIPanGestureRecognizer` sequence
/// cannot be synthesized in-process. What can be pinned is that neither surface
/// grew a second camera-movement path — which is the part that would rot.
final class CanvasPanInputParityTests: XCTestCase {

    // MARK: - Both platforms have an input

    /// The iPad half. A spatial canvas you cannot pan on a touch device is not
    /// a spatial canvas.
    func testBothCanvasesWireATouchPanForIPad() throws {
        for path in [
            "Views/Library/ViewModes/Canvas/2D/CanvasSceneView.swift",
            "Views/Library/ViewModes/Canvas/3D/SpaceSceneView.swift"
        ] {
            let source = Self.code(of: try AppSource.text(path))
            XCTAssertTrue(
                source.contains("CanvasTouchPanView"),
                "\(path) has no touch pan — iPad cannot pan it at all"
            )
            XCTAssertTrue(
                source.contains("CanvasScrollPanView"),
                "\(path) lost its macOS scroll pan"
            )
        }
    }

    /// Two fingers exactly. One stays with the marquee, and three or more are
    /// the system's (app switcher, split view) — intercepting either is how a
    /// canvas gesture starts stealing from something that already worked.
    func testTouchPanClaimsExactlyTwoFingers() throws {
        let source = Self.code(
            of: try AppSource.text("Views/Library/ViewModes/Canvas/CanvasTouchPan.swift")
        )

        XCTAssertTrue(source.contains("minimumNumberOfTouches = 2"))
        XCTAssertTrue(source.contains("maximumNumberOfTouches = 2"))
    }

    /// Pinch is also two fingers. Two that move together pan and two that
    /// spread zoom, at the same time — refusing simultaneity makes a pinch that
    /// drifts feel broken.
    func testTouchPanRunsAlongsidePinchZoom() throws {
        let source = Self.code(
            of: try AppSource.text("Views/Library/ViewModes/Canvas/CanvasTouchPan.swift")
        )

        XCTAssertTrue(source.contains("shouldRecognizeSimultaneouslyWith"))
    }

    /// Both capture views are transparent to every other input, which is what
    /// keeps selection, marquee and node-drag working underneath.
    func testBothBridgesAreTransparentToOtherInput() throws {
        let scroll = Self.code(
            of: try AppSource.text("Views/Library/ViewModes/Canvas/CanvasScrollPan.swift")
        )
        let touch = Self.code(
            of: try AppSource.text("Views/Library/ViewModes/Canvas/CanvasTouchPan.swift")
        )

        XCTAssertTrue(scroll.contains("func hitTest(_ point: NSPoint) -> NSView? { nil }"))
        XCTAssertTrue(touch.contains("func point(inside point: CGPoint, with event: UIEvent?) -> Bool { false }"))
    }

    // MARK: - Neither surface grew a second camera path

    /// The 2D canvas converts every pan input through the one shared
    /// calibration, so scroll, touch and Space-drag stay in step.
    func testTheTwoDCanvasHasOneConversion() throws {
        let source = Self.code(
            of: try AppSource.text("Views/Library/ViewModes/Canvas/2D/CanvasSceneView.swift")
        )

        // Scroll and touch both call the same entry point.
        XCTAssertEqual(
            source.components(separatedBy: "scrollPanCamera(by: delta, in: geo.size)").count - 1,
            2,
            "scroll and touch must feed the same camera entry point"
        )
        XCTAssertTrue(source.contains("Canvas2DProjection.cameraPanDelta"))
    }

    /// The 3D view derives its right/up basis and speed ONCE, so the drag path
    /// and the incremental path cannot drift. It deliberately does NOT share
    /// the 2D conversion — see the doc on `panCameraIncrementally`.
    func testTheThreeDViewDerivesItsBasisOnce() throws {
        let source = Self.code(
            of: try AppSource.text("Views/Library/ViewModes/Canvas/3D/SpaceSceneView.swift")
        )

        XCTAssertTrue(source.contains("private var panBasis:"))
        XCTAssertEqual(
            source.components(separatedBy: "let basis = panBasis").count - 1,
            2,
            "the drag path and the incremental path must both read the one basis"
        )
        // The trig belongs to `panBasis` alone; a second copy is the drift.
        XCTAssertEqual(
            source.components(separatedBy: "SIMD3<Float>(cos(yaw), 0, -sin(yaw))").count - 1,
            1,
            "the camera basis is computed in more than one place again"
        )
    }

    // MARK: - Support

    private static func code(of source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> Substring in
                guard let marker = line.range(of: "//") else { return line }
                return line[line.startIndex..<marker.lowerBound]
            }
            .joined(separator: "\n")
    }
}
