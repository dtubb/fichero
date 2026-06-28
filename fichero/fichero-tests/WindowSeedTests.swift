@testable import Fichero
import Foundation
import XCTest

/// Tests for WindowSeed — the Codable payload behind Duplicate Window (#2262).
/// It rides `openWindow(value:)` and SwiftUI scene restoration, so the lock is
/// lossless Codable round-trip (with and without the optional fields) and value
/// equality/hashing.
final class WindowSeedTests: XCTestCase {

    func testCodableRoundTripWithAllFields() throws {
        let seed = WindowSeed(
            libraryId: "lib-1",
            libraryPath: "/Users/x/Lib.fichero",
            selectedItemId: "item-1",
            viewModeType: "canvas",
            viewModeItemId: "node-1"
        )
        let restored = try JSONDecoder().decode(
            WindowSeed.self,
            from: JSONEncoder().encode(seed)
        )
        XCTAssertEqual(seed, restored)
    }

    func testCodableRoundTripWithOptionalsNil() throws {
        let seed = WindowSeed(
            libraryId: "lib-1",
            libraryPath: nil,
            selectedItemId: nil,
            viewModeType: nil,
            viewModeItemId: nil
        )
        let restored = try JSONDecoder().decode(
            WindowSeed.self,
            from: JSONEncoder().encode(seed)
        )
        XCTAssertEqual(seed, restored)
        XCTAssertNil(restored.libraryPath)
        XCTAssertNil(restored.viewModeItemId)
    }

    func testDecodesFromJSON() throws {
        let json = Data("""
        {
            "libraryId": "L",
            "libraryPath": "/p",
            "selectedItemId": "s",
            "viewModeType": "vm",
            "viewModeItemId": "vmi"
        }
        """.utf8)
        let seed = try JSONDecoder().decode(WindowSeed.self, from: json)
        XCTAssertEqual(seed.libraryId, "L")
        XCTAssertEqual(seed.libraryPath, "/p")
        XCTAssertEqual(seed.viewModeType, "vm")
        XCTAssertEqual(seed.viewModeItemId, "vmi")
    }

    func testHashableValueEquality() {
        let base = WindowSeed(
            libraryId: "l",
            libraryPath: nil,
            selectedItemId: nil,
            viewModeType: nil,
            viewModeItemId: nil
        )
        let same = base
        let different = WindowSeed(
            libraryId: "other",
            libraryPath: nil,
            selectedItemId: nil,
            viewModeType: nil,
            viewModeItemId: nil
        )
        XCTAssertEqual(base, same)
        XCTAssertNotEqual(base, different)
        XCTAssertEqual(Set([base, same, different]).count, 2)
    }
}
