#if os(macOS)
import OSLog
import SwiftUI

/// The selection verbs of the segment editor (#6582): select same kind or the next doubtful one,
/// drop and reassign lines, and the per-word, simplify and baseline tools -- each one audited
/// segment action through `runSegmentEdit`.
extension ZoomableImagePreview {
    /// ⌘⇧A: every box on the page whose segment is of a kind the selection holds (`segment-editor.select-shift-toggles`).
    /// Selecting is not an action: nothing is sent.
    func selectSameKind() {
        guard let artifactId = ocrGeometrySelectionScope, let all = ocrGeometry?.boxes, let documentId,
              let store = segmentEditStore else { return }
        let kindOf = Dictionary(
            store.segments(documentId: documentId).map { ($0.id, $0.kind) }, uniquingKeysWith: { first, _ in first }
        )
        let indices = SegmentSelectionGestures.sameKind(
            as: regionSelection.resolvedIndices(in: all), kinds: all.map { $0.segmentId.flatMap { kindOf[$0] } }
        )
        guard !indices.isEmpty else { return }
        regionSelection.selectAll(indices, artifactId: artifactId, documentId: documentId, in: all)
    }

    /// Next Doubtful (`segment-editor.low-confidence-lens`): select the next line the engine is least sure of, from
    /// the top again after the last. Selecting is not an action. The page says so when nothing is doubtful.
    func selectNextDoubtful() {
        guard let documentId, let segmentService, let artifactId = ocrGeometrySelectionScope else { return }
        let current = selectedSegments(documentId).first?.id
        Task {
            do {
                let doubtful = try await segmentService.doubtfulLines(documentId: documentId)
                guard let next = SegmentSelectionGestures.nextDoubtful(after: current, in: doubtful),
                      let all = ocrGeometry?.boxes, let index = all.firstIndex(where: { $0.segmentId == next }) else {
                    windowState?.segmentNotice = "Nothing on this page is doubtful"
                    return
                }
                regionSelection.select(index, artifactId: artifactId, documentId: documentId, in: all)
            } catch {
                Self.logger.error("Next Doubtful failed: \(error.localizedDescription, privacy: .public)")
            }
        }
    }

    /// What letting the selection go at `point` does (`segment-editor.reassign-by-drag`): judged against the segments of
    /// the selection's own pass.
    func dropOfSelection(at point: [Double], command: Bool) -> SegmentMover.Drop {
        guard let documentId, let store = segmentEditStore else { return .move }
        let dragged = selectedSegments(documentId)
        let onPass = store.segments(documentId: documentId).filter { $0.passId == dragged.first?.passId }
        return SegmentMover.drop(of: dragged, at: point, among: onPass, commandHeld: command)
    }

    /// REASSIGN the selected lines to a region (nil: the page) by a drag: one `segment.reparent`, which also places them
    /// in every order by page position, one ⌘Z.
    func reassignSelectedLines(into parent: String?) {
        guard let documentId else { return }
        runSegmentEdit(
            SegmentEdit.reparent(selectedSegments(documentId), into: parent), documentId: documentId, name: SegmentMover.actionName
        )
    }

    /// CUT CHARACTERS in the selected words (`segment-editor.cut-characters`): one ⌘Z.
    func cutCharactersInSelectedWords() {
        guard let documentId else { return }
        runSegmentEdit(SegmentEdit.cutCharacters(selectedSegments(documentId)), documentId: documentId, name: "Cut Characters")
    }

    /// SIMPLIFY the selected segments' outlines and baselines (`segment-editor.vertices`, ⌥⌘S): one ⌘Z.
    func simplifySelectedSegments(tolerance: Double = SegmentEdit.simplifyTolerance) {
        guard let documentId else { return }
        runSegmentEdit(
            SegmentEdit.simplify(selectedSegments(documentId), tolerance: tolerance), documentId: documentId, name: "Simplify Outline"
        )
    }

