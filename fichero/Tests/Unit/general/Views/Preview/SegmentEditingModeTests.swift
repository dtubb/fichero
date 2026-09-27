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
        #expect(SegmentEditingMode.action(for: .delete, isEditing: true, selectionCount: 1) == .delete)
        #expect(SegmentEditingMode.action(for: .combine, isEditing: true, selectionCount: 2) == .combine)
    }

    @Test func outOfTheModeNoVerbEdits() {
        for verb in [PreviewRegionVerb.select, .draw, .delete, .combine] {
            #expect(SegmentEditingMode.action(for: verb, isEditing: false, selectionCount: 5) == nil)
        }
    }

    @Test func combineNeedsTwoAndDeleteNeedsOne() {
        #expect(SegmentEditingMode.action(for: .combine, isEditing: true, selectionCount: 1) == nil)
        #expect(SegmentEditingMode.action(for: .delete, isEditing: true, selectionCount: 0) == nil)
    }

    /// Select and Draw ARM tools; treating them as edits would fire a verb on arming.
    @Test func selectAndDrawAreNotEdits() {
        #expect(SegmentEditingMode.action(for: .select, isEditing: true, selectionCount: 3) == nil)
        #expect(SegmentEditingMode.action(for: .draw, isEditing: true, selectionCount: 3) == nil)
    }

    /// A marquee is a run scope, not a segment: ⌫ removes it while reading too.
    @Test func deleteKeyRemovesAPickedMarqueeInEitherMode() {
        for editing in [false, true] {
            #expect(SegmentEditingMode.deleteKey(marqueePicked: true, isEditing: editing, selectionCount: 3) == .removeMarquee)
        }
    }

    /// The case that would lose work: reading a page, a region selected to see its text,
    /// ⌫ pressed -- the region must survive.
    @Test func deleteKeyNeverDeletesARegionWhileReading() {
        #expect(SegmentEditingMode.deleteKey(marqueePicked: false, isEditing: false, selectionCount: 1) == .nothing)
        #expect(SegmentEditingMode.deleteKey(marqueePicked: false, isEditing: true, selectionCount: 1) == .deleteRegions)
        #expect(SegmentEditingMode.deleteKey(marqueePicked: false, isEditing: true, selectionCount: 0) == .nothing)
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
