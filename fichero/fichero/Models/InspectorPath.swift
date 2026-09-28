import Foundation

/// What the Inspector inspects, as segments, and the path head above it (ruled 2026-09-27,
/// `build-notes-inspector.md`): Source › page › block › line › word, where clicking a crumb inspects
/// that level. Pure, like `ReadingOrderMove`: the rules live where a test can reach them.
struct InspectorPath: Equatable {
    struct Crumb: Equatable, Identifiable {
        let segmentId: String
        let kind: String
        var id: String { segmentId }
        /// "Line", "Block" -- the level, which is what a crumb names; the words are the Text section's.
        var label: String { kind.capitalized }
    }

    /// Outermost first, ending at the inspected segment. EMPTY means the page itself: a mixed
    /// selection whose segments share no parent segment.
    let crumbs: [Crumb]

    /// The path to one segment among its page's segments; nil when it is not among them.
    ///
    /// A parent missing from the list ENDS the walk rather than guessing one, and so does a cycle:
    /// a path with a crumb nobody can open would be worse than a shorter true one.
    static func to(_ segmentId: String, in segments: [Segment]) -> InspectorPath? {
        let byId = Dictionary(segments.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        guard var current = byId[segmentId] else { return nil }
        var chain = [current]
        var seen: Set<String> = [current.id]
        while let parentId = current.parentSegmentId, let parent = byId[parentId], seen.insert(parentId).inserted {
            chain.append(parent)
            current = parent
        }
        return InspectorPath(crumbs: chain.reversed().map { Crumb(segmentId: $0.id, kind: $0.kind) })
    }

    /// A MIXED selection shows its nearest common parent (ruled): the longest path every selected
    /// segment's path starts with. Nil when any selected id is not on the page.
    static func common(_ segmentIds: [String], in segments: [Segment]) -> InspectorPath? {
        let paths = segmentIds.compactMap { to($0, in: segments) }
        guard let first = paths.first, paths.count == segmentIds.count else { return nil }
        var shared = first.crumbs
        for path in paths.dropFirst() {
            shared = zip(shared, path.crumbs).prefix { $0 == $1 }.map(\.0)
        }
        return InspectorPath(crumbs: shared)
    }

    /// "3 lines, 1 word": a mixed selection's count by kind, most first, then by name.
    static func kindCounts(_ segmentIds: [String], in segments: [Segment]) -> [(kind: String, count: Int)] {
        let wanted = Set(segmentIds)
        var counts: [String: Int] = [:]
        for segment in segments where wanted.contains(segment.id) {
            counts[segment.kind, default: 0] += 1
        }
        return counts.map { (kind: $0.key, count: $0.value) }
            .sorted { $0.count != $1.count ? $0.count > $1.count : $0.kind < $1.kind }
    }

    /// The Source view's selection on one page as segment ids -- what the Inspector inspects. Its box
    /// indices are resolved against the boxes of the pass its scope names, read through the
    /// selection's own identity keys (`resolvedIndices(in:)`), so a list that changed order is not
    /// misread. The ONE resolution, called by `SourceSectionView` and by its end-to-end test.
    @MainActor
    static func selectedSegmentIds(selection: RegionSelection, documentId: String, store: SegmentStore) -> [String] {
        guard !selection.isEmpty, selection.documentId == documentId else { return [] }
        let passes = store.passes(documentId: documentId)
        let segments = store.segments(documentId: documentId)
        guard let pass = passes.first(where: {
            SegmentDisplay.selectionScope(artifactId: $0.sourceArtifactId, passId: $0.id) == selection.artifactId
        }),
              let boxes = SegmentDisplay.geometry(
                  from: segments.filter { $0.passId == pass.id }, provider: "", model: nil, renditionId: nil
              )?.boxes else { return [] }
        return segmentIds(
            selectedIndices: selection.resolvedIndices(in: boxes), artifactId: selection.artifactId,
            passes: passes, segments: segments
        )
    }

    /// The INVERSE (#5155, one selection across the three surfaces): make `segmentIds` the Source
    /// view's selection on this page -- a row picked in the Order list, the Reader's caret line.
    /// Written in the shown pass's scope and box indices, so the boxes light and the Inspector (which
    /// reads the same selection back through `selectedSegmentIds`) inspects them. Ids of another pass
    /// than the one shown are left out: they are not on screen to be selected. Answers the ids selected.
    @MainActor
    @discardableResult
    static func select(
        segmentIds: [String], into selection: RegionSelection, documentId: String, store: SegmentStore
    ) -> [String] {
        guard let shown = SegmentDisplay.selected(for: documentId, store: store),
              let scope = SegmentDisplay.selectionScope(artifactId: shown.artifactId, passId: shown.passId)
        else { return [] }
        let byId = Dictionary(
            store.segments(documentId: documentId).filter { $0.passId == shown.passId }.map { ($0.id, $0) },
            uniquingKeysWith: { first, _ in first }
        )
        let picked = segmentIds.compactMap { id in byId[id].flatMap { seg in seg.boxIndex.map { (id, $0) } } }
        guard !picked.isEmpty else { return [] }
        selection.selectAll(picked.map(\.1), artifactId: scope, documentId: documentId, in: shown.geometry.boxes)
        return picked.map(\.0)
    }

    /// The Source view's selection -- indices into the boxes of the pass its scope names (the pass's
    /// artifact, or the pass itself when it has none: `SegmentDisplay.selectionScope`) -- as segment
    /// ids, in the order picked. A box index is the segment's `boxIndex` in that pass
    /// (`SegmentDisplay.geometry`). No pass for the artifact means no segments, never a guess at
    /// another pass: the same boxes in another pass are other segments.
    static func segmentIds(
        selectedIndices: [Int], artifactId: String?,
        passes: [SegmentPassValue], segments: [Segment]
    ) -> [String] {
        guard let artifactId, let pass = passes.first(where: {
            SegmentDisplay.selectionScope(artifactId: $0.sourceArtifactId, passId: $0.id) == artifactId
        }) else { return [] }
        let byIndex = Dictionary(
            segments.filter { $0.passId == pass.id }.compactMap { seg in seg.boxIndex.map { ($0, seg.id) } },
            uniquingKeysWith: { first, _ in first }
        )
        return selectedIndices.compactMap { byIndex[$0] }
    }
}
