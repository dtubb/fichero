//
//  CanvasArrangementTests.swift
//  FicheroTests
//
//  §25.4 step 3 / §20.3 — "Arrange by" is the ONE picker that moves cards, and
//  R10 says the transition IS the information: switch arrangement and watch the
//  board fly, and what you learn in those 600ms (which cards did NOT move —
//  the ones you pinned) is not available any other way.
//
//  Three properties are pinned here, in order of how expensive they'd be to
//  discover live:
//   1. As Filed is today's behaviour RENAMED, not changed — the default board
//      cannot shift under anyone's feet;
//   2. a saved row survives every arrangement — pinning is what makes a
//      re-arrange safe to watch;
//   3. a re-arrange emits ONLY move ops — it can never become a rebuild.
//

import CoreGraphics
@testable import Fichero
import FicheroAPIClient
import Foundation
import simd
import Testing

private func sourceNode(_ id: String, label: String, kind: SpatialNodeType = .source) -> SpatialNode {
    SpatialNode(id: id, roomId: "room", nodeType: kind, label: label,
                positionX: 0, positionY: 0, positionZ: 0)
}

private func noteItem(_ id: String, text: String? = nil, kind: String = "note") throws -> CanvasItemDisplay {
    var payload: [String: Any] = ["id": id, "folderId": "scope", "kind": kind]
    if let text { payload["text"] = text }
    return try JSONDecoder().decode(
        CanvasItemDisplay.self, from: try JSONSerialization.data(withJSONObject: payload)
    )
}

@Suite("CanvasArrangement ordering (§20.3)")
struct CanvasArrangementTests {

    private let pages = [
        sourceNode("doc:3", label: "Charlie"),
        sourceNode("doc:1", label: "alpha"),
        sourceNode("doc:2", label: "Bravo"),
    ]

    @Test("As Filed keeps the order the library handed us")
    func asFiledIsIncomingOrder() {
        let slots = CanvasArrangement.slotIndices(.asFiled, nodes: pages, items: [])
        #expect(slots["doc:3"] == 0)
        #expect(slots["doc:1"] == 1)
        #expect(slots["doc:2"] == 2)
    }

    @Test("As Filed IS the pre-arrangement ordering — the default board did not move")
    func asFiledMatchesThePreArrangementOrder() throws {
        // The whole point of the rename. Before arrangements existed, `resolve`
        // slotted cards in its own walk order: nodes as given, then non-link
        // items. If As Filed ever diverges from that, every existing board
        // silently re-lays itself out on upgrade — the one outcome this feature
        // must not have.
        let items = [try noteItem("i0"), try noteItem("edge", kind: "link"), try noteItem("i1")]
        let arranged = CanvasSceneState.resolve(
            nodes: pages, connections: [], links: [], layoutRows: [], items: items,
            defaultPlacement: .grid(columns: 2), arrangement: .asFiled
        )
        // `.free` is the same ordering by another name: it only means "don't
        // re-arrange what I have not pinned".
        let free = CanvasSceneState.resolve(
            nodes: pages, connections: [], links: [], layoutRows: [], items: items,
            defaultPlacement: .grid(columns: 2), arrangement: .free
        )
        // And the default argument — what every untouched caller gets.
        let defaulted = CanvasSceneState.resolve(
            nodes: pages, connections: [], links: [], layoutRows: [], items: items,
            defaultPlacement: .grid(columns: 2)
        )
        #expect(arranged.placeables.map(\.position) == defaulted.placeables.map(\.position))
        #expect(free.placeables.map(\.position) == defaulted.placeables.map(\.position))
        #expect(arranged.placeables.map(\.id) == ["doc:3", "doc:1", "doc:2", "i0", "i1"])
    }

    @Test("Name sorts case-insensitively")
    func nameSortsCaseInsensitively() {
        let slots = CanvasArrangement.slotIndices(.name, nodes: pages, items: [])
        #expect(slots["doc:1"] == 0)   // alpha
        #expect(slots["doc:2"] == 1)   // Bravo
        #expect(slots["doc:3"] == 2)   // Charlie
    }

