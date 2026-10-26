@testable import Fichero
import OSLog
import XCTest

/// `m2p.ios.connection-menu` (#6124): the log a person shares holds the app's own lines. Not run on the Pro; the builder runs it.
final class LogExportTests: XCTestCase {
    func testTheExportedFileHoldsALineTheAppJustLogged() throws {
        let marker = "log-export-test-\(UUID().uuidString)"
        Logger(subsystem: LogExport.subsystem, category: "LogExportTests").notice("\(marker, privacy: .public)")
        let url = try LogExport.write(since: 60)
        defer { try? FileManager.default.removeItem(at: url) }
        XCTAssertTrue(try String(contentsOf: url, encoding: .utf8).contains(marker))
    }
}
