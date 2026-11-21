@testable import Fichero
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- the tool row is one choice (#6734). Exactly one tool is
/// active and shown: a flag tool (Knife, Marker, Order, Brush, Paintbrush) leaves Select empty, so Select is not also
/// highlighted and does not take the drag; another tool or Esc moves the choice. What breaks without this: two tools
/// look active and Select handles the drag meant for a brush.
@MainActor
@Suite(.tags(.paleography))
struct SegmentToolChoiceTests {
    private static let all: [SegmentFlagTool] = [.knife, .marker, .order, .brush, .paint]

    @Test("choosing each flag tool leaves only that tool active, and Select not active")
    func exactlyOne() {
        let window = WindowState(libraryId: UUID())
        for tool in Self.all {
            window.chooseSegmentTool(tool)
            #expect(window.activeSegmentTool == tool)
            #expect(window.activeMarkupTool == nil, "\(tool): Select is not also active")
            let flags = [window.knifeArmed, window.markerArmed, window.orderArmed, window.brushArmed, window.paintArmed]
            #expect(flags.filter { $0 }.count == 1, "\(tool): one flag only")
        }
    }

    @Test("choosing another tool moves the choice; putting it down returns to Select")
    func moves() {
        let window = WindowState(libraryId: UUID())
        window.chooseSegmentTool(.paint)
        window.chooseSegmentTool(.brush)
        #expect(window.activeSegmentTool == .brush)
        #expect(!window.paintArmed)
        window.chooseSegmentTool(nil)
        #expect(window.activeSegmentTool == nil)
        #expect(window.activeMarkupTool == .select)
        window.chooseSegmentTool(.knife)
        window.activeMarkupTool = .drawRegion
        #expect(window.activeSegmentTool == nil, "a drawing tool puts the flag tool down")
    }

    @Test("a tap of each tool's key chooses it alone")
    func keys() {
        let window = WindowState(libraryId: UUID())
        window.chooseSegmentTool(.paint)
        window.pressBrushKey()
        window.letGoOfBrushKey()
        #expect(window.activeSegmentTool == .brush)
        window.pressKnifeKey()
        window.letGoOfKnifeKey()
        #expect(window.activeSegmentTool == .knife)
        window.pressMarkerKey()
        window.letGoOfMarkerKey()
        #expect(window.activeSegmentTool == .marker)
        #expect(window.activeMarkupTool == nil)
    }
}