    @Test("Type groups by kind, pages first, then by name inside a kind")
    func typeGroupsByKind() {
        let mixed = [
            sourceNode("e1", label: "Andagoya", kind: .entity),
            sourceNode("doc:b", label: "page b"),
            sourceNode("n1", label: "a note", kind: .note),
            sourceNode("doc:a", label: "page a"),
        ]
        let slots = CanvasArrangement.slotIndices(.type, nodes: mixed, items: [])
        // Pages first — a diary folder is mostly pages, and burying them under
        // their own annotations would bury the board.
        #expect(slots["doc:a"] == 0)
        #expect(slots["doc:b"] == 1)
        #expect(slots["n1"] == 2)
        #expect(slots["e1"] == 3)
    }

    @Test("canvas items sort after every node kind, under every arrangement")
    func itemsFollowNodes() throws {
        let items = [try noteItem("i0", text: "aaa")]
        for arrangement in CanvasArrangement.allCases {
            let slots = CanvasArrangement.slotIndices(arrangement, nodes: pages, items: items)
            // "aaa" would sort first alphabetically; a note is a thing you put
            // ON the board, not a page to be filed among the pages.
            #expect(slots["i0"] == 3, "\(arrangement.label) interleaved items with pages")
        }
    }

    @Test("link items take no slot — they are edges, not cards")
    func linkItemsAreNotArranged() throws {
        let items = [try noteItem("i0"), try noteItem("edge", kind: "link")]
        let slots = CanvasArrangement.slotIndices(.name, nodes: [], items: items)
        #expect(slots["edge"] == nil)
        #expect(slots.count == 1)
    }

    @Test("ties keep their incoming order, so equal keys never shuffle")
    func sortingIsStable() {
        // Without stability a board of same-named cards re-flows on every
        // reconcile and the animation fires at random.
        let same = (0..<6).map { sourceNode("n\($0)", label: "Untitled") }
        for arrangement in CanvasArrangement.allCases {
            let slots = CanvasArrangement.slotIndices(arrangement, nodes: same, items: [])
            #expect(slots == Dictionary(uniqueKeysWithValues: (0..<6).map { ("n\($0)", $0) }),
                    "\(arrangement.label) is not stable across equal keys")
        }
    }

    @Test("an empty or single-card board arranges without incident")
    func degenerateBoards() {
        for arrangement in CanvasArrangement.allCases {
            #expect(CanvasArrangement.slotIndices(arrangement, nodes: [], items: []).isEmpty)
            #expect(CanvasArrangement.slotIndices(
                arrangement, nodes: [sourceNode("only", label: "x")], items: []) == ["only": 0])
        }
    }

    @Test("every arrangement produces a complete, collision-free slot map")
    func slotsAreABijection() {
        for arrangement in CanvasArrangement.allCases {
            let slots = CanvasArrangement.slotIndices(arrangement, nodes: pages, items: [])
            #expect(Set(slots.values) == Set(0..<pages.count),
                    "\(arrangement.label) skipped or doubled a slot")
        }
    }

    @Test("a stored raw value that means nothing falls back to the default board")
    func storedFallsBack() {
        #expect(CanvasArrangement.stored("name") == .name)
        #expect(CanvasArrangement.stored("") == .asFiled)
        #expect(CanvasArrangement.stored("byDate") == .asFiled)   // a future case, on an old build
    }
}

// MARK: - Pinning, and what a re-arrange is allowed to emit

@Suite("Re-arrange: pinned cards hold, and nothing rebuilds (R10)")
struct CanvasRearrangeDiffTests {

    private let pages = [
        sourceNode("doc:3", label: "Charlie"),
        sourceNode("doc:1", label: "alpha"),
        sourceNode("doc:2", label: "Bravo"),
    ]

    private func board(_ arrangement: CanvasArrangement, rows: [CanvasItemLayout] = []) -> CanvasSceneState {
        CanvasSceneState.resolve(
            nodes: pages, connections: [], links: [], layoutRows: rows, items: [],
            defaultPlacement: .grid(columns: 2), arrangement: arrangement
        )
    }

