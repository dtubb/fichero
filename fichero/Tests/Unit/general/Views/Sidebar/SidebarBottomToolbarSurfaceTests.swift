@testable import Fichero
import SwiftUI
import XCTest

/// Source-surface test for the sidebar bottom toolbar's layout (2026-11-11): Xcode's navigator
/// order, [+] [−] [filter capsule] [workflow], as plain icons. Mirrors
/// `WorkflowImportExportSurfaceTests` (deterministic, token-free).
final class SidebarBottomToolbarSurfaceTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private static func bodyBlock(of source: String) throws -> String {
        let start = try XCTUnwrap(source.range(of: "var body: some View"))
        let end = try XCTUnwrap(source.range(of: "private var filterField: some View"))
        return String(source[start.upperBound..<end.lowerBound])
    }

    func testBarOrderIsNewRemoveFilterWorkflow() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarBottomToolbar.swift")
        let body = try Self.bodyBlock(of: source)
        let order = ["newItemMenu", "removeButton", "filterField", "newWorkflowButton"]
        let positions = try order.map { try XCTUnwrap(body.range(of: $0), "\($0) missing from the bar").lowerBound }
        XCTAssertEqual(positions, positions.sorted(), "bar order must be \(order)")
    }

    func testBarIsPlainIconsNotAFloatingGlassBar() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarBottomToolbar.swift")
        XCTAssertFalse(source.contains("PaneFilterBar {"), "the verbs no longer float in a glass bar")
        XCTAssertFalse(source.contains("AdaptiveMiniToolbarRow"), "no overflow ladder: the four controls stay inline")
        XCTAssertTrue(source.contains("Capsule()"), "the filter is the one shaped control")
    }

    /// Import is the + menu's own submenu (`AddItemMenu`), so the bar has no second icon for it.
    func testImportIsOnlyInThePlusMenu() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarBottomToolbar.swift")
        XCTAssertFalse(source.contains("square.and.arrow.down"))
        XCTAssertFalse(source.contains("Import Files"))
        XCTAssertFalse(source.contains("importFiles"))
        let menu = try Self.appSource("App/Menus/AddItemMenu.swift")
        XCTAssertTrue(menu.contains("Menu(\"Import\")"), "the + menu must still offer Import")
    }

    /// #4100: the sidebar shipped an Export button that was permanently
    /// `.disabled(true)`, with `.help("Export (not yet wired)")` saying so out
    /// loud. A control that can never do anything is placeholder chrome; File ▸
    /// Export already exports, and #2309 tracks the sidebar-scoped handler.
    func testNoDeadExportControl() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarBottomToolbar.swift")
        let code = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        XCTAssertFalse(code.contains("not yet wired"), "no shipped control may advertise itself as unwired")
        XCTAssertFalse(code.contains("Label(\"Export\""), "the Export entry is dead chrome")
        XCTAssertFalse(code.contains(".disabled(true)"), "a permanently disabled control must not ship")

        // The guard must not have gone blind on a moved or emptied file: the
        // verbs that DO belong here are still present.
        XCTAssertTrue(code.contains("New Workflow"))
        XCTAssertTrue(code.contains("New Item"))
    }

    /// #4061: the sidebar filter field lives inside the shared bottom
    /// `MiniToolbar` — one unified bottom toolbar owns the filter + the
    /// sidebar-scoped actions. The filter `TextField` + its clear button
    /// must be members of `SidebarBottomToolbar`, in the same bar as the
    /// verbs. NOT inside the `AdaptiveMiniToolbarRow` tiers (#5293): see
    /// `SidebarFilterFieldKeepsFocusTests` for what that broke.
    func testSidebarFilterLivesInSharedBottomMiniToolbar() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarBottomToolbar.swift")
        // The toolbar holds a binding to the filter text — same state/bindings
        // as the old standalone filter bar (no logic change, just relocation).
        XCTAssertTrue(source.contains("var sidebarFilterText: Binding<String>"))
        // The filter field is a member of the toolbar.
        XCTAssertTrue(source.contains("private var filterField: some View"))
        XCTAssertTrue(source.contains("TextField(\"Filter\", text: sidebarFilterText)"))
        XCTAssertTrue(source.contains("accessibilityIdentifier(\"sidebarFilterField\")"))
        // The clear button is part of the same field, shown only with text.
        XCTAssertTrue(source.contains("help(\"Clear filter\")"))
        XCTAssertTrue(source.contains("accessibilityLabel(\"Clear filter\")"))
        // The New-item / Delete verbs are in the same bar.
        XCTAssertTrue(source.contains("help(\"New Item\")"))
        XCTAssertTrue(source.contains("help(\"Remove selected item\")"))
    }

    /// #4061: the standalone sidebar filter chrome is gone. The old
    /// `sidebarFilterBar` member must no longer exist in
    /// `SidebarView+ViewComponents.swift` — the bottom toolbar owns the
    /// filter now, so there is no second `PaneFilterBar` stacked above it.
    func testStandaloneSidebarFilterBarIsGone() throws {
        let componentsSource = try Self.appSource(
            "Views/Sidebar/Sections/SidebarView+ViewComponents.swift"
        )
        XCTAssertFalse(componentsSource.contains("sidebarFilterBar"),
                       "standalone sidebarFilterBar must be removed — filter now lives in the bottom toolbar (#4061)")
        XCTAssertFalse(componentsSource.contains("TextField(\"Filter\", text: $sidebarFilterText)"),
                       "the filter TextField must not live in SidebarView+ViewComponents — it moved to SidebarBottomToolbar (#4061)")
        // The bottom toolbar receives the filter binding.
        XCTAssertTrue(componentsSource.contains("sidebarFilterText: $sidebarFilterText"),
                      "SidebarBottomToolbar must receive the sidebarFilterText binding")
    }
}

