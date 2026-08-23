//
//  CanvasTintTests.swift
//  FicheroTests
//
//  §20.3 "Colour by" / §13.2 — re-encode, don't re-arrange: ask a new question
//  by changing what the cards SAY, not where they are. Re-arranging costs the
//  user's spatial memory every time; re-encoding costs nothing.
//
//  The property that makes colour information rather than decoration is
//  STABILITY: a folder is the same colour after a re-arrange, after a
//  reconcile, and after a relaunch. `stableAcrossLaunches` is the one that
//  would be expensive to discover in the wild, because the failure looks like
//  a redesign rather than a bug.
//

import CoreGraphics
@testable import Fichero
import Foundation
import simd
import Testing

private func node(_ id: String) -> SpatialNode {
    SpatialNode(id: id, roomId: "room", nodeType: .source, label: id,
                positionX: 0, positionY: 0, positionZ: 0)
}

@Suite("CanvasTint (§20.3 Colour by)")
struct CanvasTintTests {

    @Test("empty is NEUTRAL: every card keeps its kind tint")
    func emptyMeansNeutral() {
        #expect(!CanvasTint.neutral.isActive)
        #expect(CanvasTint.neutral.slot(for: "doc:a") == nil)
        #expect(CanvasTint(slots: [:]) == .neutral)
        #expect(CanvasTint.byValue([:]) == .neutral)
    }

    @Test("a card the producer has no value for keeps its kind tint too")
    func unknownCardsAreNotColoured() {
        let tint = CanvasTint.byValue(["doc:a": "folder-1"])
        #expect(tint.slot(for: "doc:a") != nil)
        #expect(tint.slot(for: "doc:b") == nil)
    }

    @Test("one colour per distinct value — the same colour every time")
    func sameValueSameColour() {
        let tint = CanvasTint.byValue([
            "doc:a": "folder-1", "doc:b": "folder-1", "doc:c": "folder-2",
        ])
        #expect(tint.slot(for: "doc:a") == tint.slot(for: "doc:b"))
        // Two values MAY collide in an 8-slot palette; what must never happen
        // is one value taking two colours.
        #expect(tint.slot(for: "doc:a") == CanvasTint.slot(forValue: "folder-1"))
        #expect(tint.slot(for: "doc:c") == CanvasTint.slot(forValue: "folder-2"))
    }

    @Test("colour is stable across launches — the reason this is not Hasher")
    func stableAcrossLaunches() {
        // Swift's Hasher is seeded per PROCESS, so a hash-derived colour is
        // stable within a launch and different after the next one: a board
        // that changes colours overnight, which is a trust bug rather than a
        // cosmetic one. These are the FNV-1a values; if the algorithm changes,
        // every user's board recolours and this test is the thing that says so.
        #expect(CanvasTint.slot(forValue: "folder-1") == CanvasTint.slot(forValue: "folder-1"))
        #expect(CanvasTint.slot(forValue: "") == 5)
        #expect(CanvasTint.slot(forValue: "completed") == 2)
        #expect(CanvasTint.slot(forValue: "processing") == 6)
    }

    @Test("colour does not depend on board position or ordering")
    func independentOfBoardOrder() {
        // Otherwise every re-arrange would be a disco and the colour would stop
        // meaning anything.
        let forward = CanvasTint.byValue(["doc:a": "x", "doc:b": "y", "doc:c": "z"])
        let shuffled = CanvasTint.byValue(["doc:c": "z", "doc:a": "x", "doc:b": "y"])
        #expect(forward == shuffled)
    }

    @Test("every slot lands inside the palette, whatever it is handed")
    func slotsStayInThePalette() {
        for value in ["", "a", "folder-99", "Ünicode ✓", String(repeating: "x", count: 5_000)] {
            let slot = CanvasTint.slot(forValue: value)
            #expect(slot >= 0 && slot < CanvasTint.paletteSize)
        }
        // Out-of-range slots from a producer are wrapped, negatives dropped.
        let raw = CanvasTint(slots: ["doc:a": CanvasTint.paletteSize + 2, "doc:b": -1])
        #expect(raw.slot(for: "doc:a") == 2)
        #expect(raw.slot(for: "doc:b") == nil)
    }

