import Foundation

/// Typing in the Reader (#5154; `source.textedit.*`): the served page posts three messages over
/// `ficheroBridge` -- agreed with the page's lane -- and this turns each into ONE audited action.
///
/// - `lineEdited` {pageId, segmentId, text, basedOn}: a run of keys on one line is a NEW READING
///   (`representation.create`, correcting the reading it was typed over), never an overwrite.
/// - `lineSplit` {pageId, segmentId, offset, text}: Return inside a line is `segment.split` -- the
///   reading cut at the caret, the box cut in proportion along the line's direction (no caret-to-
///   geometry mapping exists anywhere; the person reshapes after). The page sends `lineEdited` first
///   when the line's text changed, so no words are lost.
/// - `lineJoin` {pageId, segmentId, previousSegmentId}: Backspace at a line's start is `segment.merge`
///   into the line before it in reading order.
enum ReaderTextEdit {
    enum Message: Equatable {
        case edited(pageId: String, segmentId: String, text: String, basedOn: String?)
        case split(pageId: String, segmentId: String, offset: Int, text: String)
        case join(pageId: String, segmentId: String, previousSegmentId: String)

        var pageId: String {
            switch self {
            case .edited(let pageId, _, _, _), .split(let pageId, _, _, _), .join(let pageId, _, _): pageId
            }
        }
    }

    /// The page's message, or nil when it is not a whole one of the three.
    static func message(from body: [String: Any]) -> Message? {
        guard let kind = body["kind"] as? String,
              let pageId = body["pageId"] as? String, !pageId.isEmpty,
              let segmentId = body["segmentId"] as? String, !segmentId.isEmpty else { return nil }
        switch kind {
        case "lineEdited":
            guard let text = body["text"] as? String else { return nil }
            return .edited(pageId: pageId, segmentId: segmentId, text: text, basedOn: body["basedOn"] as? String)
        case "lineSplit":
            guard let text = body["text"] as? String, let offset = body["offset"] as? Int else { return nil }
            return .split(pageId: pageId, segmentId: segmentId, offset: offset, text: text)
        case "lineJoin":
            guard let previous = body["previousSegmentId"] as? String, !previous.isEmpty else { return nil }
            return .join(pageId: pageId, segmentId: segmentId, previousSegmentId: previous)
        default:
            return nil
        }
    }

    /// The reading `lineEdited` makes: the whole line's new text, a person's, correcting `basedOn`.
    static func newReading(for message: Message) -> NewReadingParams? {
        guard case .edited(let pageId, let segmentId, let text, let basedOn) = message else { return nil }
        return NewReadingParams(
            documentId: pageId, segmentId: segmentId, kind: "transcription", content: text,
            correctsRepresentationId: basedOn
        )
    }

    /// `lineSplit` as `segment.split`: the caret's UTF-16 offset (what the page's JavaScript counts)
    /// turned into the engine's code-point offset, and the box cut in the same proportion along the
    /// line's direction -- for right-to-left the text's first part is the RIGHT part of the box.
    static func split(_ message: Message, of line: Segment) -> Result<SegmentSplitParams, SegmentEdit.Refusal> {
        guard case .split(_, _, let utf16Offset, let text) = message else { return .failure(.tooFew) }
        guard let version = line.version else { return .failure(.versionUnknown) }
        guard let rect = line.anchor.rect, rect.count == 4 else { return .failure(.tooFew) }
        let length = text.unicodeScalars.count
        let offset = codePointOffset(utf16Offset, in: text)
        guard offset > 0, offset < length else { return .failure(.tooFew) }
        let fraction = Double(offset) / Double(length)
        let (first, second) = cut(rect, at: fraction, direction: line.direction ?? "ltr")
        let anchor = { (box: [Double]) in
            SegmentAnchorParams(
                documentId: line.anchor.documentId, pageId: line.anchor.pageId, renditionId: line.anchor.renditionId,
                space: line.anchor.space, rect: box, polygon: nil, rotation: line.anchor.rotation,
                granularity: line.anchor.granularity
            )
        }
        return .success(SegmentSplitParams(
            segmentId: line.id,
            parts: [
                SegmentSplitPartParams(anchor: anchor(first), readingSpan: [0, offset]),
                SegmentSplitPartParams(anchor: anchor(second), readingSpan: [offset, length])
            ],
            expectedVersion: version
        ))
    }

