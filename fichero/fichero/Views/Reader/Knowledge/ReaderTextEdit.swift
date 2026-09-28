import Foundation

/// Typing in the Reader (#5154; `source.textedit.*`): the served page posts three messages over
/// `ficheroBridge` -- the shape the lead ruled, the page's half in `document_view.html` -- and this turns
/// each into ONE audited action.
///
/// - `readingEdit` {pageId, segmentId, text, previous, basedOn}: a run of keys on one line is a NEW
///   READING (`representation.create`, correcting `basedOn`, the reading it was typed over), never an
///   overwrite. `basedOn` is null when the line's text came from its words: there is no one reading to
///   correct. `previous` is kept for the stale check (#5001), not sent.
/// - `lineSplit` {pageId, segmentId, offset}: Return inside a line is `segment.split {at_offset}`. The
///   ENGINE cuts the reading and the box at that character, along the line's direction (`cut:
///   estimated`) -- one implementation of the cut, not one here too. The app's job is the offset: the
///   page counts UTF-16 units, the engine counts code points.
/// - `lineJoin` {pageId, segmentId, intoSegmentId}: Backspace at a line's start is `segment.merge` into
///   the line before it in the page's text order, which is kept.
enum ReaderTextEdit {
    enum Message: Equatable {
        case edited(pageId: String, segmentId: String, text: String, basedOn: String?)
        case split(pageId: String, segmentId: String, offset: Int)
        case join(pageId: String, segmentId: String, intoSegmentId: String)

        var pageId: String {
            switch self {
            case .edited(let pageId, _, _, _), .split(let pageId, _, _), .join(let pageId, _, _): pageId
            }
        }

        var segmentId: String {
            switch self {
            case .edited(_, let segmentId, _, _), .split(_, let segmentId, _), .join(_, let segmentId, _): segmentId
            }
        }
    }

    /// The page's message, or nil when it is not a whole one of the three.
    static func message(from body: [String: Any]) -> Message? {
        guard let kind = body["kind"] as? String,
              let pageId = body["pageId"] as? String, !pageId.isEmpty,
              let segmentId = body["segmentId"] as? String, !segmentId.isEmpty else { return nil }
        switch kind {
        case "readingEdit":
            guard let text = body["text"] as? String else { return nil }
            return .edited(pageId: pageId, segmentId: segmentId, text: text, basedOn: body["basedOn"] as? String)
        case "lineSplit":
            guard let offset = body["offset"] as? Int else { return nil }
            return .split(pageId: pageId, segmentId: segmentId, offset: offset)
        case "lineJoin":
            guard let into = body["intoSegmentId"] as? String, !into.isEmpty else { return nil }
            return .join(pageId: pageId, segmentId: segmentId, intoSegmentId: into)
        default:
            return nil
        }
    }

    /// The reading `readingEdit` makes: the whole line's new text, a person's, correcting `basedOn`.
    static func newReading(for message: Message) -> NewReadingParams? {
        guard case .edited(let pageId, let segmentId, let text, let basedOn) = message else { return nil }
        return NewReadingParams(
            documentId: pageId, segmentId: segmentId, kind: "transcription", content: text,
            correctsRepresentationId: basedOn
        )
    }

    /// `lineSplit` as `segment.split {at_offset}`: the caret's UTF-16 offset into the line's text (what
    /// the page's JavaScript counts) as the engine's code-point offset, with the version the list said.
    /// No geometry: the engine cuts. A line with no text of its own to count in is refused here, as the
    /// engine would.
    ///
    /// `shownText` is the line's counting reading -- what the page shows, so what its offset counts in;
    /// the box's own text stands in when no reading counts.
    static func split(
        _ message: Message, of line: Segment, shownText: String?
    ) -> Result<SegmentSplitRequest, SegmentEdit.Refusal> {
        guard case .split(_, _, let utf16Offset) = message else { return .failure(.tooFew) }
        guard let version = line.version else { return .failure(.versionUnknown) }
        guard let text = shownText ?? line.text, !text.isEmpty else { return .failure(.tooFew) }
        return .success(SegmentSplitRequest(
            segmentId: line.id, atOffset: codePointOffset(utf16Offset, in: text), expectedVersion: version
        ))
    }

    /// `lineJoin` as `segment.merge`: this line into `intoSegmentId`, which is kept.
    static func join(_ message: Message, segments: [Segment]) -> Result<SegmentEdit.Call, SegmentEdit.Refusal> {
        guard case .join(_, let segmentId, let intoId) = message,
              let into = segments.first(where: { $0.id == intoId }),
              let line = segments.first(where: { $0.id == segmentId }) else { return .failure(.tooFew) }
        return SegmentEdit.join([into, line])
    }

    /// The app's answer to the page after each message: `window.fichero.lineCommitted({pageId,
    /// segmentId, ok, reason?})`, optional-chained so a page without it ignores it. The app then asks
    /// the page to re-read itself (`refreshPage`).
    static func committedScript(pageId: String, segmentId: String, reason: String?) -> String {
        var payload: [String: Any] = ["pageId": pageId, "segmentId": segmentId, "ok": reason == nil]
        if let reason { payload["reason"] = reason }
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

/// `segment.split` from the Reader: where to cut, in the engine's code points; the engine does the rest.
/// (Named apart from the contract's `SegmentSplitParams`, whose `parts` the Inspector's split uses.)
struct SegmentSplitRequest: Encodable, Equatable {
    let segmentId: String
    let atOffset: Int
    let expectedVersion: Int

    enum CodingKeys: String, CodingKey {
        case segmentId = "segment_id", atOffset = "at_offset", expectedVersion = "expected_version"
    }
}
