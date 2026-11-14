@testable import Fichero
import Testing

/// `source.editor.segment-focus` (#5114, ruled 2026-09-27): segment editing is a mode of
/// the Source view, and with it off NOTHING ON THE PAGE CHANGES.
///
/// Why these exist: before the mode, the markup row's Delete and Combine buttons (and
/// Combine's ⌘⌥C) posted a notification nothing observed -- two buttons that did nothing.
/// The fix routes them through `SegmentEditingMode.action`, so these pin both halves: in
/// the mode the verbs DO something, and out of it a stray press edits nothing.
@MainActor
struct SegmentEditingModeTests {

    @Test func deleteAndCombineActInTheMode() {
        #expect(SegmentEditingMode.action(for: .delete, selectionCount: 1) == .delete)
        #expect(SegmentEditingMode.action(for: .combine, selectionCount: 2) == .combine)
    }

    /// #6413: no mode first. Only the verbs that ARM a tool (select, draw) are not edits.
    @Test func noModeIsNeededForAVerbToAct() {
        #expect(SegmentEditingMode.action(for: .delete, selectionCount: 5) == .delete)
        #expect(SegmentEditingMode.action(for: .combine, selectionCount: 5) == .combine)
    }

    @Test func combineNeedsTwoAndDeleteNeedsOne() {
        #expect(SegmentEditingMode.action(for: .combine, selectionCount: 1) == nil)
        #expect(SegmentEditingMode.action(for: .delete, selectionCount: 0) == nil)
    }

    /// Select and Draw ARM tools; treating them as edits would fire a verb on arming.
    @Test func selectAndDrawAreNotEdits() {
        #expect(SegmentEditingMode.action(for: .select, selectionCount: 3) == nil)
        #expect(SegmentEditingMode.action(for: .draw, selectionCount: 3) == nil)
    }

    /// A marquee is a run scope, not a segment: ⌫ removes it while reading too.
    @Test func deleteKeyRemovesAPickedMarqueeFirst() {
        #expect(SegmentEditingMode.deleteKey(marqueePicked: true, selectionCount: 3) == .removeMarquee)
    }

    /// A selection is the edit state (#6413): click a region, press ⌫, and it is deleted (one ⌘Z).
    @Test func deleteKeyDeletesTheSelectionWithNoModeFirst() {
        #expect(SegmentEditingMode.deleteKey(marqueePicked: false, selectionCount: 1) == .deleteRegions)
        // `segment-editor.vertices`: ⌫ with a pressed point removes that point, not the segment it sits on.
        #expect(SegmentEditingMode.deleteKey(marqueePicked: false, selectionCount: 1, pointPressed: true) == .removePoint)
        #expect(SegmentEditingMode.deleteKey(marqueePicked: true, selectionCount: 1, pointPressed: true) == .removeMarquee)
        // `segment-editor.cut-marks-editable`: ⌫ with a cut mark picked removes that cut, before a point or the selection.
        #expect(SegmentEditingMode.deleteKey(
            marqueePicked: false, selectionCount: 2, pointPressed: true, cutMarkPicked: true
        ) == .removeCut)
        #expect(SegmentShapes.removing([[0, 0], [1, 0], [1, 1], [0, 1]], index: 1, .polygon) == [[0, 0], [1, 1], [0, 1]])
        #expect(SegmentShapes.removing([[0, 0], [1, 0], [1, 1]], index: 1, .polygon) == nil, "an outline keeps three")
        #expect(SegmentEditingMode.deleteKey(marqueePicked: false, selectionCount: 0) == .nothing)
    }

    @Test func aPressOnASelectedBoxMovesItOnlyInTheMode() {
        #expect(SegmentEditingMode.pressStartsMove(isEditing: true, onSelectedBox: true))
        #expect(!SegmentEditingMode.pressStartsMove(isEditing: false, onSelectedBox: true))
        #expect(!SegmentEditingMode.pressStartsMove(isEditing: true, onSelectedBox: false))
    }

    /// Off is the default: a window opens for reading.
    @Test func aNewWindowOpensForReading() {
        #expect(WindowState(libraryId: LibraryManager.globalLibraryId).isEditingSegments == false)
    }

    /// The one Shape tool (ruled 2026-09-27, Q1). While editing, a drawn box is a segment; while
    /// reading it stays a marquee -- a run scope that writes nothing. Getting this backwards would
    /// write a region every time somebody drew a box to choose what to read.
    @Test func theShapeToolDrawsASegmentOnlyWhileEditing() {
        #expect(SegmentEditingMode.shapeDrawsSegment(isEditing: true))
        #expect(!SegmentEditingMode.shapeDrawsSegment(isEditing: false))
    }

    /// Merged, not added: the tool keeps its place, its ⌘⌥R and its identifier; only its name
    /// and what it makes in the mode change.
    @Test func drawRegionIsNowCalledShape() {
        #expect(PreviewMarkupTool.drawRegion.label == "Shape")
    }
}
