@testable import Fichero
import SwiftUI
import XCTest

#if os(macOS)
/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.select-marquee-lasso` and
/// `segment-editor.select-shift-toggles` (#7033). Pages are covered by region, line and word boxes, so a drag that
/// starts on a box must still draw the band; the band selects every box it touches; a click selects; ⇧-click adds;
/// ⌘-click toggles. What breaks without this: Select does nothing on a page, because every press lands on a box.
@MainActor
final class SelectPointerTests: XCTestCase {
    private let size = CGSize(width: 400, height: 300)
    private let lines = [
        OCRGeometryBox(text: "a", bbox: [0.1, 0.1, 0.3, 0.1], level: "line", confidence: nil),
        OCRGeometryBox(text: "b", bbox: [0.1, 0.4, 0.3, 0.1], level: "line", confidence: nil),
        OCRGeometryBox(text: "c", bbox: [0.6, 0.7, 0.3, 0.1], level: "line", confidence: nil)
    ]

    private func event(_ phase: PreviewPointerPhase, _ across: Double, _ down: Double,
                       shift: Bool = false, command: Bool = false, option: Bool = false, control: Bool = false) -> PreviewPointerEvent {
        var event = PreviewPointerEvent(phase: phase, point: CGPoint(x: across, y: down), shift: shift, clickCount: 1)
        event.command = command
        event.option = option
        event.control = control
        return event
    }

    /// Host a layer over `lines` (all shown) and play `script` through the feed; returns the selection.
    private func play(_ script: [PreviewPointerEvent], onDrawBox: (([Double]) -> Void)? = nil) async throws -> RegionSelection {
        let selection = RegionSelection()
        let feed = PreviewPointerFeed()
        var layer = RegionInteractionLayer(
            boxes: lines.enumerated().map { (index: $0.offset, box: $0.element) }, allBoxes: lines,
            visible: CGRect(x: 0, y: 0, width: 1, height: 1), artifactId: "art",
            documentId: "page", marquees: nil, imagePixelSize: nil, isAddingRegion: false,
            drawsSelection: false, pointer: feed,
            onMoveCommit: { _, _ in }, onPromote: { _, _ in }, onOpenRegion: { _ in }, selection: selection
        )
        if let onDrawBox {
            layer.drawsSegments = true
            layer.onDrawBox = onDrawBox
        }
        let window = NSWindow(contentRect: CGRect(origin: CGPoint(x: 100, y: 100), size: size),
                              styleMask: [.borderless], backing: .buffered, defer: false)
        let host = NSHostingView(
            rootView: layer.environment(WindowState(libraryId: UUID())).frame(width: size.width, height: size.height)
        )
        window.contentView = host
        defer { window.contentView = nil }
        host.layoutSubtreeIfNeeded()
        try await Task.sleep(nanoseconds: 50_000_000)
        // The layer reads the feed once per update with the latest event: let each event land before the next.
        for step in script {
            feed.publish(step)
            for _ in 0..<5 {
                host.layoutSubtreeIfNeeded()
                try await Task.sleep(nanoseconds: 10_000_000)
            }
        }
        return selection
    }

    private func drag(from start: (Double, Double), to end: (Double, Double)) -> [PreviewPointerEvent] {
        [event(.pressed, start.0, start.1),
         event(.dragged, (start.0 + end.0) / 2, (start.1 + end.1) / 2),
         event(.dragged, end.0, end.1),
         event(.released, end.0, end.1)]
    }

    private func click(_ across: Double, _ down: Double, shift: Bool = false, command: Bool = false) -> [PreviewPointerEvent] {
        [event(.pressed, across, down, shift: shift, command: command),
         event(.released, across, down, shift: shift, command: command)]
    }

    func testADragThatStartsOnABoxSelectsEveryBoxItTouches() async throws {
        // Not exactly vertical: a band with no width is no box (`BoundingBoxGeometry.normalizedBox`), so it would be a click.
        let selection = try await play(drag(from: (0.2, 0.15), to: (0.25, 0.45)))
        XCTAssertEqual(Set(selection.indices), [0, 1], "the band started on line a and reached line b")
    }

    func testAClickSelectsTheBoxUnderIt() async throws {
        let selection = try await play(click(0.2, 0.15))
        XCTAssertEqual(selection.indices, [0])
    }

    func testShiftClickAddsToTheSelection() async throws {
        let selection = try await play(click(0.2, 0.15) + click(0.2, 0.45, shift: true))
        XCTAssertEqual(Set(selection.indices), [0, 1])
    }

    func testCommandClickTogglesABox() async throws {
        let added = try await play(click(0.2, 0.15) + click(0.2, 0.45, command: true))
        XCTAssertEqual(Set(added.indices), [0, 1], "⌘-click adds an unselected box")
        let removed = try await play(click(0.2, 0.15) + click(0.2, 0.45, command: true) + click(0.2, 0.45, command: true))
        XCTAssertEqual(removed.indices, [0], "⌘-click on a selected box takes it out")
    }

    /// A loop round line c (0.6-0.9 across, 0.7-0.8 down), pressed on empty page.
    private func loopRoundC(option: Bool, control: Bool) -> [PreviewPointerEvent] {
        let corners = [(0.55, 0.65), (0.95, 0.65), (0.95, 0.85), (0.55, 0.85)]
        var steps = [event(.pressed, 0.55, 0.65, option: option, control: control)]
        for corner in corners.dropFirst() { steps.append(event(.dragged, corner.0, corner.1, option: option, control: control)) }
        steps.append(event(.released, 0.55, 0.85, option: option, control: control))
        return steps
    }

    /// Owner ruling 2026-11-26: the lasso is ⌃-drag.
    func testControlDragIsTheLasso() async throws {
        let selection = try await play(loopRoundC(option: false, control: true))
        XCTAssertEqual(selection.indices, [2], "the loop held line c")
    }

    /// Owner ruling 2026-11-26: ⌥-drag in Select draws a new box, it does not lasso.
    func testOptionDragDrawsABoxAndSelectsNothing() async throws {
        var drawn: [[Double]] = []
        let selection = try await play(loopRoundC(option: true, control: false), onDrawBox: { drawn.append($0) })
        XCTAssertEqual(drawn.count, 1, "one box is drawn")
        XCTAssertTrue(selection.indices.isEmpty, "and nothing is lassoed")
    }
}
#endif