    @Test("a pinned card does not move when the arrangement changes")
    func pinnedCardsHold() {
        // §20.2: "cards that don't move are the ones you pinned" — your own
        // decisions become visible during the transition.
        let pinned = CanvasItemLayout(itemId: "doc:1", x: 42, y: -7, z: 1.5)
        let filed = board(.asFiled, rows: [pinned])
        let byName = board(.name, rows: [pinned])

        let before = Dictionary(uniqueKeysWithValues: filed.placeables.map { ($0.id, $0.position) })
        let after = Dictionary(uniqueKeysWithValues: byName.placeables.map { ($0.id, $0.position) })
        #expect(before["doc:1"] == SIMD3<Double>(42, -7, 1.5))
        #expect(after["doc:1"] == SIMD3<Double>(42, -7, 1.5))
        // Its neighbours DID move — otherwise this test would pass on a
        // re-arrange that does nothing at all.
        #expect(before["doc:2"] != after["doc:2"])
    }

    @Test("a re-arrange emits ONLY move ops — it can never be a rebuild")
    func rearrangeEmitsOnlyMoves() {
        let ops = CanvasSceneDiff.compute(from: board(.asFiled), to: board(.name))
        #expect(!ops.isEmpty)
        // Exhaustive on purpose, with no `default`: a NEW op added to
        // CanvasSceneOp must fail to compile here rather than quietly slip past
        // as "not forbidden". `.setTint` arrived this way — arrangement moves
        // cards, it does not recolour them, so it belongs on the forbidden side.
        for op in ops {
            switch op {
            case .move:
                continue
            case .insert, .remove, .resize, .updateContent,
                 .setEdges, .setSelection, .setEmphasis, .setTint:
                Issue.record("a re-arrange emitted \(op) — that is a rebuild, not a transition")
            }
        }
    }

    @Test("re-arranging to the same arrangement is silent")
    func idempotentArrangement() {
        #expect(CanvasSceneDiff.compute(from: board(.name), to: board(.name)).isEmpty)
    }

    @Test("cards that share a slot in both arrangements emit no move at all")
    func unmovedCardsAreNotTouched() {
        // The diff is per-card, so a card whose slot is unchanged must produce
        // nothing — that is what makes "watch which cards don't move" true of
        // the RENDER and not just of the model.
        let ops = CanvasSceneDiff.compute(from: board(.asFiled), to: board(.name))
        let moved = ops.compactMap { op -> String? in
            if case .move(let id, _) = op { return id }
            return nil
        }
        // doc:3 is slot 0 As Filed and slot 2 by name; doc:1 goes 1 → 0. Both
        // move. Nothing may appear twice.
        #expect(Set(moved).count == moved.count)
        #expect(!moved.contains { !["doc:1", "doc:2", "doc:3"].contains($0) })
    }
}

// MARK: - How long the transition takes

@Suite("CanvasMoveAnimation duration (R10, §20.2)")
struct CanvasMoveAnimationTests {

    @Test("one card is quick feedback; a board is a transition")
    func endsOfTheScale() {
        #expect(CanvasMoveAnimation.duration(movedCount: 1) == CanvasMoveAnimation.feedbackDuration)
        #expect(CanvasMoveAnimation.duration(movedCount: 2_228) == CanvasMoveAnimation.transitionDuration)
    }

    @Test("nothing ever animates longer than the cap")
    func hardCeiling() {
        // Every Frame Perfect cuts both ways: a board that floats for a second
        // reads as broken, not elegant.
        #expect(CanvasMoveAnimation.transitionDuration <= 0.6)
        for count in [0, 1, 5, 8, 50, 1_500, 4_241, Int.max] {
            let duration = CanvasMoveAnimation.duration(movedCount: count)
            #expect(duration >= CanvasMoveAnimation.feedbackDuration)
            #expect(duration <= CanvasMoveAnimation.transitionDuration)
        }
    }

