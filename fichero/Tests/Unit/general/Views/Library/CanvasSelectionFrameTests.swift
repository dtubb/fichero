//
//  CanvasSelectionFrameTests.swift
//  FicheroTests
//
//  #4409 — what a selection LOOKS like on the canvas: a frame per selected
//  item, one set frame around a multi-selection, and resize handles ONLY where
//  resizing actually happens. Pure geometry and policy; no renderer, no app.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import simd
import Testing

// MARK: - Helpers

private func item(
    _ id: String,
    x: Float = 0,
    y: Float = 0,
    width: Float = 1.0,
    height: Float = 0.75,
    resizable: Bool = true
) -> CanvasSelectionFrame.Item {
    CanvasSelectionFrame.Item(
        id: id, centerX: x, centerY: y, width: width, height: height, isResizable: resizable
    )
}

private func canvasItem(_ id: String, kind: String) throws -> CanvasItemDisplay {
    let payload: [String: Any] = ["id": id, "folderId": "scope", "kind": kind]
    let data = try JSONSerialization.data(withJSONObject: payload)
    return try JSONDecoder().decode(CanvasItemDisplay.self, from: data)
}

private func isClose(_ lhs: Float, _ rhs: Float, tolerance: Float = 0.0005) -> Bool {
    abs(lhs - rhs) <= tolerance
}

// MARK: - The frame

@Suite("CanvasSelectionFrame.plan (#4409)")
struct CanvasSelectionFramePlanTests {

    @Test("a selected item gets a frame, inset outside its own edges")
    func singleSelectionHasAFrame() throws {
        let plan = CanvasSelectionFrame.plan(for: [item("a")])
        #expect(plan.itemBoxes.count == 1)
        let box = try #require(plan.itemBoxes.first)
        // Outside the card, not drawn on it — a frame the card's own edge
        // would hide is not an affordance.
        #expect(box.width > 1.0)
        #expect(box.height > 0.75)
        #expect(isClose(box.width, 1.0 + CanvasSelectionFrame.itemInset))
        #expect(isClose(box.height, 0.75 + CanvasSelectionFrame.itemInset))
    }

    @Test("EVERY item of a multi-selection gets its own frame")
    func everyMemberIsFramed() {
        let plan = CanvasSelectionFrame.plan(for: [item("a", x: -2), item("b", x: 0), item("c", x: 2)])
        #expect(plan.itemBoxes.count == 3)
    }

    @Test("a multi-selection ALSO gets one set frame containing all of them")
    func multiSelectionReadsAsASet() throws {
        let plan = CanvasSelectionFrame.plan(for: [item("a", x: -2), item("b", x: 2)])
        let setBox = try #require(plan.setBox, "a multi-selection must read as a set, not as N highlights")
        // Contains both item frames, with the set margin outside them.
        for box in plan.itemBoxes {
            #expect(setBox.minX <= box.minX)
            #expect(setBox.maxX >= box.maxX)
            #expect(setBox.minY <= box.minY)
            #expect(setBox.maxY >= box.maxY)
        }
        #expect(isClose(setBox.centerX, 0))
    }

    @Test("a single selection has NO set frame — the item frame already is the set")
    func singleSelectionHasNoSetFrame() {
        #expect(CanvasSelectionFrame.plan(for: [item("a")]).setBox == nil)
    }

    @Test("an empty selection draws nothing at all")
    func emptySelectionDrawsNothing() {
        let plan = CanvasSelectionFrame.plan(for: [])
        #expect(plan.itemBoxes.isEmpty)
        #expect(plan.setBox == nil)
        #expect(plan.handles.isEmpty)
    }

    @Test("the plan is ORDERED by id, so a Set-derived selection renders the same every run")
    func planIsDeterministic() {
        let forward = CanvasSelectionFrame.plan(for: [item("a", x: -1), item("b", x: 1)])
        let reversed = CanvasSelectionFrame.plan(for: [item("b", x: 1), item("a", x: -1)])
        #expect(forward == reversed)
    }
}

// MARK: - Handles

@Suite("CanvasSelectionFrame handles (#4409)")
struct CanvasSelectionFrameHandleTests {

    @Test("a single resizable selection gets four corner handles, on the frame's corners")
    func fourCorners() throws {
        let plan = CanvasSelectionFrame.plan(for: [item("a")])
        #expect(plan.handles.count == 4)
        #expect(Set(plan.handles.map(\.corner)) == Set(CanvasSelectionFrame.Corner.allCases))
        let box = try #require(plan.itemBoxes.first)
        for handle in plan.handles {
            #expect(isClose(abs(handle.positionX - box.centerX), box.width / 2))
            #expect(isClose(abs(handle.positionY - box.centerY), box.height / 2))
            #expect(handle.itemId == "a")
        }
    }