    @Test("every slot has a colour, and no slot can trap")
    func paletteCoversTheSlots() {
        // Negative, in-range and far-out-of-range all resolve — a producer
        // cannot crash the board with an arithmetic slip.
        for slot in [-9, -1, 0, 3, CanvasTint.paletteSize, 10_000] {
            _ = CanvasTintPainter.color(forSlot: slot)
        }
        // Slots wrap, so the palette is a cycle rather than a cliff.
        #expect(CanvasTintPainter.color(forSlot: 0) == CanvasTintPainter.color(forSlot: CanvasTint.paletteSize))
    }

    // MARK: Colour-by modes

    @Test("None colours nothing — it is the kind tint, which IS a colouring")
    func noneIsNotAColouring() {
        #expect(CanvasColourBy.off.value(for: document(id: "d1")) == nil)
    }

    @Test("each mode reads its own attribute")
    func modesReadTheirAttribute() {
        let doc = document(id: "d1", parentId: "folder-7", status: .failed)
        #expect(CanvasColourBy.folder.value(for: doc) == "folder-7")
        #expect(CanvasColourBy.status.value(for: doc) == "failed")
        #expect(CanvasColourBy.type.value(for: doc) == doc.docType.rawValue)
    }

    @Test("a document missing the attribute is left uncoloured, not mis-coloured")
    func missingAttributeIsNil() {
        // A top-level document has no parent; it must keep its kind tint rather
        // than joining an "empty folder" colour group.
        #expect(CanvasColourBy.folder.value(for: document(id: "d1", parentId: nil)) == nil)
    }

    @Test("a stored mode that means nothing falls back to no colouring")
    func storedFallsBack() {
        #expect(CanvasColourBy.stored("folder") == .folder)
        #expect(CanvasColourBy.stored("") == .off)
        #expect(CanvasColourBy.stored("byDate") == .off)
    }

    private func document(
        id: String, parentId: String? = nil, status: Status = .completed
    ) -> Document {
        Document(id: id, parentId: parentId, docType: .page, name: id, status: status)
    }
}

// MARK: - Nothing moves, nothing rebuilds

@Suite("Colour re-encodes in place (§13.2, #4409)")
struct CanvasTintDiffTests {

    private func state(_ tint: CanvasTint = .neutral, emphasis: CanvasEmphasis = .neutral) -> CanvasSceneState {
        var state = CanvasSceneState.resolve(
            nodes: ["a", "b", "c"].map(node), connections: [], links: [], layoutRows: [], items: [],
            defaultPlacement: .grid(columns: 3)
        )
        state.tint = tint
        state.emphasis = emphasis
        return state
    }

    @Test("a colouring change emits exactly one op, and it is setTint")
    func tintEmitsOneOp() {
        let coloured = CanvasTint.byValue(["a": "x"])
        #expect(CanvasSceneDiff.compute(from: state(), to: state(coloured)) == [.setTint(coloured)])
    }

    @Test("colour NEVER produces a layout op")
    func colourMovesNothing() {
        let before = state(CanvasTint.byValue(["a": "x", "b": "y"]))
        let after = state(CanvasTint.byValue(["a": "y", "b": "x", "c": "z"]))
        for op in CanvasSceneDiff.compute(from: before, to: after) {
            switch op {
            case .move, .resize, .insert, .remove, .updateContent:
                Issue.record("colour produced a layout op: \(op)")
            case .setTint, .setEmphasis, .setSelection, .setEdges:
                continue
            }
        }
        #expect(before.placeables.map(\.position) == after.placeables.map(\.position))
    }

