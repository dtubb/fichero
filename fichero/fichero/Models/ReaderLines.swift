import CoreText
import Foundation
import Observation
import SwiftUI

/// The Reader's Lines mode (#5414, `reader.lines.*`) and the Preview's double-click popover
/// (`preview.segment.double-click-popover`), which is one row of it. The decisions live here, apart
/// from the views, so a test can make them against the real `SegmentStore`.
enum ReaderLines {
    /// The page's lines, down the page: the WORKING pass's line segments (`SegmentStore.workingSegments`,
    /// #5467), in the engine's order -- the order the Segments list and the Preview read the pass in.
    @MainActor
    static func lines(documentId: String, store: SegmentStore) -> [Segment] {
        store.workingSegments(documentId: documentId).filter { $0.kind.lowercased() == "line" }
    }

    /// What a click on a line's picture makes the selection, Finder style: a plain click is that line alone; ⌘ adds
    /// it or takes it out; ⇧ takes the run from the last picked line to it, down the page's order (the whole run is
    /// added to what is held with ⌘⇧, replaces it with ⇧ alone). An id off the page changes nothing.
    static func picked(
        _ id: String, held: [String], order: [String], command: Bool, shift: Bool
    ) -> [String] {
        guard let place = order.firstIndex(of: id) else { return held }
        if shift, let anchorId = held.last, let anchor = order.firstIndex(of: anchorId) {
            let run = Array(order[min(anchor, place)...max(anchor, place)])
            return command ? held + run.filter { !held.contains($0) } : run
        }
        if command { return held.contains(id) ? held.filter { $0 != id } : held + [id] }
        return [id]
    }

    /// The lines the selection lights: a selected line, and the line a selected word sits in. The Lines
    /// mode follows the focused Preview's selection as the other Reader modes do.
    static func shown(_ selectedIds: [String], among lines: [Segment], segments: [Segment]) -> Set<String> {
        let lineIds = Set(lines.map(\.id))
        let parentById = Dictionary(
            segments.map { ($0.id, $0.parentSegmentId) }, uniquingKeysWith: { first, _ in first }
        )
        var shown: Set<String> = []
        for id in selectedIds {
            var cursor: String? = id
            var hops = 0
            while let current = cursor, hops < 16 {
                if lineIds.contains(current) { shown.insert(current); break }
                cursor = parentById[current] ?? nil
                hops += 1
            }
        }
        return shown
    }

    /// Where a line's picture stands against its words.
    enum Arrangement: Equatable {
        /// Picture above, words below: a line written across.
        case above
        /// Picture beside the words' column: a line written top to bottom (vertical Han, Mongolian).
        case beside
    }

    /// From the line's resolved direction (the engine's cascade, #5411), read as the Inspector's editor
    /// reads it, so the row and the Inspector agree about which lines are vertical.
    static func arrangement(direction: String?) -> Arrangement {
        InspectorReadingEdit.layout(direction: direction) == .vertical ? .beside : .above
    }

    /// The picture's long side asked of the engine (`GET /api/segments/{id}/picture?size=`): large enough
    /// that zooming in does not blur the hand, well under the engine's 8192 cap.
    static let pictureSize = 1600

    /// How large the Preview popover draws its row: the hand shown large.
    static let popoverZoom = 1.6

    /// Sizes at one zoom. Zoom scales the picture and the words together, and the picture is always the
    /// larger, so the hand can be read against its transcription.
    struct Metrics: Equatable {
        /// How much larger the picture is drawn than the words: its extent across the line (a horizontal
        /// line's height, a vertical line's width) is this many times the words' point size.
        static let pictureToText: CGFloat = 3

        let fontSize: CGFloat

        init(zoom: Double, bodySize: CGFloat = ReaderLines.bodyPointSize) {
            fontSize = bodySize * CGFloat(zoom)
        }

        var pictureExtent: CGFloat { fontSize * Self.pictureToText }
    }

