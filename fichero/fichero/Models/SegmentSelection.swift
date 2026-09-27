import Foundation
import Observation

/// What is selected, as SEGMENT IDS (source-model slice 13, #4941).
///
/// WHY A FOURTH THING, when the app already has `RegionSelection` and
/// `FocusedRegionSelection` and the reader posts character offsets. Because none of
/// those can address a segment:
///
/// * `RegionSelection` holds **indices into one artifact's box list**. That is a
///   position used as an identity, which is the defect `source.app.index-is-the-engines`
///   exists to name and which has now appeared three times in this slice — most
///   recently as the reason `RegionEditTarget.forSelectionEdit` must refuse a selection
///   made against a different artifact. Every editor verb needs an id: `segment.update`
///   takes `segment_id` and `expected_version`, `segment.merge` takes `segment_ids`,
///   `reading_order.place` takes a `segment_id`.
/// * the reader's `.readerTextSelection` carries character offsets into a page's text.
///   A range is not a segment either; the preview resolves it to the word boxes whose
///   spans intersect, which is a derivation and not the selection itself.
///
/// So this is the one the editor, the Reader and the Inspector can all share
/// (`source.editor.selection-shared`), and it holds what the engine needs to be told.
///
/// A process-wide shared instance, the same shape as `FocusedArtifact.shared` and
/// `FocusedRegionSelection.shared`, and for the stated reason: writer and readers live
/// in different view subtrees, so environment plumbing cannot reach between them.
@Observable
@MainActor
final class SegmentSelection {
    static let shared = SegmentSelection()

    /// The selected segments, in the order they were picked — which is a record of what
    /// the person did, not a claim about reading order. A verb that needs reading order
    /// asks the engine's named order; combine does exactly that server-side, so click
    /// order stays free to mean "what I picked, when".
    private(set) var segmentIds: [String] = []

    /// The document the selection belongs to. A selection NEVER spans documents: two
    /// pages share no coordinate frame, no pass and no reading order, and a verb sent
    /// with ids from two pages would be one audited action claiming to be about a page
    /// it is not.
    private(set) var documentId: String?

    /// The pass the selected segments were read from, when the caller knows it. Kept
    /// because `source.app.edits-name-the-chosen-pass` is about exactly this: an edit
    /// goes to the result the SHOWN pass came from. A selection that cannot say which
    /// pass it was made in cannot answer that, and a verb should refuse rather than
    /// guess.
    private(set) var passId: String?

    /// The version each selected segment had when it was selected, so a verb can send
    /// `expected_version` without re-reading — and so a stale selection is REFUSED by
    /// the engine's compare-and-set rather than overwriting somebody's edit.
    private(set) var versions: [String: Int] = [:]

    init() {}

    var count: Int { segmentIds.count }
    var isEmpty: Bool { segmentIds.isEmpty }

    func isSelected(_ segmentId: String) -> Bool { segmentIds.contains(segmentId) }

    /// Replace the selection. `documentId` is required: a selection with no document
    /// cannot be checked against what is on screen, and every refusal in the editor
    /// depends on that check.
    func select(
        _ segmentIds: [String],
        documentId: String,
        passId: String? = nil,
        versions: [String: Int] = [:]
    ) {
        self.segmentIds = segmentIds
        self.documentId = documentId
        self.passId = passId
        self.versions = versions.filter { segmentIds.contains($0.key) }
    }

    /// Add to the selection, keeping pick order and refusing a cross-document add.
    ///
    /// Returns false when the add was refused, so a caller can say why rather than
    /// silently doing nothing — a shift-click that appears to do nothing is a bug
    /// report, and a shift-click that silently moved the selection to another page is
    /// worse.
    @discardableResult
    func add(_ segmentId: String, documentId: String, version: Int? = nil) -> Bool {
        if let current = self.documentId, current != documentId { return false }
        self.documentId = documentId
        if !segmentIds.contains(segmentId) { segmentIds.append(segmentId) }
        if let version { versions[segmentId] = version }
        return true
    }

    func deselect(_ segmentId: String) {
        segmentIds.removeAll { $0 == segmentId }
        versions[segmentId] = nil
        if segmentIds.isEmpty { documentId = nil; passId = nil }
    }

    func clear() {
        segmentIds = []
        documentId = nil
        passId = nil
        versions = [:]
    }

    /// Drop ids the page no longer has, after a change event patched it.
    ///
    /// A merge makes its absorbed ids stop existing and a delete removes one, so a held
    /// selection can name rows that are gone. Keeping them would send a verb ids the
    /// engine refuses one at a time; dropping them silently would make a Delete act on
    /// fewer lines than are highlighted. So it PRUNES and reports what went, and the
    /// caller decides whether to tell anybody.
    @discardableResult
    func prune(toLive liveIds: Set<String>) -> [String] {
        let gone = segmentIds.filter { !liveIds.contains($0) }
        guard !gone.isEmpty else { return [] }
        segmentIds.removeAll { gone.contains($0) }
        for id in gone { versions[id] = nil }
        if segmentIds.isEmpty { documentId = nil; passId = nil }
        return gone
    }

    /// The versions a verb should send for the current selection, or nil when any is
    /// missing.
    ///
    /// All or nothing on purpose: `segment.delete` takes `expected_versions` as a map of
    /// every id it is deleting, and sending a partial map would delete the rows it knows
    /// versions for and refuse the rest — half a Delete, which is worse than none.
    var expectedVersions: [String: Int]? {
        guard !segmentIds.isEmpty else { return nil }
        let known = versions.filter { segmentIds.contains($0.key) }
        return known.count == segmentIds.count ? known : nil
    }
}
