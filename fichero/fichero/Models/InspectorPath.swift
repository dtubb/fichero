import FicheroAPIClient
import Foundation

/// What the Inspector inspects, as segments, and the path head above it (ruled 2026-09-27,
/// `build-notes-inspector.md`): Source › page › block › line › word, where clicking a crumb inspects
/// that level. Pure, like `ReadingOrderMove`: the rules live where a test can reach them.
struct InspectorPath: Equatable {
    struct Crumb: Equatable, Identifiable {
        let segmentId: String
        let kind: String
        /// "Line", "Block" -- the level, which is what a crumb names; the words are the Text section's.
        /// A table cell is named by its place: "Cell, Row 3, Column 1" (#5168).
        let label: String
        var id: String { segmentId }
    }

    /// What a segment is called where its level is named -- the path head, the Segments pane's rows:
    /// its kind, or for a table cell its place in the table (#5168).
    static func name(of segment: Segment) -> String {
        guard let place = cellPlace(segment.cell) else { return segment.kind.capitalized }
        return "Cell, " + place
    }

    /// A cell's place counted from 1, as people count ("Row 3, Column 1"; "Rows 3–4, Column 1" for a
    /// span). The file counts from 0 (PAGE's `TableCell`), so row 2 there is Row 3 here.
    static func cellPlace(_ cell: Components.Schemas.TableCellPlace?) -> String? {
        guard let cell else { return nil }
        let span = { (name: String, start: Int, count: Int) -> String in
            count > 1 ? "\(name)s \(start + 1)–\(start + count)" : "\(name) \(start + 1)"
        }
        return span("Row", cell.row, cell.rowSpan ?? 1) + ", " + span("Column", cell.column, cell.columnSpan ?? 1)
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
        return InspectorPath(crumbs: chain.reversed().map { Crumb(segmentId: $0.id, kind: $0.kind, label: name(of: $0)) })
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

    /// REVEAL (#5424, `reader.order.reveal-line-in-preview`): select `segmentIds` exactly as `select`
    /// does, then ask the pane owning `selection` to scroll and zoom to their boxes (their union). The
    /// ONE reveal action: the Order tab's and the Order pane's double-click and the Reader's line click
    /// all call this, so they cannot disagree about the box or the rect. Answers the ids selected.
    @MainActor
    @discardableResult
    static func reveal(
        segmentIds: [String], into selection: RegionSelection, documentId: String, store: SegmentStore
    ) -> [String] {
        let picked = select(segmentIds: segmentIds, into: selection, documentId: documentId, store: store)
        guard !picked.isEmpty, let boxes = SegmentDisplay.selected(for: documentId, store: store)?.geometry.boxes,
              let rect = union(selection.resolvedIndices(in: boxes).map { boxes[$0].bbox })
        else { return picked }
        selection.reveal(rect)
        return picked
    }

    /// A selection the Inspector's OWN Order list wrote (#4981, #5424): the box lights in the Preview,
    /// but the Inspector stays on what it was showing (`shown`; empty is the page), so the list being
    /// clicked does not vanish under the second click of a double-click. Any other selection -- a
    /// Preview click, the Order pane, the Reader -- is followed, as #5155 rules.
    struct Hold: Equatable {
        let wrote: [String]
        let shown: [String]

        /// What the Inspector inspects, given the focused pane's selection.
        static func inspected(_ selected: [String], held: Hold?) -> [String] {
            guard let held, held.wrote == selected else { return selected }
            return held.shown
        }
    }

    /// The smallest normalized `[x, y, w, h]` holding every rect; nil when none is a whole rect.
    static func union(_ rects: [[Double]]) -> [Double]? {
        let whole = rects.filter { $0.count >= 4 }
        guard let minX = whole.map({ $0[0] }).min(), let minY = whole.map({ $0[1] }).min(),
              let maxX = whole.map({ $0[0] + $0[2] }).max(), let maxY = whole.map({ $0[1] + $0[3] }).max()
        else { return nil }
        return [minX, minY, maxX - minX, maxY - minY]
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
