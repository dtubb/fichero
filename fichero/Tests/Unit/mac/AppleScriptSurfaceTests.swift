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
        for verb in ["open project", "open node", "select nodes", "reveal segments", "show pane",
                     "show inspector tab", "run workflow", "stop run", "screenshot", "get workflow status"] {
            XCTAssertTrue(
                sdef.contains("<command name=\"\(verb)\""),
                "Fichero.sdef must declare the '\(verb)' verb (#4535)"
            )
        }
        // One screenshot verb, window-vs-pane as a PARAMETER (not two verbs) —
        // the #4536 shape, by pane name since #5453.
        XCTAssertTrue(sdef.contains("name=\"of pane\" code=\"pane\""),
                      "screenshot must take its target as the 'of pane' parameter")
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

    /// The Debug dictionary (#5193, #5258): the whole user dictionary, then the Debug-only test suite.
    /// It is a COPY of Fichero.sdef's suites, not an XInclude -- the system resolved the include against
    /// the reader's working directory, so a Debug app had no verbs at all (#5258). Breaks if the copy
    /// drifts from Fichero.sdef, if an include comes back, or a test verb binds a class not in this build.
    func testTheDebugDictionaryIsTheUserOnePlusTheTestSuite() throws {
        let user = try XMLDocument(contentsOf: AppSource.root().appendingPathComponent("Fichero.sdef"))
        let debug = try XMLDocument(contentsOf: AppSource.root().appendingPathComponent("FicheroDebug.sdef"))
        let userSuites = try user.nodes(forXPath: "/dictionary/suite").map { $0.xmlString }
        let debugSuites = try debug.nodes(forXPath: "/dictionary/suite").map { $0.xmlString }
        XCTAssertEqual(userSuites.count, 2, "the user dictionary's two suites were found")
        XCTAssertEqual(Array(debugSuites.prefix(userSuites.count)), userSuites,
                       "FicheroDebug.sdef's user suites are Fichero.sdef's, word for word")
        XCTAssertEqual(debugSuites.count, userSuites.count + 1, "plus the test suite, and nothing else")
        XCTAssertTrue(try debug.nodes(forXPath: "//*[local-name()='include']").isEmpty, "no XInclude (#5258)")
        let testVerbs = ["describe window": "FicheroDescribeWindowCommand", "select segment": "FicheroSelectSegmentCommand"]
        for (verb, cls) in testVerbs {
            let bound = try debug.nodes(forXPath: "//suite[@name='Fichero Test Suite']/command[@name='\(verb)']/cocoa/@class")
            XCTAssertEqual(bound.first?.stringValue, cls, verb)
            XCTAssertNotNil(NSClassFromString(cls), "\(cls) is in the Debug build")
        }
        let plist = try String(contentsOf: AppSource.root().appendingPathComponent("Info.plist"), encoding: .utf8)
        XCTAssertTrue(plist.range(of: "<string>$(FICHERO_SCRIPTING_DEFINITION)</string>") != nil,
                      "the dictionary is chosen per configuration, never one file for both")
    }

    private static func code(_ text: String) -> FourCharCode {
        text.utf8.reduce(0) { $0 << 8 | FourCharCode($1) }
    }

    /// `automation.applescript.debug-dictionary-loads` (#5258) and `openapi.ui.verbs-are-the-click`
    /// (#5453): the dictionary THIS running (Debug) app loaded knows every UI verb and the test suite,
    /// each bound to a class that exists. Before the fix the Debug app loaded no dictionary at all, so
    /// every osascript call failed with -1728.
    func testTheRunningAppLoadedItsDictionary() throws {
        let registry = NSScriptSuiteRegistry.shared()
        // Suite + event code -> the class it binds.
        let verbs = [
            "FICHoprj": "FicheroOpenProjectCommand", "FICHopnd": "FicheroOpenNodeCommand",
            "FICHslnd": "FicheroSelectNodesCommand", "FICHrvsg": "FicheroRevealSegmentsCommand",
            "FICHshpn": "FicheroShowPaneCommand", "FICHshit": "FicheroShowInspectorTabCommand",
            "FICHshot": "FicheroScreenshotCommand", "FTSTdesw": "FicheroDescribeWindowCommand"
        ]
        for (codes, cls) in verbs {
            let description = registry.commandDescription(
                withAppleEventClass: Self.code(String(codes.prefix(4))), andAppleEventCode: Self.code(String(codes.suffix(4)))
            )
            XCTAssertEqual(description?.commandClassName, cls, "\(codes) is loaded")
            XCTAssertNotNil(NSClassFromString(cls), cls)
        }
    }

    private func command(_ event: String) throws -> NSScriptCommandDescription {
        try XCTUnwrap(NSScriptSuiteRegistry.shared().commandDescription(
            withAppleEventClass: Self.code("FICH"), andAppleEventCode: Self.code(event)
        ))
    }

    /// `openapi.ui.verbs-are-the-click` (#5453): an AppleScript command is its App Intent's call -- the
    /// same front-window request -- and a name that is not a pane or tab is refused naming the good ones.
    @MainActor
    func testTheCommandsCallTheUIVerbs() throws {
        let window = WindowState(libraryId: UUID())
        WindowState.front = window

        let show = FicheroShowPaneCommand(commandDescription: try command("shpn"))
        show.directParameter = "reading"
        XCTAssertEqual(show.performDefaultImplementation() as? Bool, true)
        XCTAssertEqual(window.uiVerbRequest?.action, .showPane(.reader))
        show.directParameter = "kg"
        XCTAssertNil(show.performDefaultImplementation())
        XCTAssertTrue(show.scriptErrorString?.contains("Panes: library, preview, reader") == true, show.scriptErrorString ?? "")

        let nodes = FicheroSelectNodesCommand(commandDescription: try command("slnd"))
        nodes.directParameter = ["doc-1", "doc-2"]
        XCTAssertEqual(nodes.performDefaultImplementation() as? Bool, true)
        XCTAssertEqual(window.uiVerbRequest?.action, .select(["doc-1", "doc-2"]))

        let inspector = FicheroShowInspectorTabCommand(commandDescription: try command("shit"))
        inspector.directParameter = "Entities"
        XCTAssertEqual(inspector.performDefaultImplementation() as? Bool, true)
        XCTAssertEqual(window.uiVerbRequest?.action, .showInspectorTab(.entities))
    }

    /// The smoke's pane step depends on the miss being LOUD and self-describing — a capture of a pane
    /// that is not shown must say which panes are, or every miss becomes an undebuggable blank.
    @MainActor
    func testPaneNotShownNamesThePanesShown() {
        let error = FicheroUICapture.CaptureError.paneNotShown(name: "preview", shown: ["reading", "library"])
        let message = String(describing: error)
        XCTAssertTrue(message.contains("preview"))
        XCTAssertTrue(message.contains("Panes shown: library, reading"))
    }

    /// Whole-window capture with no window must throw `.noWindow`, never
    /// return a path to nothing.
    @MainActor
    func testNoWindowErrorIsSelfDescribing() {
        let message = String(describing: FicheroUICapture.CaptureError.noWindow)
        XCTAssertTrue(message.contains("window"))
    }
}
#endif
