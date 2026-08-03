import SwiftUI

/// The shared selection grammar for the canvas renderers that have NO
/// `CanvasInteractionController` (#4436).
///
/// The two legacy renderers — `Spatial2DCanvas` and `SpaceSceneView`, still
/// shipping as the flag-off fallbacks for `isCanvasRealityKit2DEnabled` /
/// `isCanvasRealityKit3DEnabled` — wrote `selectedNodeIds = [node.id]` at four
/// call sites. Plain replace, no ⌘-toggle, no anchor: the fifth and sixth
/// implementations of a concept that already had one. They cannot borrow the
/// controller (they predate it and drive the stores directly), so this is the
/// seam that lets them delegate instead of copy.
///
/// It is a thin adapter, not a second grammar. Every rule lives in
/// `SelectionGrammar`; this only translates the live platform modifiers and
/// writes the two fields back — the same two steps `CanvasInteractionController`
/// performs, reusing its translator rather than duplicating the `NSEvent` read.
@MainActor
enum CanvasTapSelection {

    /// A tap on a card or chip.
    ///
    /// ⇧ is passed through as "no modifier" for the same reason it is on the
    /// RealityKit canvas: a ⇧-range indexes an ORDERED list and a spatial
    /// surface has no inherent order, so choosing one is a product decision
    /// (#4460). ⌘ has no such problem — that branch is a pure toggle and never
    /// indexes `in:`, which is why the empty array here is correct today and
    /// would be silently wrong the moment ⇧ is wired.
    /// `modifiers: nil` means "read the live platform state" — the ordinary
    /// case. It is a parameter at all so a caller that must NOT consult the
    /// keyboard (a drag beginning on an unselected node) can say so, and so a
    /// test can drive this without an `NSEvent`.
    static func tap(
        _ id: String,
        selection: inout Set<String>,
        anchor: inout String?,
        modifiers: SelectionGrammar.Modifiers? = nil
    ) {
        let held = modifiers ?? CanvasInteractionController.liveSelectionModifiers()
        let result = SelectionGrammar.click(
            id: id,
            in: [],
            selection: selection,
            anchor: anchor,
            modifiers: held.contains(.command) ? .command : []
        )
        selection = result.selection
        anchor = result.anchor
    }

    /// A rubber-band drag. ⇧/⌘ ADD to the selection, as in Finder; a plain
    /// marquee replaces, and a plain marquee that caught nothing clears.
    static func marquee(
        _ ids: Set<String>,
        selection: inout Set<String>,
        anchor: inout String?,
        modifiers: SelectionGrammar.Modifiers? = nil
    ) {
        let result = SelectionGrammar.marquee(
            ids: ids,
            selection: selection,
            modifiers: modifiers ?? CanvasInteractionController.liveSelectionModifiers()
        )
        selection = result.selection
        anchor = result.anchor
    }
}