    /// The Simplify slider moved: what the engine would make of the selection at `tolerance`, drawn over the page and
    /// written nowhere. A slower answer for an older tolerance is dropped.
    func previewSimplify(_ tolerance: Double?) {
        guard let windowState else { return }
        guard let tolerance, let documentId, let segmentService else { windowState.simplifyPreview = []; return }
        let ids = selectedSegments(documentId).map(\.id)
        guard !ids.isEmpty else { windowState.simplifyPreview = []; return }
        Task {
            do {
                let paths = try await segmentService.simplifyPreview(documentId: documentId, segmentIds: ids, tolerance: tolerance)
                if windowState.simplifyTolerance == tolerance { windowState.simplifyPreview = paths }
            } catch {
                Self.logger.error("Simplify preview failed: \(error.localizedDescription, privacy: .public)")
            }
        }
    }

    /// CUT WORDS on the selected lines (`segment-editor.cut-words-from-positions`, ⇧⌘W): one ⌘Z; the page says how many
    /// lines could not be cut.
    func cutWordsOnSelectedLines() {
        guard let documentId else { return }
        runSegmentEdit(SegmentEdit.cutWords(selectedSegments(documentId)), documentId: documentId, name: "Cut Words") { result in
            let pairs = result.resultIdPairs["joinable"] ?? []
            windowState?.brokenWords = pairs
            windowState?.segmentNotice = SegmentEdit.brokenWordsNotice(pairs.count) ?? SegmentEdit.cutWordsNotice(
                made: result.resultListCounts["segment_ids"] ?? 0, leftAlone: result.resultListCounts["left_alone"] ?? 0
            )
        }
    }

    /// JOIN BROKEN WORDS: each word the last Cut Words found broken at a line's end becomes one word with both pieces'
    /// shapes (`segment-editor.edge.word-across-lines`), one merge (and one ⌘Z) per word.
    func joinBrokenWords() {
        guard let windowState, let documentId, let store = segmentEditStore else { return }
        let byId = Dictionary(store.segments(documentId: documentId).map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let pairs = windowState.brokenWords
        windowState.brokenWords = []
        for pair in pairs {
            guard pair.count == 2, let first = byId[pair[0]], let second = byId[pair[1]] else { continue }
            runSegmentEdit(SegmentEdit.joinBrokenWord(first, second), documentId: documentId, name: "Join Broken Word")
        }
    }

    /// ADD BASELINE to the selected lines that have none (`segment-editor.edge.no-baseline`): one ⌘Z.
    func addBaselineToSelectedLines() {
        guard let documentId else { return }
        runSegmentEdit(SegmentEdit.addBaseline(selectedSegments(documentId)), documentId: documentId, name: "Add Baseline")
    }

    /// SPLIT the one selected line where it was last clicked (`segment-editor.split-at-a-point`, ⌘⇧K).
    func splitSelectedLineAtLastPoint() {
        guard let documentId, let line = selectedSegments(documentId).first, let pressed = pointerFeed.latest?.point else { return }
        runSegmentEdit(
            SegmentEdit.splitAtPoint(line, at: [Double(pressed.x), Double(pressed.y)]), documentId: documentId, name: "Split Line"
        )
    }

    /// Whether every selected segment has a baseline, so Redraw can act on the selection.
    var selectionHasBaselines: Bool {
        guard let documentId else { return false }
        let segments = selectedSegments(documentId)
        return !segments.isEmpty && segments.allSatisfy(SegmentEdit.hasBaseline)
    }

    /// The Segment menu on the selection (#5157), on any page whose boxes are segments: one audited
    /// `segment.update_many`, ⌘Z.
    func setSelectedSegments(_ attribute: SegmentEdit.Attribute) {
        guard let documentId else { return }
        runSegmentEdit(
            SegmentEdit.set(attribute, on: selectedSegments(documentId)), documentId: documentId, name: "Set Segment"
        )
    }

    /// The selection as segments, in the order picked, through the Inspector's one resolution.
    func selectedSegments(_ documentId: String) -> [Segment] {
        guard let store = segmentEditStore else { return [] }
        let ids = InspectorPath.selectedSegmentIds(selection: regionSelection, documentId: documentId, store: store)
        let byId = Dictionary(
            store.segments(documentId: documentId).map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first }
        )
        return ids.compactMap { byId[$0] }
    }
}
#endif
