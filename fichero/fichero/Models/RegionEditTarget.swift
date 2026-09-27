import Foundation

/// Which result a region edit is sent to, or `nil` for "send nothing"
/// (`source.app.edits-name-the-chosen-pass`, #4954).
///
/// The rule has three clauses and the third is a REFUSAL, which is why this is a
/// type rather than a `guard` repeated in four verbs:
///
/// 1. an edit goes to the result the SHOWN pass came from, and to no other. The
///    shown artifact id is whatever `loadOCRGeometry` last recorded, and since
///    2026-09-27 that comes from the winning PASS
///    (`SegmentDisplay.selected(for:store:)`) rather than a separate lookup.
/// 2. when what is shown changes, the next edit follows it. That falls out of (1):
///    `FocusedArtifact.shared.id` is part of the preview's `.task(id:)` identity,
///    so choosing another artifact reloads the geometry and reassigns the id.
/// 3. **with nothing shown, no edit is sent.** A refusal with no test is how a
///    silent write to the wrong pass ships, and the verbs' own `guard` could not be
///    tested without mounting a view.
///
/// Extracted from `ZoomableImagePreviewMac+Regions`'s verbs with their behaviour
/// unchanged: each already guarded on exactly these conditions.
enum RegionEditTarget {
    /// An edit that names its own boxes (move, add): it needs only a shown result.
    ///
    /// `nil` when nothing is shown — the page has no geometry, or a load failed, and
    /// an edit sent anyway would land on whatever artifact the engine picked, which
    /// is the "silent write to the wrong pass" this behaviour exists to prevent.
    static func forDirectEdit(shownArtifactId: String?) -> String? {
        guard let shown = shownArtifactId, !shown.isEmpty else { return nil }
        return shown
    }

    /// An edit that acts on the CURRENT SELECTION (delete, combine).
    ///
    /// Stricter than `forDirectEdit` by one clause, and the extra clause is the one
    /// that matters: the selection must belong to the artifact on screen. Indices are
    /// positions in one artifact's box list, so a selection made against the previous
    /// artifact names different boxes in this one — the same class of defect as
    /// addressing a box by its position in what happens to be drawn
    /// (`source.app.index-is-the-engines`).
    ///
    /// `minimumCount` is the verb's own arity: delete needs one box, combine two.
    static func forSelectionEdit(
        shownArtifactId: String?,
        selectionArtifactId: String?,
        selectionCount: Int,
        minimumCount: Int
    ) -> String? {
        guard let shown = forDirectEdit(shownArtifactId: shownArtifactId) else { return nil }
        guard selectionArtifactId == shown else { return nil }
        guard selectionCount >= minimumCount else { return nil }
        return shown
    }
}