    @Test("a NON-resizable item is framed but gets no handles")
    func noHandlesWhereResizeIsUnsupported() {
        let plan = CanvasSelectionFrame.plan(for: [item("link", resizable: false)])
        #expect(plan.itemBoxes.count == 1, "it is still selected, so it is still framed")
        #expect(plan.handles.isEmpty, "a handle that cannot resize is worse than no handle")
    }

    @Test("a multi-selection gets no handles: resizing a SET is a different operation")
    func noHandlesOnASet() {
        let plan = CanvasSelectionFrame.plan(for: [item("a", x: -2), item("b", x: 2)])
        #expect(plan.setBox != nil)
        #expect(plan.handles.isEmpty)
    }

    @Test("a link item is not resizable; notes, quotes, text and nodes are")
    func resizabilityPolicy() throws {
        // A link is an EDGE — its endpoints decide where it is drawn, so a
        // handle on it could not do anything.
        #expect(CanvasSelectionFrame.isResizable(.item(try canvasItem("l", kind: "link"))) == false)
        for kind in ["note", "quote", "text", "work_note"] {
            #expect(CanvasSelectionFrame.isResizable(.item(try canvasItem("i", kind: kind))))
        }
        let node = SpatialNode(
            id: "n", roomId: "r", nodeType: .source, label: "N",
            positionX: 0, positionY: 0, positionZ: 0
        )
        #expect(CanvasSelectionFrame.isResizable(.node(node)))
    }
}

// MARK: - Entity naming

@Suite("CanvasSelectionFrame entity names (#4409)")
struct CanvasSelectionFrameNamingTests {

    @Test("a handle name round-trips, including ids that contain colons")
    func handleNameRoundTrip() throws {
        // Placeable ids are namespaced (`doc:…`), so a naive split on ":"
        // would truncate every id in the app.
        for id in ["doc:abc-123", "entity:x:y", "plain"] {
            for corner in CanvasSelectionFrame.Corner.allCases {
                let name = CanvasSelectionFrame.handleName(corner: corner, itemId: id)
                let parsed = try #require(CanvasSelectionFrame.handle(fromEntityName: name))
                #expect(parsed.corner == corner)
                #expect(parsed.itemId == id)
            }
        }
    }

    @Test("every decoration name is recognisable, so no host mistakes one for a placeable")
    func decorationIsRecognisable() {
        #expect(CanvasSelectionFrame.isDecoration(
            CanvasSelectionFrame.handleName(corner: .topLeading, itemId: "doc:1")
        ))
        #expect(CanvasSelectionFrame.isDecoration(CanvasSelectionFrame.decorationNamePrefix + "frame"))
        #expect(CanvasSelectionFrame.isDecoration("doc:1") == false)
        #expect(CanvasSelectionFrame.isDecoration("") == false)
    }

    @Test("a card name is never parsed as a handle")
    func cardsAreNotHandles() {
        #expect(CanvasSelectionFrame.handle(fromEntityName: "doc:1") == nil)
        #expect(CanvasSelectionFrame.handle(fromEntityName: "") == nil)
        // Malformed decoration names decode to nil rather than to a wrong id.
        #expect(CanvasSelectionFrame.handle(fromEntityName: CanvasSelectionFrame.handleNamePrefix) == nil)
        #expect(CanvasSelectionFrame.handle(fromEntityName: CanvasSelectionFrame.handleNamePrefix + "nope:x") == nil)
        #expect(CanvasSelectionFrame.handle(fromEntityName: CanvasSelectionFrame.handleNamePrefix + "topLeading:") == nil)
    }
}

// MARK: - Resize math

@Suite("CanvasSelectionFrame.resizedSize (#4409)")
struct CanvasSelectionResizeTests {

    private let origin = CGSize(width: 1.0, height: 0.75)

    @Test("dragging a corner OUTWARD grows the card, from every corner")
    func everyCornerGrowsOutward() {
        // Plane coordinates are y-UP, so "outward" for each corner is its own
        // sign pair. A corner that shrank when dragged outward would be the
        // handle feeling backwards, which is the whole point of the affordance.
        let cases: [(CanvasSelectionFrame.Corner, SIMD2<Float>)] = [
            (.topTrailing, SIMD2(0.5, 0.5)),
            (.topLeading, SIMD2(-0.5, 0.5)),
            (.bottomTrailing, SIMD2(0.5, -0.5)),
            (.bottomLeading, SIMD2(-0.5, -0.5))
        ]
        for (corner, delta) in cases {
            let result = CanvasSelectionFrame.resizedSize(
                from: origin, corner: corner, sceneDelta: delta, proportional: false
            )
            #expect(isClose(Float(result.width), 1.5), "\(corner) width")
            #expect(isClose(Float(result.height), 1.25), "\(corner) height")
        }
    }

