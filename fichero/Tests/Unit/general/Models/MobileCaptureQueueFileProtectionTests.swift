import XCTest

/// spec: library-sharing §`sharing.ios-device-token-hygiene` (#3290). Every outbox write goes through
/// `writeOptions`, which adds file protection on iOS; a bare `.atomic` write would skip it. A source
/// scan, since the iOS branch does not compile into the Mac test host.
final class MobileCaptureQueueFileProtectionTests: XCTestCase {

    func testOutboxWritesUseTheProtectedOptions() throws {
        let root = try AppSource.root().appendingPathComponent("Models")
        for file in ["MobileCaptureQueue+Enqueueing.swift", "MobileCaptureQueue+Persistence.swift"] {
            let source = try String(contentsOf: root.appendingPathComponent(file), encoding: .utf8)
            XCTAssertTrue(source.contains("options: Self.writeOptions"), "\(file) must write with Self.writeOptions")
            XCTAssertFalse(source.contains("options: .atomic"), "\(file) has an unprotected outbox write")
        }
        let queue = try String(contentsOf: root.appendingPathComponent("MobileCaptureQueue.swift"), encoding: .utf8)
        XCTAssertTrue(queue.contains("[.atomic, .completeFileProtectionUntilFirstUserAuthentication]"))
    }
}
