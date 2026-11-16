// MARK: - A selection is the edit state (`source.editor.no-mode-gate-selection-is-the-edit-state`, #6413)
//
// Ruled 2026-11-08 (replacing the 2026-09-27 mode of #5114): delete, combine, the attributes, promoting a marquee or
// words and the nudge act on the SELECTED segments with no mode first. What stays a mode is the SHAPE tool: drawing a
// new shape by hand (`shapeDrawsSegment`) and moving a box by dragging (`pressStartsMove`), like the markup tools.
//
// Pure, so the gates are tested as decisions rather than scanned out of view bodies.

/// What a persistent region verb does, once the mode has had its say.
enum SegmentEditAction: Equatable {
    case delete
    case combine
}

/// What ⌫ does on the image.
enum SegmentDeleteKeyAction: Equatable {
    /// The picked marquee goes. Ephemeral, so allowed while reading.
    case removeMarquee
    /// The selected persisted regions go -- an audited edit with one ⌘Z, on the selection alone.
    case deleteRegions
    /// The shape point last pressed in Edit Segments goes (`segment-editor.vertices`), one reshape, one ⌘Z.
    case removePoint
    /// The cut mark last clicked goes: its two pieces joined (`segment-editor.cut-marks-editable`), one ⌘Z.
    case removeCut
    case nothing
}

enum SegmentEditingMode {
    /// A verb from the head's markup row, or nil when the verb has nothing to do here.
    ///
    /// `.select` and `.draw` ARM tools (the row sets `activeMarkupTool` itself), so they
    /// are not edits. Combine needs two segments to have anything to merge.
    static func action(for verb: PreviewRegionVerb, selectionCount: Int) -> SegmentEditAction? {
        switch verb {
        case .select, .draw: return nil
        case .delete: return selectionCount > 0 ? .delete : nil
        case .combine: return selectionCount >= 2 ? .combine : nil
        }
    }

    /// ⌫: the most recent, most ephemeral thing first -- a picked marquee -- then a picked cut mark, then a pressed
    /// shape point, then the selected regions.
    static func deleteKey(
        marqueePicked: Bool, selectionCount: Int, pointPressed: Bool = false, cutMarkPicked: Bool = false
    ) -> SegmentDeleteKeyAction {
        if marqueePicked { return .removeMarquee }
        if cutMarkPicked { return .removeCut }
        // A pressed point is smaller and more recent than the selection it sits on: it goes alone.
        if pointPressed { return .removePoint }
        return selectionCount > 0 ? .deleteRegions : .nothing
    }

    /// What a finished drag with the SHAPE tool makes (ruled 2026-09-27, Q1: Draw Region is
    /// merged into the one Shape tool). In the mode it is a SEGMENT -- the drawn box is promoted
    /// at once through the same path "New Region from Selection" uses, so there is one way to
    /// make a region. Outside the mode it is a marquee, a run scope, as it always was: drawing
    /// while reading chooses what to read or run on, and writes nothing.
    static func shapeDrawsSegment(isEditing: Bool) -> Bool { isEditing }

    /// A press on a selected box starts a move only in the mode; while reading it is a
    /// click, which re-selects. With ⇧ it is a ⇧-click, which takes the box out of the selection
    /// (`segment-editor.select-shift-toggles`).
    static func pressStartsMove(isEditing: Bool, onSelectedBox: Bool, shift: Bool = false) -> Bool {
        isEditing && onSelectedBox && !shift
    }
}

/// Which door a Preview Delete takes (#6419). Boxes that ARE segments (each carries a segment id, and each segment has the version
/// the engine checks an edit against) go through the one audited `segment.delete` batch, `SegmentDeleter`, so the segment goes
/// with its box, in one step and one ⌘Z, on every surface. Anything else is a box of a result artifact that is not rows yet: the
/// artifact route converts it and deletes (and the segments are re-read afterwards, so no surface keeps the old ones).
enum PreviewRegionDelete {
    enum Door: Equatable {
        case segments
        case artifact
    }

    /// `selectionCount` boxes are selected; `segmentCount` of them name a segment and `versionedCount` of those have a version.
    static func door(selectionCount: Int, segmentCount: Int, versionedCount: Int) -> Door {
        selectionCount > 0 && segmentCount == selectionCount && versionedCount == segmentCount ? .segments : .artifact
    }
}
