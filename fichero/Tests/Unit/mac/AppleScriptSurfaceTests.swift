#if os(macOS)
@testable import Fichero
import XCTest

/// The AppleScript dictionary is test/agent infrastructure (#4535): the
/// scripted UX smoke (scripts/ux_smoke.py) drives these verbs against a live
/// build. What a unit test CAN pin without launching the app is the contract
/// the smoke depends on: the sdef names the verbs, every verb's Cocoa class
/// exists, and the capture engine fails the way the smoke's named-view step
/// relies on (a miss that lists what exists, never a silent nil).
final class AppleScriptSurfaceTests: XCTestCase {

    private static func sdef() throws -> String {
        let url = try AppSource.root().appendingPathComponent("Fichero.sdef")
        let text = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(text.isEmpty, "Fichero.sdef is empty — nothing below measures anything")
        return text
    }

    /// The verbs the 2026-08-04 test-architecture decisions require, by name.
    func testTheAgentVerbsAreDeclared() throws {
        let sdef = try Self.sdef()
        for verb in ["open library", "select document", "run workflow",
                     "stop run", "screenshot", "get workflow status"] {
            XCTAssertTrue(
                sdef.contains("<command name=\"\(verb)\""),
                "Fichero.sdef must declare the '\(verb)' verb (#4535)"
            )
        }
        // One screenshot verb, window-vs-view as a PARAMETER (not two verbs) —
        // the #4536 shape.
        XCTAssertTrue(sdef.contains("name=\"of view\" code=\"view\""),
                      "screenshot must take its target as the 'of view' parameter")
        // The declared-selection parameter on run workflow (#4414).
        XCTAssertTrue(sdef.contains("cocoa key=\"selectedDocIds\""),
                      "run workflow must accept the 'on documents' declared selection")
    }

    /// Every `<cocoa class="X"/>` the sdef binds must exist as an
    /// `@objc(X)` class, or the verb dispatches to nothing at runtime with no
    /// compile-time complaint — the classic silent sdef rot.
    func testEveryCocoaCommandClassExistsInSource() throws {
        let sdef = try Self.sdef()
        let services = try AppSource.root().appendingPathComponent("Services")
        let sources = try FileManager.default
            .contentsOfDirectory(at: services, includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "swift" }
            .map { try String(contentsOf: $0, encoding: .utf8) }
            .joined(separator: "\n")

        let pattern = /<cocoa class="(Fichero[A-Za-z]+Command)"/
        let classes = sdef.matches(of: pattern).map { String($0.1) }
        XCTAssertGreaterThanOrEqual(
            classes.count, 12,
            "the sdef parse found implausibly few command classes — the scan is blind"
        )
        for name in classes {
            XCTAssertTrue(
                sources.contains("@objc(\(name))"),
                "\(name) is bound in Fichero.sdef but no @objc(\(name)) class exists"
            )
        }
    }

    /// The smoke's named-view step depends on the miss being LOUD and
    /// self-describing — a capture that cannot find its view must say what it
    /// could see, or every miss becomes an undebuggable blank.
    @MainActor
    func testViewNotFoundNamesTheIdentifiersPresent() {
        let error = FicheroUICapture.CaptureError.viewNotFound(
            name: "sidebar", available: ["toolbar.status", "library.list"]
        )
        let message = String(describing: error)
        XCTAssertTrue(message.contains("sidebar"))
        XCTAssertTrue(message.contains("Identifiers present"))
        XCTAssertTrue(message.contains("library.list"))
        XCTAssertTrue(message.contains("toolbar.status"))
    }

    /// Whole-window capture with no window must throw `.noWindow`, never
    /// return a path to nothing. (Unit hosts DO have windows sometimes; only
    /// the error-shape is assertable here — the live capture is the smoke's.)
    @MainActor
    func testNoWindowErrorIsSelfDescribing() {
        let message = String(describing: FicheroUICapture.CaptureError.noWindow)
        XCTAssertTrue(message.contains("window"))
    }
}
#endif
