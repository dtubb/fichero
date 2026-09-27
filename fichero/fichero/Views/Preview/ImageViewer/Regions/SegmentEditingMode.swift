// MARK: - Segment editing is a mode of the Source view (`source.editor.segment-focus`, #5114)
//
// Ruled 2026-09-27: segment editing is a MODE of the Preview / Source view, switched on
// from the view's what-to-show menu like its other view options. Off, the page is for
// reading. The rule this type encodes is one sentence: **with the mode off, nothing on
// the page changes.** Selecting and the ephemeral marquees (which are run scopes, not
// segments) stay available, because choosing what to read or what a workflow runs on
// is reading. Every verb that writes a segment -- move, delete, combine, promote a
// marquee or words to a region -- needs the mode.
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
    /// The selected persisted regions go -- an audited edit, so only in the mode.
    case deleteRegions
    case nothing
}

enum SegmentEditingMode {
    /// A verb from the head's markup row, or nil when the verb has nothing to do here.
    ///
    /// `.select` and `.draw` ARM tools (the row sets `activeMarkupTool` itself), so they
    /// are not edits. Combine needs two segments to have anything to merge.
    static func action(
        for verb: PreviewRegionVerb, isEditing: Bool, selectionCount: Int
    ) -> SegmentEditAction? {
        guard isEditing else { return nil }
        switch verb {
        case .select, .draw: return nil
        case .delete: return selectionCount > 0 ? .delete : nil
        case .combine: return selectionCount >= 2 ? .combine : nil
        }
    }

    /// ⌫: the most recent, most ephemeral thing first -- a picked marquee -- then the
    /// selected regions, and those only in the mode.
    static func deleteKey(
        marqueePicked: Bool, isEditing: Bool, selectionCount: Int
    ) -> SegmentDeleteKeyAction {
        if marqueePicked { return .removeMarquee }
        return isEditing && selectionCount > 0 ? .deleteRegions : .nothing
    }

    /// What a finished drag with the SHAPE tool makes (ruled 2026-09-27, Q1: Draw Region is
    /// merged into the one Shape tool). In the mode it is a SEGMENT -- the drawn box is promoted
    /// at once through the same path "New Region from Selection" uses, so there is one way to
    /// make a region. Outside the mode it is a marquee, a run scope, as it always was: drawing
    /// while reading chooses what to read or run on, and writes nothing.
    static func shapeDrawsSegment(isEditing: Bool) -> Bool { isEditing }

    /// A press on a selected box starts a move only in the mode; while reading it is a
    /// click, which re-selects.
    static func pressStartsMove(isEditing: Bool, onSelectedBox: Bool) -> Bool {
        isEditing && onSelectedBox
    }
}
