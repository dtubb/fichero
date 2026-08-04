//
//  CanvasSelectionVisualGuardTests.swift
//  FicheroTests
//
//  #4409 — source-surface guards for the BLUE FLASH.
//
//  The flash was not a stray SwiftUI selection style leaking onto the canvas.
//  It was self-inflicted: both RealityKit renderers drew selection inside
//  `makeCard`, so `setSelection` had to `reskinCard` every id whose state
//  flipped — destroying the `ModelEntity` and rebuilding it with a flat
//  `UnlitMaterial(color:)` until an ASYNC thumbnail reload restored the page
//  texture. A source node's base colour is `.systemBlue`, which is the blue,
//  and the diff reskinned the SYMMETRIC DIFFERENCE, so the card being
//  deselected flashed too.
//
//  These guards exist because the fix is an ABSENCE — no selection in
//  `makeCard`, no reskin in `setSelection` — and an absence is exactly what a
//  later edit restores without noticing. A unit test on the pure layers cannot
//  see it; only the source can.
//

import Foundation
import Testing

@Suite("Canvas selection never rebuilds a card (#4409)")
struct CanvasSelectionVisualGuardTests {

    private func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private var ortho2DPath: String { "Views/Library/ViewModes/Canvas/2D/CanvasOrtho2DRenderer.swift" }
    private var ortho2DSelectionPath: String {
        "Views/Library/ViewModes/Canvas/2D/CanvasOrtho2DRenderer+Selection.swift"
    }
    private var scene3DPath: String { "Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer.swift" }
    private var controllerPath: String {
        "Views/Library/ViewModes/Canvas/Engine/CanvasInteractionController.swift"
    }

    /// The 2D host and its resize extension, concatenated: both halves of one
    /// type, split only for file length, so a guard about the view should not
    /// care which half a line landed in.
    private func hostSource() throws -> String {
        try appSource("Views/Library/ViewModes/Canvas/2D/CanvasSceneView.swift")
            + appSource("Views/Library/ViewModes/Canvas/2D/CanvasSceneView+Resize.swift")
    }

    /// The renderers' `applyOne` bodies, which is where the defect lived.
    private func renderers() throws -> [(name: String, source: String)] {
        [("2D ortho", try appSource(ortho2DPath)), ("3D scene", try appSource(scene3DPath))]
    }

    @Test("neither renderer reskins a card when the selection changes")
    func setSelectionDoesNotReskin() throws {
        for (name, source) in try renderers() {
            // The exact shape of the defect: fan the symmetric difference out
            // to `reskinCard`. Nothing may bring it back under any renderer.
            #expect(
                !source.contains("for id in changed { reskinCard(id) }"),
                "\(name) rebuilds cards on selection — that is the blue flash"
            )
            #expect(!source.contains("symmetricDifference"), "\(name) still fans a selection change out to cards")
        }
    }

    @Test("neither renderer's card builder knows whether it is selected")
    func makeCardIsSelectionBlind() throws {
        for (name, source) in try renderers() {
            // A card that knows it is selected must be REBUILT when that
            // changes. Keeping `makeCard` selection-blind is what makes the
            // flash impossible rather than merely absent.
            #expect(
                !source.contains("if selection.contains(placeable.id) {"),
                "\(name) draws selection inside makeCard, so selection forces a rebuild"
            )
        }
    }

    @Test("both renderers draw selection into a separate decoration root")
    func decorationHasItsOwnRoot() throws {
        for (name, source) in try renderers() {
            #expect(source.contains("CanvasSelectionDecorator("), "\(name) has no decoration owner")
            #expect(source.contains("root.addChild(decorator.root)"), "\(name) never adds its decoration root")
            #expect(source.contains("refreshSelectionDecoration"), "\(name) never redraws decoration")
        }
    }

    @Test("a committed resize keeps the card's materials instead of rebuilding it")
    func resizeDoesNotDropTheTexture() throws {
        let source = try appSource(ortho2DPath) + appSource(ortho2DSelectionPath)
        // Same failure mode as selection, one op along: `reskinCard` on
        // `.resize` would drop the loaded page texture and flash the base
        // colour every time a handle is released.
        #expect(source.contains("resizeCardInPlace"))
        #expect(source.contains("entity.model?.mesh = MeshResource.generatePlane"))
    }

    @Test("decoration entities are never mistaken for placeables by the host's gestures")
    func hostSkipsDecoration() throws {
        let source = try hostSource()
        // Decoration lives in the same scene, so `.targetedToAnyEntity()` will
        // target it. A tap dispatched with a frame's synthetic name would
        // select a placeable that does not exist and clear the real selection;
        // a drag would move the card the user is trying to resize.
        #expect(source.contains("guard !CanvasSelectionFrame.isDecoration(id) else { return }"))
        #expect(source.contains("CanvasSelectionFrame.handle(fromEntityName:"))
    }

    @Test("a resize drag does not also marquee or pan")
    func resizeDoesNotFightTheOtherGestures() throws {
        let source = try hostSource()
        // A resize starts on a HANDLE, so `draggingNodeId` stays nil and the
        // background gesture's existing guard does not cover it.
        #expect(source.contains("guard resizeHandle == nil else { marqueeRect = nil; return }"))
        #expect(source.contains("if resizeHandle == nil, draggingNodeId == nil, !spaceHeld"))
    }

    @Test("resizing is undoable, through the same UndoManager pattern a move uses")
    func resizeIsUndoable() throws {
        let controller = try appSource(controllerPath)
            + appSource("Views/Library/ViewModes/Canvas/Engine/CanvasInteractionController+Undo.swift")
        #expect(controller.contains("func registerResizeUndo("))
        #expect(controller.contains("undoManager.setActionName(\"Resize\")"))
        #expect(try hostSource().contains("registerResizeUndo("))
    }

    @Test("a resize persists through the exactly-one-row save, carrying the position with it")
    func resizePersistsOneRow() throws {
        let controller = try appSource(controllerPath)
            + appSource("Views/Library/ViewModes/Canvas/Engine/CanvasInteractionController+Undo.swift")
        // Size rides with a position because a placeable in its default grid
        // slot has NO row yet: writing a size-only row would default x/y/z to
        // the origin and teleport the card there.
        #expect(controller.contains("case resize(id: String, size: CGSize, position: SIMD3<Double>)"))
        #expect(controller.contains("await persistSingleRow(id: id, to: worldPosition, size: size, rollbackTo: nil)"))
        // And a plain MOVE must not clear a size the user set.
        #expect(controller.contains("size: CGSize? = nil"))
    }
}