    @Test("duration rises with the number of cards, never falls")
    func monotonic() {
        var previous = 0.0
        for count in 0...40 {
            let duration = CanvasMoveAnimation.duration(movedCount: count)
            #expect(duration >= previous || count == 1)
            previous = duration
        }
    }

    @Test("the duration comes off the diff, so both renderers get the same answer")
    func derivedFromTheOpBatch() {
        let moves = (0..<12).map { CanvasSceneOp.move(id: "n\($0)", position: SIMD3<Double>(0, 0, 0)) }
        #expect(CanvasMoveAnimation.duration(for: moves) == CanvasMoveAnimation.transitionDuration)
        // Non-move ops are not cards moving: a batch of one move alongside a
        // selection change is still feedback.
        #expect(CanvasMoveAnimation.duration(for: [moves[0], .setSelection(["n0"])])
                    == CanvasMoveAnimation.feedbackDuration)
        #expect(CanvasMoveAnimation.duration(for: []) == CanvasMoveAnimation.feedbackDuration)
    }
}

// MARK: - Wiring

/// One arrangement, two canvases, one animated move path.
struct CanvasArrangeWiringGuardTests {
    private func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private let canvases = [
        "Views/Library/ViewModes/Canvas/2D/CanvasSceneView.swift",
        "Views/Library/ViewModes/Canvas/3D/CanvasSpaceView.swift",
    ]
    /// FILE SETS — op application lives in +Ops.swift since the 2026-08-22
    /// split, and a guard reading only the main file would pass by reading
    /// nothing.
    private let renderers = [
        ["Views/Library/ViewModes/Canvas/2D/CanvasOrtho2DRenderer.swift",
         "Views/Library/ViewModes/Canvas/2D/CanvasOrtho2DRenderer+Ops.swift"],
        ["Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer.swift",
         "Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer+Ops.swift"],
    ]

    private func combined(_ paths: [String]) throws -> String {
        try paths.map { try appSource($0) }.joined(separator: "\n")
    }

    @Test("both canvases read the ONE persisted arrangement and show the picker")
    func bothCanvasesShareTheArrangement() throws {
        for path in canvases {
            let source = try appSource(path)
            #expect(source.contains("@AppStorage(CanvasArrangement.storageKey)"), "\(path) forked the choice")
            #expect(source.contains("arrangement: CanvasArrangement.stored(arrangementRaw)"))
            // Through the shared strip since Colour-by landed — so the guard
            // asserts the strip is present AND that the strip still carries the
            // arrangement picker, which is the property (both canvases can
            // re-arrange), not the spelling.
            #expect(source.contains("CanvasControlStrip()"), "\(path) has no control strip")
        }
    }

    @Test("the control strip is where the arrangement picker actually lives")
    func stripCarriesTheArrangePicker() throws {
        let strip = try appSource("Views/Library/ViewModes/Canvas/CanvasArrangePicker.swift")
        #expect(strip.contains("struct CanvasControlStrip"))
        #expect(strip.contains("CanvasArrangePicker()"))
        #expect(strip.contains("CanvasColourPicker()"))
    }

    @Test("both renderers ANIMATE a move, through the shared duration")
    func bothRenderersAnimate() throws {
        for paths in renderers {
            let source = try combined(paths)
            #expect(source.contains("CanvasMoveAnimation.duration(for: ops)"), "\(paths) picked its own timing")
            #expect(source.contains("duration: moveDuration"), "\(paths) teleports cards")
            // The 3D teleport this replaced: a bare position assignment.
            #expect(!source.contains("?.position = Canvas3DProjection.scenePosition(position)"))
        }
    }

    @Test("the arrangement seam is the only ordering path")
    func orderingIsNotForkedIntoAView() throws {
        // Date and Entity arrive later (build-order step 8); they must come
        // through CanvasArrangement, not a sort inside a renderer or a view.
        for path in canvases {
            #expect(!(try appSource(path)).contains(".sorted {"), "\(path) sorts a board outside CanvasArrangement")
        }
        for paths in renderers {
            #expect(!(try combined(paths)).contains(".sorted {"), "\(paths) sorts a board outside CanvasArrangement")
        }
    }
}
