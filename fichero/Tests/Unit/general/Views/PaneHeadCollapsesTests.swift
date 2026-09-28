@testable import Fichero
import SwiftUI
import XCTest

#if os(macOS)
/// A narrow window's pane head (#5213, Daniel): its icons did not collapse, so the head could not fit one
/// row and its width stopped the window narrowing. What breaks without this: the controls go back to one
/// fixed row, and the pane's minimum width is the sum of every control again.
@MainActor
final class PaneHeadCollapsesTests: XCTestCase {
    private func host(width: CGFloat) -> NSHostingView<some View> {
        let head = PaneHead<EmptyView, AnyView, EmptyView>(
            crumbs: [
                PaneCrumb(id: "a", title: "Acceptance 2026-09-27b", icon: "books.vertical.fill"),
                PaneCrumb(id: "b", title: "syriac-rtl", icon: "folder.fill"),
                PaneCrumb(id: "c", title: "onb-syr1-0001", icon: "photo.fill")
            ],
            onClose: {},
            selector: { EmptyView() },
            controls: {
                AnyView(HStack {
                    Button("Lens") {}.accessibilityIdentifier("lensControl")
                    Button("Regions") {}.accessibilityIdentifier("regionsControl")
                    Button("Renditions") {}.accessibilityIdentifier("renditionsControl")
                })
            },
            tools: { EmptyView() }
        )
        let window = NSWindow(contentRect: CGRect(x: 0, y: 0, width: width, height: 60),
                              styleMask: [.borderless], backing: .buffered, defer: false)
        let view = NSHostingView(rootView: head.frame(width: width, height: 60))
        window.contentView = view
        return view
    }

    func testANarrowHeadFitsOneRowWithItsControlsInTheOverflowMenu() async throws {
        let narrow = host(width: 240)
        defer { narrow.window?.contentView = nil }
        let overflow = try await element(PaneHeadMetrics.overflowIdentifier, under: narrow)
        let frame = try XCTUnwrap(overflow, "the controls fold into the … menu").accessibilityFrame()
        let inWindow = try XCTUnwrap(narrow.window).convertFromScreen(frame)
        XCTAssertLessThanOrEqual(inWindow.maxX, 240, "the head fits the pane: nothing runs past its edge")
        let lens = try await element("lensControl", under: narrow, waiting: false)
        XCTAssertNil(lens, "a folded control is in the menu, not in the row")
    }

    func testAWideHeadShowsItsControlsAndNoOverflow() async throws {
        let wide = host(width: 900)
        defer { wide.window?.contentView = nil }
        let lens = try await element("lensControl", under: wide)
        XCTAssertNotNil(lens, "with room, the controls sit in the row")
        let overflow = try await element(PaneHeadMetrics.overflowIdentifier, under: wide, waiting: false)
        XCTAssertNil(overflow, "and nothing is folded away")
    }

    /// The first accessibility element with this identifier; waits for SwiftUI's layout unless told not to.
    private func element(_ identifier: String, under root: NSView, waiting: Bool = true) async throws -> NSAccessibilityElementProtocol? {
        for _ in 0..<(waiting ? 100 : 5) {
            root.layoutSubtreeIfNeeded()
            if let found = Self.find(identifier, in: root) { return found }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        return nil
    }

    private static func find(_ identifier: String, in node: Any) -> NSAccessibilityElementProtocol? {
        guard let element = node as? NSAccessibilityElementProtocol & NSObject else { return nil }
        if (element as? NSAccessibilityProtocol)?.accessibilityIdentifier() == identifier { return element }
        for child in (element as? NSAccessibilityProtocol)?.accessibilityChildren() ?? [] {
            if let found = find(identifier, in: child) { return found }
        }
        return nil
    }
}
#endif
