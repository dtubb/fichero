import FicheroAPIClient
import Foundation

/// The compare view's model (`wide.compare.three-modes`, `.per-line-diff`, `.empty-and-error-states`, #5900): modes, rows and
/// states over the engine's one compare answer (`GET /api/pages/{id}/compare-readers`). Pure: no view, no network; the engine
/// does the matching and the agreement, this only chooses what to show.
struct CompareViewModel: Equatable {
    enum Mode: Equatable, CaseIterable {
        case sideBySide, overlay, wipe
    }

    enum Platform: Equatable {
        case mac, iPad, iPhone

        /// The narrow screen is the iPhone's (a compact width); anything wider opens side by side.
        static func of(compactWidth: Bool) -> Platform {
            #if os(macOS)
            .mac
            #else
            compactWidth ? .iPhone : .iPad
            #endif
        }

    }

    /// Side by side is the Mac's and iPad's default, Overlay the iPhone's (one picture fits the narrow screen).
    static func defaultMode(for platform: Platform) -> Mode { platform == .iPhone ? .overlay : .sideBySide }

    let readers: [Components.Schemas.CompareReader]
    let lines: [Components.Schemas.CompareLine]
    var mode: Mode
    /// Reader ids the person switched off in Overlay's legend.
    private(set) var hidden: Set<String> = []
    /// Show only the lines whose texts differ.
    var onlyDiffering = false
    /// Wipe's handle, 0 (all B) to 1 (all A).
    private(set) var handle = 0.5

    init(answer: Components.Schemas.CompareReadersResponse, platform: Platform) {
        readers = answer.readers
        lines = answer.lines
        mode = Self.defaultMode(for: platform)
    }

    // MARK: Overlay and Wipe

    /// Overlay's legend toggle for one reader.
    mutating func toggle(reader id: String) {
        if hidden.contains(id) { hidden.remove(id) } else { hidden.insert(id) }
    }

    /// The readers whose boxes Overlay draws, in the engine's order.
    var drawn: [Components.Schemas.CompareReader] { readers.filter { !hidden.contains($0.id) } }

    /// Move Wipe's handle (a drag or an arrow key), kept inside the picture.
    mutating func moveHandle(to position: Double) { handle = min(1, max(0, position)) }

    /// Wipe compares two readers: A left of the handle, B right of it; the first two readers unless there is one.
    var wipePair: (a: Components.Schemas.CompareReader, b: Components.Schemas.CompareReader)? {
        readers.count >= 2 ? (readers[0], readers[1]) : nil
    }

    /// How many characters of a line's text show on A's side at the handle: the texts wipe with the picture.
    func charactersOnA(of text: String) -> Int { Int((Double(text.count) * handle).rounded(.down)) }

    // MARK: Rows

    /// One line under the pictures: its order, its text per reader in the readers' order (nil where a reader gave none), whether
    /// the readers differ, and the words that carry a disagreement.
    struct Row: Equatable, Identifiable {
        let id: Int
        let texts: [String?]
        let differs: Bool
        let differingWords: [String]
        let pickedByPerson: Bool
        let countingReaderId: String?
        /// A try's lines have no segment yet (`segment_id` null): there is nothing to make count, so no Use This.
        let canPick: Bool
    }

    /// What Use This sends for one reading of one line: the line's segment, the reading chosen, and the reading that counted when
    /// the person looked, as a representation id (the engine compares representation ids, never reader ids).
    struct Pick: Equatable {
        let segmentId: String
        let representationId: String
        let expectedCountingId: String?
    }

    func pick(readerId: String, onLine order: Int) -> Pick? {
        guard let line = lines.first(where: { $0.order == order }), let segment = line.segmentId,
              let reading = line.readings.first(where: { $0.readerId == readerId }),
              let representation = reading.representationId else { return nil }
        let counting = line.readings.first { $0.readerId == line.countingReaderId }?.representationId
        return Pick(segmentId: segment, representationId: representation, expectedCountingId: counting)
    }

    /// A line's box and the size of the pixels it is in, for the picture shown. The picture is the page's saved edits when it has
    /// any (`frame.read_from == "edited"`), else the photograph. On an edited page the boxes are `frame_bbox` in the edited
    /// image's size, and when the lines' place on it is not known (`followed` false) no box is drawn; otherwise the line's `bbox`
    /// in the photograph's pixels.
    static func drawnBox(boxes: (bbox: [Double]?, frame: [Double]?), readFrom: String?, followed: Bool,
                         frameSize: (width: Int, height: Int)?, photograph: (width: Int, height: Int)?)
        -> (box: [Double], image: (width: Int, height: Int))? {
        if readFrom == "edited" {
            guard followed, let box = boxes.frame, let frameSize else { return nil }
            return (box, frameSize)
        }
        guard let bbox = boxes.bbox, let photograph else { return nil }
        return (bbox, photograph)
    }

    /// Said under the picture when the page has saved edits whose lines' place is not known: no box is drawn, and why.
    static func noBoxesNote(readFrom: String?, followed: Bool) -> String? {
        readFrom == "edited" && !followed
            ? "The lines' place on this edited page is not known, so no boxes are drawn." : nil
    }

    /// `drawnBox` over one of the engine's lines and its answer's frame.
    static func drawnBox(of line: Components.Schemas.CompareLine, frame: Components.Schemas.CompareFrame?,
                         photograph: (width: Int, height: Int)?) -> (box: [Double], image: (width: Int, height: Int))? {
        var size: (width: Int, height: Int)?
        if let width = frame?.imageWidth, let height = frame?.imageHeight { size = (width, height) }
        return drawnBox(boxes: (line.bbox, line.frameBbox), readFrom: frame?.readFrom.rawValue,
                        followed: frame?.followed ?? false, frameSize: size, photograph: photograph)
    }

    /// A box from the engine, in the page image's pixels, scaled onto a canvas that shows the whole image.
    static func boxRect(_ box: [Double], image: (width: Int, height: Int)?, canvas: CGSize) -> CGRect? {
        guard box.count == 4, let image, image.width > 0, image.height > 0 else { return nil }
        let across = canvas.width / Double(image.width), down = canvas.height / Double(image.height)
        return CGRect(x: box[0] * across, y: box[1] * down, width: box[2] * across, height: box[3] * down)
    }

    var rows: [Row] {
        lines.filter { !onlyDiffering || $0.differs }.map { line in
            let byReader = Dictionary(line.readings.map { ($0.readerId, $0.text) }, uniquingKeysWith: { first, _ in first })
            return Row(id: line.order, texts: readers.map { byReader[$0.id] }, differs: line.differs,
                       differingWords: line.words.filter { !$0.variants.isEmpty }.map(\.text),
                       pickedByPerson: line.pickedByPerson, countingReaderId: line.countingReaderId,
                       canPick: line.segmentId != nil)
        }
    }

    // MARK: States

    /// The engine-sentence for a view with nothing to compare: never an empty picture. Nil when there is something to compare.
    var emptyState: String? {
        if readers.isEmpty { return "Nothing has read this page yet." }
        if readers.count == 1 { return "Only one reader has read this page: there is nothing to compare it with yet." }
        if lines.isEmpty { return "No reader has lines on this page yet: the readers have not read it line by line." }
        return nil
    }

    /// A candidate that did not read this page says why in its own words (its measure's `not_measured`).
    func notReadBecause(reader id: String) -> String? {
        guard let reader = readers.first(where: { $0.id == id }) else { return nil }
        let reads = lines.contains { line in line.readings.contains { $0.readerId == id } }
        return reads ? nil : (reader.measure?.notMeasured ?? "\(reader.label) did not read this page.")
    }
}
