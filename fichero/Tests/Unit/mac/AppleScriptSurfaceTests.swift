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

    /// The Debug dictionary (#5193): `FicheroDebug.sdef` includes the whole user dictionary by XInclude
    /// -- so the two never drift -- and adds the Debug-only test suite, whose `describe window` binds a
    /// class this (Debug) build has. Info.plist names it through a build setting, so Release keeps
    /// Fichero.sdef. Breaks if the include stops resolving (a Debug app with no user verbs) or the
    /// verb names a class that is not there.
    func testTheDebugDictionaryIncludesTheUserOneAndAddsDescribeWindow() throws {
        let url = try AppSource.root().appendingPathComponent("FicheroDebug.sdef")
        // Resolved by xmllint, as the system resolves it: the include uses
        // `xpointer(/dictionary/suite)` (Apple's own sdef pattern), which Foundation's
        // XMLDocument .documentXInclude does not implement -- it silently kept one suite.
        let lint = Process()
        lint.executableURL = URL(fileURLWithPath: "/usr/bin/xmllint")
        lint.arguments = ["--xinclude", "--nowarning", url.path]
        let out = Pipe()
        lint.standardOutput = out
        try lint.run()
        let xml = out.fileHandleForReading.readDataToEndOfFile()
        lint.waitUntilExit()
        XCTAssertEqual(lint.terminationStatus, 0, "xmllint resolved the include")
        let resolved = try XMLDocument(data: xml)
        let suites = try resolved.nodes(forXPath: "/dictionary/suite/@name").compactMap(\.stringValue)
        XCTAssertEqual(suites, ["Standard Suite", "Fichero Suite", "Fichero Test Suite"])
        let binding = try resolved.nodes(forXPath: "//command[@name='describe window']/cocoa/@class").first?.stringValue
        XCTAssertEqual(binding, "FicheroDescribeWindowCommand")
        XCTAssertNotNil(NSClassFromString("FicheroDescribeWindowCommand"), "the Debug build has the class the verb binds")
        let plist = try String(contentsOf: AppSource.root().appendingPathComponent("Info.plist"), encoding: .utf8)
        XCTAssertTrue(plist.range(of: "<string>$(FICHERO_SCRIPTING_DEFINITION)</string>") != nil,
                      "the dictionary is chosen per configuration, never one file for both")
    }

    /// #5194 (`ui-testing.drive-below-a-document`): the Debug suite reaches below a document --
    /// `select page`, `select segment`, `show pane` -- each bound to a class this Debug build has, each
    /// answering whether it was accepted. The rules they use: a pane by the name a script says (and a
    /// refusal naming the panes that would have worked), and the sidebar reveal's page + segment -- the
    /// seam a citable reference already lands through. Breaks if a verb binds nothing, a pane name is
    /// misread, or a segment lands without its page.
    func testTheDebugSuiteReachesBelowADocument() throws {
        let url = try AppSource.root().appendingPathComponent("FicheroDebug.sdef")
        // Resolved by xmllint, as the system resolves it: the include uses
        // `xpointer(/dictionary/suite)` (Apple's own sdef pattern), which Foundation's
        // XMLDocument .documentXInclude does not implement -- it silently kept one suite.
        let lint = Process()
        lint.executableURL = URL(fileURLWithPath: "/usr/bin/xmllint")
        lint.arguments = ["--xinclude", "--nowarning", url.path]
        let out = Pipe()
        lint.standardOutput = out
        try lint.run()
        let xml = out.fileHandleForReading.readDataToEndOfFile()
        lint.waitUntilExit()
        XCTAssertEqual(lint.terminationStatus, 0, "xmllint resolved the include")
        let resolved = try XMLDocument(data: xml)
        let bindings: [String: String] = [
            "select page": "FicheroSelectPageCommand",
            "select segment": "FicheroSelectSegmentCommand",
            "show pane": "FicheroShowPaneCommand",
        ]
        for (verb, cls) in bindings {
            let bound = try resolved.nodes(forXPath: "//suite[@name='Fichero Test Suite']/command[@name='\(verb)']/cocoa/@class")
            XCTAssertEqual(bound.first?.stringValue, cls, verb)
            XCTAssertNotNil(NSClassFromString(cls), "\(cls) is in the Debug build")
        }
        XCTAssertEqual(DebugScriptVerbs.paneKind(named: " Segments "), .segments)
        XCTAssertEqual(DebugScriptVerbs.paneKind(named: "preview"), .preview)
        XCTAssertNil(DebugScriptVerbs.paneKind(named: "kg"), "a panel is not a pane")
        XCTAssertEqual(Set(DebugScriptVerbs.paneNames), Set(PaneKind.allCases.map(\.rawValue)))
        XCTAssertEqual(DebugScriptVerbs.revealUserInfo(documentId: "doc-1"), ["documentId": "doc-1"])
        XCTAssertEqual(DebugScriptVerbs.revealUserInfo(documentId: "doc-1", segmentId: "seg-3"),
                       ["documentId": "doc-1", "segmentId": "seg-3"])
        XCTAssertEqual(PaneList([.leaf(.preview)]).settingVisible(.segments, true).leafIDs(of: .segments).count, 1,
                       "show pane adds the pane when it is absent")
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
