@testable import Fichero
import CoreGraphics
import Foundation
import Testing

/// The two bars beneath the window toolbar are the toolbar's size, not
/// approximately it (Daniel, 2026-09-02: the model mark "blows up the UX";
/// "the whole workflow strip should match toolbar metrics").
///
/// A value test where one is possible, and a source scan only for the wiring:
/// the numbers themselves are pure, but "the chip passes the toolbar's glyph
/// size" is a fact about a call site.
struct ToolbarMetricsTests {
    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath),
                   encoding: .utf8)
    }

    @Test("a toolbar glyph is one square, and it is not badge sized")
    func glyphSideIsToolbarSized() {
        #expect(ToolbarMetrics.glyphSide == 16)
        // The regression this pins: the family mark defaulted to 20pt, three
        // points taller than the `.body` SF Symbols on either side of it.
        #expect(ToolbarMetrics.glyphSide < 20)
        #expect(ModelFamilyMark(model: "", provider: "").side == ToolbarMetrics.glyphSide)
    }

    @Test("a bar's height follows its label mode")
    func rowHeightFollowsLabels() {
        #expect(ToolbarMetrics.rowHeight(showsLabels: true) == ToolbarMetrics.rowHeightWithLabels)
        #expect(ToolbarMetrics.rowHeight(showsLabels: false) == ToolbarMetrics.rowHeightIconOnly)
        // Hiding the labels must actually shrink the strip — the workflow
        // bar's verb row was pinned at the tall value in both modes, so
        // turning labels off left a band of empty bar above the content.
        #expect(ToolbarMetrics.rowHeight(showsLabels: false)
                < ToolbarMetrics.rowHeight(showsLabels: true))
    }

    @Test("both bars read the shared table rather than their own literals")
    func barsShareOneHeightTable() throws {
        let workflowBar = try Self.appSource("Views/Shell/Toolbar/WorkflowBar.swift")
        let annotationBar = try Self.appSource("Views/Shell/Toolbar/AnnotationBar.swift")
        #expect(workflowBar.contains("ToolbarMetrics.rowHeight(showsLabels: showsLabels)"))
        #expect(annotationBar.contains("ToolbarMetrics.rowHeight(showsLabels: showsLabels)"))
        // The literals they used to carry are gone, not merely shadowed.
        #expect(!workflowBar.contains(".frame(height: 52)"))
        #expect(!annotationBar.contains("showsLabels ? 52 : 38"))
    }

    @Test("the model chip asks for the toolbar's glyph size by name")
    func modelChipUsesTheSharedGlyphSize() throws {
        let chip = try Self.appSource("Views/Shell/Toolbar/ModelChipToolbarItem.swift")
        #expect(chip.contains("side: ToolbarMetrics.glyphSide"))
        #expect(!chip.contains("var side: CGFloat = 20"))
    }
}