    @Test("dragging a corner INWARD shrinks the card")
    func draggingInwardShrinks() {
        let result = CanvasSelectionFrame.resizedSize(
            from: origin, corner: .topTrailing, sceneDelta: SIMD2(-0.4, -0.25), proportional: false
        )
        #expect(isClose(Float(result.width), 0.6))
        #expect(isClose(Float(result.height), 0.5))
    }

    @Test("proportional is the DEFAULT and preserves the aspect ratio exactly")
    func proportionalPreservesAspect() {
        let result = CanvasSelectionFrame.resizedSize(
            from: origin, corner: .topTrailing, sceneDelta: SIMD2(0.5, 0), proportional: true
        )
        #expect(isClose(Float(result.width), 1.5))
        #expect(isClose(Float(result.height), 1.125))
        #expect(isClose(Float(result.width / result.height), Float(origin.width / origin.height)))
    }

    @Test("under proportional the DOMINANT axis drives, so a vertical drag is not dead")
    func proportionalFollowsTheDominantAxis() {
        // Purely vertical: width contributed nothing, so height must still
        // drive the scale. A width-only implementation would return `origin`.
        let result = CanvasSelectionFrame.resizedSize(
            from: origin, corner: .topTrailing, sceneDelta: SIMD2(0, 0.375), proportional: true
        )
        #expect(isClose(Float(result.width), 1.5))
        #expect(isClose(Float(result.height), 1.125))
    }

    @Test("freeing the aspect ratio lets the two axes diverge")
    func freeAspectDiverges() {
        let free = CanvasSelectionFrame.resizedSize(
            from: origin, corner: .topTrailing, sceneDelta: SIMD2(0.5, 0), proportional: false
        )
        #expect(isClose(Float(free.width), 1.5))
        #expect(isClose(Float(free.height), 0.75), "height untouched when the aspect is free")
    }

    @Test("a card can never be resized to nothing, or to something unbounded")
    func sizeIsClamped() {
        let collapsed = CanvasSelectionFrame.resizedSize(
            from: origin, corner: .topTrailing, sceneDelta: SIMD2(-99, -99), proportional: false
        )
        #expect(isClose(Float(collapsed.width), CanvasSelectionFrame.minimumSide))
        #expect(isClose(Float(collapsed.height), CanvasSelectionFrame.minimumSide))

        let enormous = CanvasSelectionFrame.resizedSize(
            from: origin, corner: .topTrailing, sceneDelta: SIMD2(999, 999), proportional: false
        )
        #expect(isClose(Float(enormous.width), CanvasSelectionFrame.maximumSide))
        #expect(isClose(Float(enormous.height), CanvasSelectionFrame.maximumSide))
    }

    @Test("clamping under proportional keeps the aspect rather than squaring the card off")
    func proportionalClampKeepsAspect() {
        let enormous = CanvasSelectionFrame.resizedSize(
            from: origin, corner: .topTrailing, sceneDelta: SIMD2(999, 999), proportional: true
        )
        #expect(Float(enormous.width) <= CanvasSelectionFrame.maximumSide + 0.001)
        #expect(Float(enormous.height) <= CanvasSelectionFrame.maximumSide + 0.001)
        #expect(isClose(Float(enormous.width / enormous.height), Float(origin.width / origin.height)))

        let collapsed = CanvasSelectionFrame.resizedSize(
            from: origin, corner: .topTrailing, sceneDelta: SIMD2(-999, -999), proportional: true
        )
        #expect(Float(collapsed.width) >= CanvasSelectionFrame.minimumSide - 0.001)
        #expect(Float(collapsed.height) >= CanvasSelectionFrame.minimumSide - 0.001)
        #expect(isClose(Float(collapsed.width / collapsed.height), Float(origin.width / origin.height)))
    }

    @Test("a degenerate origin size is returned unchanged instead of dividing by zero")
    func degenerateOriginIsSafe() {
        let zero = CGSize(width: 0, height: 0)
        #expect(CanvasSelectionFrame.resizedSize(
            from: zero, corner: .topTrailing, sceneDelta: SIMD2(1, 1), proportional: true
        ) == zero)
    }
}
