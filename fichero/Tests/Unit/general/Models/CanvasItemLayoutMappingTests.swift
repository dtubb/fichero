import FicheroAPIClient
import Foundation
import XCTest

@testable import Fichero

/// Schema ↔ display-model mapping for `CanvasItemLayout` (#2293/#3082). The
/// generated `CanvasLayout` makes every numeric optional; `init(schema:)` must
/// default the position/rotation/z-index to 0 (never propagate nil into layout
/// math) while passing size (w/h/d) and style through as genuine optionals.
/// `asSaveItem` projects back for the PUT body. Pure value mapping — no store.
final class CanvasItemLayoutMappingTests: XCTestCase {

    func testInitFromSchemaDefaultsNilNumericsToZero() {
        // A row the server returned with all optionals absent.
        let schema = Components.Schemas.CanvasLayout(folderId: "f", itemId: "i")
        let layout = CanvasItemLayout(schema: schema)

        XCTAssertEqual(layout.itemId, "i")
        XCTAssertEqual(layout.x, 0)
        XCTAssertEqual(layout.y, 0)
        XCTAssertEqual(layout.z, 0)
        XCTAssertEqual(layout.angle, 0)
        XCTAssertEqual(layout.zIndex, 0)
        // Size + style are genuinely optional — nil stays nil, not defaulted.
        XCTAssertNil(layout.w)
        XCTAssertNil(layout.h)
        XCTAssertNil(layout.d)
        XCTAssertNil(layout.style)
    }

    func testInitFromSchemaPassesThroughPopulatedValues() {
        let schema = Components.Schemas.CanvasLayout(
            folderId: "f", itemId: "i",
            x: 1, y: 2, z: 3, w: 4, h: 5, d: 6, angle: 7, zIndex: 8, style: "card"
        )
        let layout = CanvasItemLayout(schema: schema)

        XCTAssertEqual(layout.x, 1)
        XCTAssertEqual(layout.y, 2)
        XCTAssertEqual(layout.z, 3)
        XCTAssertEqual(layout.w, 4)
        XCTAssertEqual(layout.h, 5)
        XCTAssertEqual(layout.d, 6)
        XCTAssertEqual(layout.angle, 7)
        XCTAssertEqual(layout.zIndex, 8)
        XCTAssertEqual(layout.style, "card")
    }

    func testAsSaveItemProjectsEveryField() {
        let layout = CanvasItemLayout(
            itemId: "i", x: 1, y: 2, z: 3, w: 4, h: 5, d: 6,
            angle: 7, zIndex: 8, style: "card"
        )
        let save = layout.asSaveItem

        XCTAssertEqual(save.itemId, "i")
        XCTAssertEqual(save.x, 1)
        XCTAssertEqual(save.y, 2)
        XCTAssertEqual(save.z, 3)
        XCTAssertEqual(save.w, 4)
        XCTAssertEqual(save.h, 5)
        XCTAssertEqual(save.d, 6)
        XCTAssertEqual(save.angle, 7)
        XCTAssertEqual(save.zIndex, 8)
        XCTAssertEqual(save.style, "card")
    }

    func testSchemaRoundTripPreservesValues() {
        // schema → display → save body must not lose or alter any field.
        let schema = Components.Schemas.CanvasLayout(
            folderId: "f", itemId: "i",
            x: 1.5, y: -2, z: 0, w: nil, h: nil, d: nil,
            angle: 90, zIndex: 3, style: nil
        )
        let save = CanvasItemLayout(schema: schema).asSaveItem

        XCTAssertEqual(save.itemId, "i")
        XCTAssertEqual(save.x, 1.5)
        XCTAssertEqual(save.y, -2)
        XCTAssertEqual(save.angle, 90)
        XCTAssertEqual(save.zIndex, 3)
        XCTAssertNil(save.w)
        XCTAssertNil(save.style)
    }
}
