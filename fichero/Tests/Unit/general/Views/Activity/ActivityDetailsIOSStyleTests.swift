@testable import Fichero
import Foundation
import XCTest

/// `.buttonStyle(.link)` does not exist on iOS, so in the Activity details it may only follow `#if os(macOS)` (#6390).
final class ActivityDetailsIOSStyleTests: XCTestCase {
    func testLinkStyleIsOnlyUsedUnderTheMacCondition() throws {
        let views = try AppSource.root().appendingPathComponent("Views/Activity/Detail")
        for name in ["ActivityDetailsSections.swift", "ActivityDetailsStageCards.swift"] {
            let text = try String(contentsOf: views.appendingPathComponent(name), encoding: .utf8)
            let lines = text.components(separatedBy: "\n").map { $0.trimmingCharacters(in: .whitespaces) }
            let uses = lines.indices.filter { lines[$0] == ".buttonStyle(.link)" }
            XCTAssertFalse(uses.isEmpty, "\(name) no longer uses .link; update this test")
            for index in uses {
                XCTAssertEqual(lines[index - 1], "#if os(macOS)", "\(name) line \(index + 1): .link needs #if os(macOS)")
            }
        }
    }
}