    /// `lineJoin` as `segment.merge`: this line into the one before it, which is kept.
    static func join(_ message: Message, segments: [Segment]) -> Result<SegmentEdit.Call, SegmentEdit.Refusal> {
        guard case .join(_, let segmentId, let previousId) = message,
              let previous = segments.first(where: { $0.id == previousId }),
              let line = segments.first(where: { $0.id == segmentId }) else { return .failure(.tooFew) }
        return SegmentEdit.join([previous, line])
    }

    /// The app's answer to the page after each message: `window.fichero.lineCommitted({kind,
    /// segmentId, ok, detail})`, optional-chained so a page without it ignores it. On ok the page
    /// re-reads its text (the page's own business, keeping its place).
    static func committedScript(kind: String, segmentId: String, succeeded: Bool, detail: String) -> String {
        let payload: [String: Any] = ["kind": kind, "segmentId": segmentId, "ok": succeeded, "detail": detail]
        let data = (try? JSONSerialization.data(withJSONObject: payload)) ?? Data()
        let json = String(bytes: data, encoding: .utf8) ?? "{}"
        return "window.fichero?.lineCommitted?.(\(json));"
    }

    /// A JavaScript (UTF-16) offset into `text` as a Unicode-scalar offset -- what the engine's Python
    /// strings count. They differ past any character outside the Basic Multilingual Plane.
    static func codePointOffset(_ utf16Offset: Int, in text: String) -> Int {
        let utf16 = text.utf16
        let clamped = min(max(utf16Offset, 0), utf16.count)
        let index = utf16.index(utf16.startIndex, offsetBy: clamped)
        let scalarIndex = index.samePosition(in: text.unicodeScalars) ?? text.unicodeScalars.endIndex
        return text.unicodeScalars.distance(from: text.unicodeScalars.startIndex, to: scalarIndex)
    }

    /// The two boxes a line is cut into, in reading order: along the width for horizontal writing
    /// (the right part first for right-to-left), along the height for vertical.
    static func cut(_ rect: [Double], at fraction: Double, direction: String) -> ([Double], [Double]) {
        let (left, top, width, height) = (rect[0], rect[1], rect[2], rect[3])
        switch direction {
        case "ttb":
            return ([left, top, width, height * fraction], [left, top + height * fraction, width, height * (1 - fraction)])
        case "btt":
            let lower = height * fraction
            return ([left, top + height - lower, width, lower], [left, top, width, height - lower])
        case "rtl":
            let right = width * fraction
            return ([left + width - right, top, right, height], [left, top, width - right, height])
        default:
            return ([left, top, width * fraction, height], [left + width * fraction, top, width * (1 - fraction), height])
        }
    }
}

/// `representation.create` for a reading typed in the Reader.
struct NewReadingParams: Encodable, Equatable {
    let documentId: String
    let segmentId: String
    let kind: String
    let content: String
    let correctsRepresentationId: String?

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id", segmentId = "segment_id", kind, content
        case correctsRepresentationId = "corrects_representation_id"
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(documentId, forKey: .documentId)
        try container.encode(segmentId, forKey: .segmentId)
        try container.encode(kind, forKey: .kind)
        try container.encode(content, forKey: .content)
        try container.encodeIfPresent(correctsRepresentationId, forKey: .correctsRepresentationId)
    }
}

/// `segment.split`.
struct SegmentSplitParams: Encodable, Equatable {
    let segmentId: String
    let parts: [SegmentSplitPartParams]
    let expectedVersion: Int

    enum CodingKeys: String, CodingKey {
        case segmentId = "segment_id", parts, expectedVersion = "expected_version"
    }
}

struct SegmentSplitPartParams: Encodable, Equatable {
    let anchor: SegmentAnchorParams
    let readingSpan: [Int]

    enum CodingKeys: String, CodingKey { case anchor, readingSpan = "reading_span" }
}
