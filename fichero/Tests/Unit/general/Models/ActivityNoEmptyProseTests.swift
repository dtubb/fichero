import Foundation
import XCTest
@testable import Fichero

/// `activity.window.no-empty-prose` (#5960): an empty window, an empty group and an empty details pane say nothing.
/// A source pin, as the view files cannot be drawn in a unit test: the sentences are gone from every Activity view.
final class ActivityNoEmptyProseTests: XCTestCase {
    private static let sentences = ["No Runs Yet", "Nothing running.", "No Activity Selected", "Reading the Row"]

    func testNoActivityViewSaysAnEmptyStateInWords() throws {
        let folder = try AppSource.root().appendingPathComponent("Views/Activity")
        let files = try XCTUnwrap(FileManager.default.enumerator(at: folder, includingPropertiesForKeys: nil))
        var scanned = 0
        for case let url as URL in files where url.pathExtension == "swift" {
            scanned += 1
            let source = try String(contentsOf: url, encoding: .utf8)
            for sentence in Self.sentences {
                XCTAssertFalse(source.contains("\"\(sentence)\""), "\(url.lastPathComponent) says \"\(sentence)\"")
            }
        }
        XCTAssertGreaterThan(scanned, 20, "the walk found the Activity views")
    }
}