    @Test("hue and strength are independent channels")
    func tintAndEmphasisDoNotInterfere() {
        // The whole reason colour is not multiplexed into emphasis: changing
        // one must say nothing about the other.
        let tint = CanvasTint.byValue(["a": "x"])
        let emphasis = CanvasEmphasis(weights: ["b": 1])
        #expect(CanvasSceneDiff.compute(from: state(tint), to: state(tint, emphasis: emphasis))
                    == [.setEmphasis(emphasis)])
        #expect(CanvasSceneDiff.compute(from: state(.neutral, emphasis: emphasis),
                                        to: state(tint, emphasis: emphasis)) == [.setTint(tint)])
    }

    @Test("clearing a colouring returns to neutral in one op, and re-setting is silent")
    func clearingAndIdempotence() {
        let tint = CanvasTint.byValue(["a": "x"])
        #expect(CanvasSceneDiff.compute(from: state(tint), to: state()) == [.setTint(.neutral)])
        #expect(CanvasSceneDiff.compute(from: state(tint), to: state(tint)).isEmpty)
    }

    @Test("a fresh scene is uncoloured")
    func defaultStateIsNeutral() {
        #expect(CanvasSceneState.empty.tint == .neutral)
    }
}

// MARK: - Wiring

struct CanvasTintWiringGuardTests {
    private func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private let renderers = [
        ["Views/Library/ViewModes/Canvas/2D/CanvasOrtho2DRenderer.swift",
         "Views/Library/ViewModes/Canvas/2D/CanvasOrtho2DRenderer+Ops.swift"],
        ["Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer.swift",
         "Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer+Ops.swift"],
    ]
    private let canvases = [
        "Views/Library/ViewModes/Canvas/2D/CanvasSceneView.swift",
        "Views/Library/ViewModes/Canvas/3D/CanvasSpaceView.swift",
    ]

    private func combined(_ paths: [String]) throws -> String {
        try paths.map { try appSource($0) }.joined(separator: "\n")
    }

    @Test("both renderers colour through the shared painter")
    func bothRenderersPaintTint() throws {
        for paths in renderers {
            let source = try combined(paths)
            #expect(source.contains("case .setTint(let newTint):"), "\(paths) ignores the colour channel")
            #expect(source.contains("CanvasTintPainter.apply("), "\(paths) rolled its own palette")
        }
    }

    @Test("colouring never rebuilds a card")
    func tintNeverReskins() throws {
        for paths in renderers {
            let source = try combined(paths)
            let tail = try #require(source.components(separatedBy: "case .setTint").last)
            // Bounded at the next case OR the switch's closing brace, whichever
            // comes first — a window that runs past the switch reports on the
            // methods below it, which is how the emphasis guard failed once.
            let end = ["\n        case ", "\n        }"]
                .compactMap { tail.range(of: $0)?.lowerBound }
                .min() ?? tail.endIndex
            let handler = String(tail[..<end])
            #expect(!handler.isEmpty)
            #expect(!handler.contains("reskinCard"), "\(paths) rebuilds cards to colour them")
            #expect(!handler.contains("makeCard"), "\(paths) rebuilds cards to colour them")
            #expect(handler.contains("repaintTint()"))
        }
    }

    @Test("a textured card keeps its page — legibility outranks the encoding")
    func texturedCardsAreNotTinted() throws {
        let painter = try appSource("Views/Library/ViewModes/Canvas/Engine/CanvasTintPainter.swift")
        #expect(painter.contains("guard !isTextured else { return }"))
        for paths in renderers {
            #expect(try combined(paths).contains("isTextured: isTextured("))
        }
    }

    @Test("both canvases show the strip and forward the one produced tint")
    func bothCanvasesShareTheStrip() throws {
        for path in canvases {
            let source = try appSource(path)
            #expect(source.contains("CanvasControlStrip()"), "\(path) has no control strip")
            #expect(source.contains("state.tint = tint"))
        }
        let host = try appSource("Views/Library/LibraryView+CanvasModes.swift")
        #expect(host.contains("CanvasTint.byValue("))
        #expect(host.contains("SpatialLibraryProjector.nodeId(forDocument:"))
        #expect(host.components(separatedBy: "tint: canvasTint").count - 1 == 2)
    }
}