#if os(macOS)
/// #5293: the sidebar Filter field beeped and did not filter.
///
/// WHY this test exists: the field used to sit inside `AdaptiveMiniToolbarRow`,
/// a `ViewThatFits` ladder whose rungs are separate copies of their content. A
/// text field's ideal width grows as you type, so at sidebar widths of roughly
/// 228 to 320 pt a keystroke moved the row to the next rung; that mounted a NEW
/// field without focus, and the next key went nowhere (the beep). If this test
/// goes red, a text field is back inside a rung: move the field out, do not
/// loosen the test.
///
/// It types into the REAL toolbar, in a window that is never shown.
@MainActor
final class SidebarFilterFieldKeepsFocusTests: XCTestCase {
    private struct Host: View {
        @State var text = ""
        let width: CGFloat

        var body: some View {
            SidebarBottomToolbar(
                itemRegistry: ItemTypeRegistry(),
                sidebarFilterText: $text
            )
            .frame(width: width)
        }
    }

    private func editableField(in view: NSView) -> NSTextField? {
        if let field = view as? NSTextField, field.isEditable { return field }
        return view.subviews.lazy.compactMap { self.editableField(in: $0) }.first
    }

    /// What landed in the field when `typed` is keyed in one character at a time.
    private func type(_ typed: String, atWidth width: CGFloat) throws -> String {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: width, height: 60),
            styleMask: [.borderless], backing: .buffered, defer: false
        )
        window.isReleasedWhenClosed = false
        defer { window.close() }
        let host = NSHostingView(rootView: Host(width: width))
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))

        let field = try XCTUnwrap(editableField(in: host), "no filter field at width \(width)")
        window.makeFirstResponder(field)
        var landed = ""
        for character in typed {
            guard let editor = window.firstResponder as? NSTextView, editor.isFieldEditor else { break }
            editor.insertText(String(character), replacementRange: NSRange(location: NSNotFound, length: 0))
            landed.append(character)
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }
        return landed
    }

    func testTypingAFilterKeepsTheFieldFocusedAtEverySidebarWidth() throws {
        let typed = "marshall diary"
        // From narrower than the sidebar's minimum to wider than its default,
        // in steps small enough to land on every rung boundary.
        for width in stride(from: CGFloat(160), through: 420, by: 8) {
            XCTAssertEqual(
                try type(typed, atWidth: width), typed,
                "at a \(Int(width)) pt sidebar the filter field lost focus mid-word"
            )
        }
    }

    func testTheFieldKeepsRoomToTypeInANarrowSidebar() throws {
        let host = NSHostingView(rootView: Host(width: 160))
        host.frame = NSRect(x: 0, y: 0, width: 160, height: 60)
        host.layoutSubtreeIfNeeded()
        let field = try XCTUnwrap(editableField(in: host))
        XCTAssertGreaterThanOrEqual(field.frame.width, 24, "the verbs squeezed the filter field away")
    }
}
#endif
