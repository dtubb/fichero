@testable import Fichero
import Testing

/// #6413 (segment-editor-crud Step 1.2, part b): the verbs act on the selection with no mode first; Edit Shape is a tool.
@MainActor
struct SegmentVerbsNeedNoModeTests {
    @Test func theMenuEnablesDeleteAndJoinFromTheSelectionCountAlone() {
        #expect(!SegmentMenuContent.canDelete(selected: 0))
        #expect(SegmentMenuContent.canDelete(selected: 1))
        #expect(SegmentMenuContent.reason(hasPage: true, selected: 1) == nil)
        #expect(SegmentMenuContent.reason(hasPage: true, selected: 0) == "Select segments on the page")
    }

    @Test func theMarkupRowOffersDeleteAndCombineWithNoModeAndTheShapeKindsOnlyInTheTool() {
        #expect(SegmentVerbs.offered(.all, isEditing: false, selectionCount: 1) == ["previewMarkupDelete"])
        #expect(SegmentVerbs.offered(.all, isEditing: false, selectionCount: 2) == ["previewMarkupDelete", "previewMarkupCombine"])
        #expect(SegmentVerbs.offered(.all, isEditing: true, selectionCount: 0) == ["previewMarkupShapeKind"])
    }

    @Test func theKeyAndTheRowActOnASelectionWithNoModeEntered() {
        #expect(SegmentEditingMode.deleteKey(marqueePicked: false, selectionCount: 2) == .deleteRegions)
        #expect(SegmentEditingMode.action(for: .delete, selectionCount: 2) == .delete)
        #expect(SegmentEditingMode.action(for: .combine, selectionCount: 2) == .combine)
        #expect(SegmentEditingMode.action(for: .combine, selectionCount: 1) == nil, "joining needs two")
    }

    @Test func drawingAndMovingByHandStayTheShapeToolsAndNeedTheTool() {
        #expect(!SegmentEditingMode.shapeDrawsSegment(isEditing: false))
        #expect(SegmentEditingMode.shapeDrawsSegment(isEditing: true))
        #expect(!SegmentEditingMode.pressStartsMove(isEditing: false, onSelectedBox: true))
    }
}
