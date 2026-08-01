import XCTest

/// #4408 — two-finger scroll did not pan the 2D canvas; panning required
/// holding Space. `e4bfe9ede` wired a scroll handler shipped with NO test —
/// found during the #4421 guardrail-fires audit ("hard to test" isn't the
/// same as "tested").
///
/// What's genuinely testable without a live trackpad, and what isn't:
///
/// - The delta CONVERSION (`Canvas2DProjection.cameraPanDelta`) is pure and
///   already covered by `Canvas2DGestureMathTests` — the scroll path calls
///   the exact same function the drag path does, so those tests already
///   protect the calibration for both inputs.
/// - The WIRING — that a scroll event actually reaches `renderer.panCamera`
///   — is a source-surface fact this file locks: `#4408` added a SECOND
///   call site, and a caller-count regression (the wiring silently dropped
///   again) is exactly the "wired-but-unfed" shape that keeps recurring in
///   this codebase.
/// - The DIRECTION READ (`isDirectionInvertedFromDevice`, not a hardcoded
///   sign) is locked structurally: the source must read the event property,
///   never assign a bare `+`/`-` sign to the delta unconditionally.
/// - Actual NSEvent delivery — whether AppKit hands `scrollWheel(with:)` a
///   real two-finger gesture, with correct `scrollingDeltaX/Y` and
///   `isDirectionInvertedFromDevice` for the live system scroll-direction
///   preference — CANNOT be simulated in a unit test; `NSEvent` scroll
///   events aren't synthesizable with controlled trackpad semantics outside
///   AppKit's own event pipeline. See "Manual check" below.
final class CanvasScrollPanTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    // MARK: - Wiring: panCamera has a scroll caller, not just the drag one

    func testPanCameraHasBothADragCallerAndAScrollCaller() throws {
        let source = try Self.appSource("Views/Library/ViewModes/Canvas/2D/CanvasSceneView.swift")
        // `panCamera(worldDelta:` had exactly ONE caller before #4408 (the
        // Space-drag path). Counting call sites — not just checking one
        // exists — is what catches "the scroll handler stopped calling it"
        // without catching a comment mentioning the name.
        let callSites = source.components(separatedBy: "renderer.panCamera(").count - 1
        XCTAssertEqual(
            callSites, 2,
            "expected exactly 2 callers (drag + scroll #4408); got \(callSites) — " +
            "the scroll path either isn't wired or a caller was silently removed"
        )
    }

    func testScrollPathConvertsThroughTheSameCalibrationAsDrag() throws {
        let source = try Self.appSource("Views/Library/ViewModes/Canvas/2D/CanvasSceneView.swift")
        let scrollFn = source
            .components(separatedBy: "private func scrollPanCamera(by delta: CGSize, in size: CGSize) {")[1]
            .components(separatedBy: "\n    }")[0]
        // Same conversion the drag path uses — no second scale factor.
        XCTAssertTrue(scrollFn.contains("Canvas2DProjection.cameraPanDelta("))
        XCTAssertTrue(scrollFn.contains("renderer.panCamera("))
    }

    func testScrollOverlayIsWiredIntoTheSceneAndHitTestTransparent() throws {
        let source = try Self.appSource("Views/Library/ViewModes/Canvas/2D/CanvasSceneView.swift")
        XCTAssertTrue(source.contains("CanvasScrollPanView"))
        XCTAssertTrue(source.contains("scrollPanCamera(by: delta, in: geo.size)"))
        // If this stops being hit-test transparent, selection/drag/marquee
        // break underneath it — a regression a user finds immediately but
        // no test currently catches structurally besides this line existing.
        XCTAssertTrue(source.contains(".allowsHitTesting(false)"))
    }

    // MARK: - Direction: read from the event, never a hardcoded sign

    func testDirectionIsReadFromTheEventNotHardcoded() throws {
        let source = try Self.appSource("Views/Library/ViewModes/Canvas/CanvasScrollPan.swift")
        XCTAssertTrue(
            source.contains("event.isDirectionInvertedFromDevice"),
            "the sign must come from the OS's natural-scrolling preference, " +
            "not a bare + or - baked into the source"
        )
        // Momentum/inertial phases must not be filtered — that's what makes
        // trackpad panning glide instead of feeling dead.
        XCTAssertFalse(
            source.contains("event.phase == .ended"),
            "filtering to .ended would cut the momentum glide short"
        )
    }

    func testCaptureViewIsTransparentToEveryOtherInput() throws {
        let source = try Self.appSource("Views/Library/ViewModes/Canvas/CanvasScrollPan.swift")
        XCTAssertTrue(source.contains("override func hitTest(_ point: NSPoint) -> NSView? { nil }"))
    }

    // MARK: - What this file cannot verify

    /// NSEvent scroll delivery (real `scrollingDeltaX/Y`, real
    /// `isDirectionInvertedFromDevice` for the live "natural scrolling"
    /// system preference) cannot be constructed in a unit test — it comes
    /// from AppKit's own event pipeline reading actual trackpad hardware.
    /// Manual check required before this can be called verified end to end:
    ///   1. Open a library in Canvas (2D) view mode.
    ///   2. Two-finger-scroll on a trackpad. Content must move WITH the
    ///      fingers (matches Space-drag's existing feel).
    ///   3. Toggle System Settings → Trackpad → "Natural scrolling" and
    ///      repeat step 2 — content must still move the same way relative
    ///      to the fingers (the inversion read must cancel the OS flip both
    ///      ways, not just one).
    ///   4. Confirm a flick continues to glide briefly after fingers lift
    ///      (momentum phases reaching the handler).
    /// This test exists so that gap is a documented follow-up in the suite,
    /// not a silent absence.
    func testManualVerificationIsRequired() {
        XCTAssertTrue(
            true,
            "Real scroll-gesture delivery needs a human + trackpad — see this " +
            "test's doc comment for the exact steps. Not exercised by CI."
        )
    }
}
