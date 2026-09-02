@testable import Fichero
import Foundation
import Testing

/// Every toolbar toggle that opens or closes a surface shows the lit state
/// while that surface is open (Daniel, 2026-09-02: "the way the workflow bar
/// and markup bar toggles already do").
///
/// A source scan, because the thing under test is which controls opted in.
/// The rendered tint is a pixel; the LIST of controls that ask for it is the
/// fact that regressed — before this, only the two bar toggles lit, and in the
/// toolbar's Icon Only mode nothing else told a user which panes were up.
struct ToolbarSurfaceLitStateTests {
    private static var toolbarSource: String {
        get throws {
            try String(
                contentsOf: AppSource.root().appendingPathComponent(
                    "Views/Shell/ContentView/ContentView+Toolbar.swift"),
                encoding: .utf8)
        }
    }

    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath),
                   encoding: .utf8)
    }

    @Test("every pane toggle lights with its own pane")
    func paneTogglesLight() throws {
        let source = try Self.toolbarSource
        for flag in ["model.isVisible", "showDocumentCanvas", "showReadingPane", "showChatPane"] {
            #expect(source.contains(".toolbarSurfaceLit(\(flag))"),
                    "the toggle governed by \(flag) does not light")
        }
    }

    @Test("the inspector and both bar toggles light too")
    func inspectorAndBarsLight() throws {
        let source = try Self.toolbarSource
        #expect(source.contains(".toolbarSurfaceLit(showInspectorSidebar)"))
        #expect(source.contains(".toolbarSurfaceLit(showAnnotationBar)"))
        #expect(source.contains(".toolbarSurfaceLit(showWorkflowBar)"))
    }

    @Test("the two bar toggles route through the shared modifier, not their own copy")
    func barTogglesShareOneImplementation() throws {
        // They had the accent expression inline — which is how the other six
        // controls never got it. One modifier is what makes "every toggle"
        // checkable at all.
        let source = try Self.toolbarSource
        #expect(!source.contains("AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.primary)"))
    }

    @Test("the status buttons light while their popover is open")
    func statusButtonsLight() throws {
        let engine = try Self.appSource("Views/Shell/Toolbar/EngineStatusToolbarItem.swift")
        let activity = try Self.appSource("Views/Shell/Toolbar/ActivityStatusToolbarItem.swift")
        #expect(engine.contains("showPopover"))
        #expect(engine.contains("AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.secondary)"))
        #expect(activity.contains("AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.secondary)"))
    }

    @Test("the lit state is a tint, never a filled control")
    func litStateIsAGlyphTintNotAFill() throws {
        // The 2026-08-29 ruling stands: an accent-FILLED on-state is bad UX.
        // The modifier may only reach for `foregroundStyle`.
        let modifier = try Self.appSource("Views/Shell/Toolbar/ToolbarSurfaceToggleStyle.swift")
        #expect(modifier.contains("foregroundStyle"))
        #expect(!modifier.contains(".background("))
        #expect(!modifier.contains("Toggle"))
    }

    @Test("the words still flip, so state reads without colour")
    func wordsStillCarryTheState() throws {
        let source = try Self.toolbarSource
        for pair in ["\"Hide Preview\" : \"Show Preview\"",
                     "\"Hide Reader\" : \"Show Reader\"",
                     "\"Hide Chat\" : \"Show Chat\"",
                     "\"Hide Library\" : \"Show Library\"",
                     "\"Hide Inspector\" : \"Show Inspector\""] {
            #expect(source.contains(pair), "the label for \(pair) stopped flipping")
        }
    }
}