    /// The body text style's point size on this platform: the size the words take at 100%.
    static var bodyPointSize: CGFloat {
        CTFontGetSize(BundledFonts.ctFont(base: BundledFonts.systemDescriptor(.body), size: 0, cascade: []))
    }
}

/// A double-clicked box that opens the segment popover (`preview.segment.double-click-popover`, #5414):
/// a line, word or region box naming a stored segment. A provisional (`legacy:`) id has nowhere to save a
/// reading, and a box with no segment has no reading, so those keep the double-click's old open/zoom.
struct SegmentPopoverTarget: Identifiable, Equatable {
    let id: String
    let bbox: [Double]

    static let kinds: Set<String> = ["line", "word", "region"]

    static func target(for box: OCRGeometryBox) -> SegmentPopoverTarget? {
        guard let segmentId = box.segmentId, !segmentId.hasPrefix("legacy:"),
              kinds.contains(box.level.lowercased()) else { return nil }
        return SegmentPopoverTarget(id: segmentId, bbox: box.bbox)
    }
}

/// One line's row: its picture and its reading, and the person's correction of it. Saved through
/// `InspectorReadingEdit.save` -- the Inspector's Edit… action, one path -- as a person's reading.
@MainActor
@Observable
final class ReaderLineEditor {
    let segment: Segment
    /// The line cut from the page by the engine (PNG bytes; the row draws them); nil until fetched, or
    /// when there is no page image.
    private(set) var picture: Data?
    /// The reading that counts now, which a correction corrects; nil when none counts yet.
    private(set) var reading: InspectorText.Reading?
    /// The line's label and the reading it shows (#6455): where none counts, the newest person's reading, never an unlabelled text.
    private(set) var label: ShownReadingLabel?
    /// The line's readings as a tree, for its disclosure triangle (#6492).
    private(set) var versions: [ReadingTree] = []
    /// The words in the field.
    var draft: String
    /// Why the last save did not land.
    private(set) var note: String?

    init(segment: Segment) {
        self.segment = segment
        draft = segment.text ?? ""
    }

    /// The words shown before any typing: the counting reading, else the segment's own text.
    var shownWords: String { label?.shown.content ?? reading?.content ?? segment.text ?? "" }

    var isChanged: Bool {
        draft.trimmingCharacters(in: .whitespacesAndNewlines) != shownWords.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// The picture and the counting reading, through the same services the Segments grid and the
    /// Inspector use.
    func load(_ service: SegmentService) async {
        let untouched = draft == shownWords
        let readings = try? await service.readings(segmentId: segment.id)
        reading = readings?.countingReading(ofKind: "transcription")
        label = ShownReadingLabel(readings)
        versions = ReadingTree.build(readings?.readings ?? [])
        if untouched { draft = shownWords }  // words typed while it loaded are kept
        if picture == nil {
            picture = try? await SegmentPictureService(client: service.client)
                .picture(segmentId: segment.id, size: ReaderLines.pictureSize)
        }
    }

    /// Save the words as a person's reading -- the Inspector's own save -- then re-read what counts, so
    /// the next correction corrects this one.
    func save(runner: ReaderTextEditRunner, service: SegmentService) async {
        guard isChanged else { return }
        if let problem = await InspectorReadingEdit.save(
            draft, documentId: segment.documentId, segmentId: segment.id, editing: reading, runner: runner
        ) {
            note = InspectorReadingEdit.note(for: problem)
            if problem == ReaderTextEditRunner.staleProblem { await reread(service) }
            return
        }
        note = nil
        await reread(service)
    }

    /// Put the words back as they were.
    func revert() {
        draft = shownWords
        note = nil
    }

    private func reread(_ service: SegmentService) async {
        let readings = try? await service.readings(segmentId: segment.id)
        reading = readings?.countingReading(ofKind: "transcription")
        label = ShownReadingLabel(readings)
        versions = ReadingTree.build(readings?.readings ?? [])
        draft = shownWords
    }
}
