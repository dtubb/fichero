@testable import Fichero
import SwiftUI
import XCTest

#if os(macOS)
/// A narrow window's pane head (#5213, Daniel): its icons did not collapse, so the head could not fit one
/// row and its width stopped the window narrowing. What breaks without this: the controls go back to one
/// fixed row, and the pane's minimum width is the sum of every control again.
///
/// The test host's in-process accessibility tree is empty, so the head reports where its parts landed through
/// its test-only `onPartFrame` probe (nil in the app), as the region band does with `onBandFrame`.
@MainActor
final class PaneHeadCollapsesTests: XCTestCase {
    /// The frames the head reported, by part.
    private final class Probe {
        var frames: [String: CGRect] = [:]
    }

    private func host(width: CGFloat, probe: Probe) -> NSHostingView<some View> {
        let head = PaneHead<EmptyView, AnyView, EmptyView>(
            crumbs: [
                PaneCrumb(id: "a", title: "Acceptance 2026-09-27b", icon: "books.vertical.fill"),
                PaneCrumb(id: "b", title: "syriac-rtl", icon: "folder.fill"),
                PaneCrumb(id: "c", title: "onb-syr1-0001", icon: "photo.fill")
            ],
            onClose: {},
            onPartFrame: { probe.frames[$0] = $1 },
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
        let probe = Probe()
        let narrow = host(width: 240, probe: probe)
        defer { narrow.window?.contentView = nil }
        let overflow = try await frame(PaneHeadMetrics.overflowIdentifier, in: probe, under: narrow)
        let inWindow = try XCTUnwrap(overflow, "the controls fold into the … menu")
        XCTAssertLessThanOrEqual(inWindow.maxX, 240, "the head fits the pane: nothing runs past its edge")
        let lens = try await frame(PaneHeadMetrics.controlsIdentifier, in: probe, under: narrow, waiting: false)
        XCTAssertNil(lens, "a folded control is in the menu, not in the row")
    }

    func testAWideHeadShowsItsControlsAndNoOverflow() async throws {
        let probe = Probe()
        let wide = host(width: 900, probe: probe)
        defer { wide.window?.contentView = nil }
        let lens = try await frame(PaneHeadMetrics.controlsIdentifier, in: probe, under: wide)
        XCTAssertNotNil(lens, "with room, the controls sit in the row")
        let overflow = try await frame(PaneHeadMetrics.overflowIdentifier, in: probe, under: wide, waiting: false)
        XCTAssertNil(overflow, "and nothing is folded away")
    }

    /// The frame the head reported for this part (in the hosting view's space); waits for SwiftUI's layout
    /// unless told not to.
    private func frame(_ part: String, in probe: Probe, under root: NSView, waiting: Bool = true) async throws -> CGRect? {
        for _ in 0..<(waiting ? 100 : 5) {
            root.layoutSubtreeIfNeeded()
            if let found = probe.frames[part] { return found }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        return nil
    }
}
#endif
