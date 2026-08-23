//
//  CanvasInteractionPolicyGuardTests.swift
//  FicheroTests
//
//  #4290 — source-surface guards for the 2D canvas GESTURE POLICY, split out of
//  `CanvasGridPlacementTests` (which pins the placement math). Deterministic, no
//  running app; mirrors `LibraryListModeGuardTests`.
//

import Foundation
import Testing

/// The gesture POLICY #4290 settled on: a plain drag moves the ITEM under the
/// pointer; panning the view needs Space held, with a cursor affordance. The
/// 2D canvas shipped with the inverse — any plain drag panned the camera, from a
/// gesture attached to the same view as the card drag — so these guard the
/// direction of the fix, which no unit test on the pure layers can see.
struct CanvasInteractionPolicyGuardTests {
    private func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private var sceneViewPath: String { "Views/Library/ViewModes/Canvas/2D/CanvasSceneView.swift" }

    @Test("panning requires Space; it is no longer what a plain drag does")
    func panRequiresModifier() throws {
        let source = try appSource(sceneViewPath)
        // Shape changed with the ghost-marquee fix (2026-08-22): pan moved to
        // .onChanged behind a positive spaceHeld guard; the policy is the same.
        #expect(source.contains("draggingNodeId == nil, spaceHeld else { return }"))
        #expect(source.contains("panCamera(by:"))
        // The old policy read `if shiftHeld { marquee } else { pan }` — a plain
        // drag panning. Nothing may reintroduce an unmodified pan.
        #expect(!source.contains("if shiftHeld {"))
    }

    @Test("the item drag stays enabled for plain drags and yields only to Space")
    func itemDragOwnsThePlainDrag() throws {
        let source = try appSource(sceneViewPath)
        #expect(source.contains("nodeDrag(in: geo.size), isEnabled: !spaceHeld"))
    }

    @Test("the pan/marquee gesture stands down while a card drag is live")
    func panDoesNotFightTheCardDrag() throws {
        let source = try appSource(sceneViewPath)
        // Both halves stand down: the marquee (.updating) resets its rect and
        // the pan (.onChanged) returns while a card drag or resize is live.
        #expect(source.contains("guard resizeHandle == nil, draggingNodeId == nil, !spaceHeld else {"))
        #expect(source.contains("guard resizeHandle == nil, draggingNodeId == nil, spaceHeld else { return }"))
    }

    @Test("the marquee rect cannot outlive a cancelled drag")
    func marqueeRectResetsOnCancel() throws {
        let source = try appSource(sceneViewPath)
        // Ghost-marquee fix (2026-08-22): SwiftUI never calls .onEnded on a
        // CANCELLED gesture (a competing recognizer winning, Space mid-drag,
        // focus loss), so a @State rect cleared only in .onEnded stayed
        // painted. @GestureState resets on end AND cancel.
        #expect(source.contains("@GestureState private var marqueeRect: CGRect?"))
        #expect(!source.contains("@State private var marqueeRect"))
        #expect(source.contains(".updating($marqueeRect)"))
    }

    @Test("Space is a visible mode: a cursor change, on a focusable canvas")
    func spaceHasAnAffordance() throws {
        let source = try appSource(sceneViewPath)
        #expect(source.contains("applyPanCursor"))
        #expect(source.contains("NSCursor.openHand"))
        // `.onKeyPress` only fires on a focused view.
        #expect(source.contains(".focusable()"))
    }

    @Test("the shared modifier tracker observes Space without swallowing it")
    func trackerObservesSpace() throws {
        let source = try appSource("Views/Library/ViewModes/Canvas/CanvasModifierTracker.swift")
        #expect(source.contains(".onKeyPress(.space, phases: [.down, .up])"))
        #expect(source.contains("return .ignored"))
    }

    @Test("the 2D canvas asks for the grid default, and the camera frames it")
    func canvasUsesGridDefault() throws {
        let source = try appSource(sceneViewPath)
        #expect(source.contains("defaultPlacement: .grid(columns:"))
        #expect(source.contains("needsFitOnNextContent = true"))
    }
}
