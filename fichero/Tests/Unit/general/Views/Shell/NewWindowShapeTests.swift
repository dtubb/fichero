@testable import Fichero
import Foundation
import Testing

/// A new window's shape (Daniel, 2026-10-11): about 1400 × 900, the sidebar about 225, the Inspector about 270,
/// the Items-and-Reader column about 265 with Items about 330 tall over the Reader, and the Preview the rest (about
/// 640). Driven through the same sizing rules the panes lay out with (`ContentView.childSizings`,
/// `WorkspaceSplitStack.resolvedExtents`).
@MainActor
struct NewWindowShapeTests {
    @Test("a new window is about 1400 × 900, with a 225-point sidebar and a 270-point Inspector")
    func windowAndSideColumns() {
        #expect(ContentView.defaultWindowSize == CGSize(width: 1400, height: 900))
        #expect(ContentView.defaultSidebarWidth == 225)
        #expect(ContentView.defaultInspectorWidth == 270)
        #expect(ContentView.defaultSidebarWidth >= ContentView.sidebarMinWidth)
        #expect(ContentView.defaultInspectorWidth >= ContentView.inspectorMinWidth)
    }

    @Test("Read lays out Items-and-Reader about 265 wide, Items about 330 tall over the Reader, the Preview about 640")
    func readColumns() throws {
        let row = BuiltInWorkspaceLayout.read.panes.nodes
        #expect(row.count == 2)
        // Across: the column (a split, no size of its own) and the Preview holding its share.
        let across = ContentView.childSizings([nil, .fraction(BuiltInWorkspaceLayout.readPreviewWidthFraction)],
                                              fallbackFraction: 0.4)
        let between = Double(ContentView.defaultWindowSize.width) - ContentView.defaultSidebarWidth
            - ContentView.defaultInspectorWidth
        let widths = WorkspaceSplitStack.resolvedExtents(across, total: between)
        let preview = try #require(widths[1])
        #expect(abs(preview - 640) < 15)
        #expect(abs((between - preview) - 265) < 15, "the Items-and-Reader column")
        // Down the column: Items over the Reader, under a toolbar of about 50 points.
        let down = ContentView.childSizings([.fraction(BuiltInWorkspaceLayout.readItemsHeightFraction), nil],
                                            fallbackFraction: 0.4)
        let heights = WorkspaceSplitStack.resolvedExtents(down, total: Double(ContentView.defaultWindowSize.height) - 50)
        let items = try #require(heights[0])
        #expect(abs(items - 330) < 15)
        // The leaves carry exactly those fractions.
        guard case let .split(_, axis, column) = row[0], case let .leaf(_, kind, _, itemsConfig) = column[0],
              case let .leaf(_, previewKind, _, previewConfig) = row[1] else {
            Issue.record("Read is a column split beside the Preview")
            return
        }
        #expect(axis == .vertical && kind == .library && previewKind == .preview)
        #expect(itemsConfig.paneFraction == BuiltInWorkspaceLayout.readItemsHeightFraction)
        #expect(previewConfig.paneFraction == BuiltInWorkspaceLayout.readPreviewWidthFraction)
    }
}
