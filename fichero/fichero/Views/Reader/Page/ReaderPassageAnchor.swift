import Foundation

// MARK: - The passage a search hit is ABOUT (Daniel, 2026-09-03)
//
// "The reader does not land on the matched passage and does not show what
// matched." The plumbing to say WHICH passage already existed end to end —
// the engine anchors every transcript excerpt at the match rather than at
// char 0, and `ContentView.postSearchPassageAnchor(for:)` posts it on the
// `.readerTextSelection` seam — but the reader was not on the other end of
// that seam. `PageContentPane.updateSourceHighlight(_:)` was written to
// receive it and NOTHING ever called it: the pane subscribed to
// `claimFocusState` only, so the anchor was posted into a room the reader was
// not in. The preview's word boxes and the annotation bar listened; the
// reader, the one surface the anchor is for, did not.
//
// Two things had to be true for a landing to work, and only the first is a
// subscription:
//
//  1. The reader must HEAR the anchor. It now does (`PageContentPane`'s
//     `.onReceive`).
//  2. The anchor must survive arriving EARLY. It is posted from
//     `handleDetailDocumentChange`, the moment the selected document changes
//     — before the pane has been handed that document's `page_content`, and
//     sometimes before the pane exists at all. A one-shot notification
//     matched against empty content matches nothing, and `onChange(of:
//     pageContent)` then cleared any highlight the instant the text did
//     arrive. So the anchor is LATCHED as a value and re-applied whenever the
//     content or the document changes, and `ReaderPassageFocus` holds the
//     latest one for a pane that mounts after the post.
//
// A typed value, not the raw `[AnyHashable: Any]` of the notification: the
// userInfo dictionary is the transport, and it stops being untyped at the
// first place that can name the fields.

/// The passage a search hit matched: where it is, and what it says.
struct ReaderPassageAnchor: Equatable, Sendable {
    /// Marks a post as "land the reader HERE", distinguishing it from the
    /// other traffic on `.readerTextSelection`.
    ///
    /// The seam is shared, and the reader is a PUBLISHER on it as well as a
    /// subscriber: `postReaderSelection` announces the user's own text
    /// selection so the preview can light the matching word boxes. Without
    /// this marker, subscribing would make the reader answer its own post —
    /// every drag of the cursor would swap the selectable text view for the
    /// static highlighted rendering, and selecting text would destroy the
    /// selection that caused it.
    static let kindKey = "readerPassageAnchorKind"
    static let searchPassageKind = "searchPassage"

    /// Is this post asking the reader to LAND somewhere, or merely reporting
    /// a selection to whoever else is listening?
    static func isPassageLanding(_ userInfo: [AnyHashable: Any]?) -> Bool {
        (userInfo?[kindKey] as? String) == searchPassageKind
    }

    /// The document the offsets belong to. Offsets are meaningless without
    /// it, so a highlight is only ever applied to THIS document.
    let documentId: String
    /// The matched text itself — the fallback when offsets do not resolve
    /// (a re-transcribed page, an entry rendered from a different source).
    let text: String
    /// UTF-16 offsets of the match within the document's decoded text.
    let charStart: Int?
    let charEnd: Int?

    init(documentId: String, text: String, charStart: Int?, charEnd: Int?) {
        self.documentId = documentId
        self.text = text
        self.charStart = charStart
        self.charEnd = charEnd
    }

    /// Reads the `.readerTextSelection` userInfo. `nil` when the payload
    /// names no document — an anchor that cannot say what it anchors TO is
    /// not an anchor, and applying it to whatever happens to be on screen is
    /// how the reader would highlight the wrong page.
    init?(userInfo: [AnyHashable: Any]?) {
        guard let userInfo,
              let documentId = userInfo["documentId"] as? String,
              !documentId.isEmpty else { return nil }
        self.documentId = documentId
        self.text = (userInfo["text"] as? String)
            ?? (userInfo["excerpt"] as? String)
            ?? (userInfo["claimText"] as? String)
            ?? ""
        self.charStart = Self.intValue(userInfo["charStart"])
        self.charEnd = Self.intValue(userInfo["charEnd"])
    }

    /// The dictionary `PageContentClaimSourceHighlight.match` reads. The
    /// matcher stays the ONE implementation of "where does this land in the
    /// text" — shared with the claim-source path — so a search passage and a
    /// claim source can never disagree about offsets.
    var highlightInfo: [AnyHashable: Any] {
        var info: [AnyHashable: Any] = ["documentId": documentId]
        if !text.isEmpty { info["excerpt"] = text }
        if let charStart { info["charStart"] = charStart }
        if let charEnd { info["charEnd"] = charEnd }
        return info
    }

    /// A phrase from the matched passage that the reader can FIND.
    ///
    /// The reader's Page tab renders the parent's ASSEMBLED transcript
    /// (`kgDocumentId` maps a page to its parent), so this anchor's offsets —
    /// which the engine measured against the PAGE — address the wrong text
    /// there. `scrollToSpan(page, …)` declares a page parameter for exactly
    /// this, but `document_view.html` ignores it and slices
    /// `documentTranscript`, so handing it page offsets would highlight a
    /// confidently wrong passage. Over a manuscript that is worse than none,
    /// because the reader cannot tell.
    ///
    /// So the landing goes through TEXT instead, on the find-in-page path
    /// that already works over an assembled transcript (#4338). The whole
    /// excerpt is a poor needle — it spans line breaks the assembly
    /// re-flows — so this takes a short, whitespace-normalized head of it:
    /// long enough to be the passage rather than a common word, short enough
    /// to survive re-wrapping.
    ///
    /// Empty when there is nothing findable, which the caller reads as "leave
    /// the find bar alone".
    static func findPhrase(from text: String, wordLimit: Int = 8, characterLimit: Int = 80) -> String {
        let words = text
            .split(whereSeparator: \.isWhitespace)
            .prefix(wordLimit)
            .map(String.init)
        guard !words.isEmpty else { return "" }
        var phrase = ""
        for word in words {
            let candidate = phrase.isEmpty ? word : phrase + " " + word
            if candidate.count > characterLimit { break }
            phrase = candidate
        }
        // A single word longer than the cap is still the best needle there is
        // — truncating mid-word would find nothing at all.
        return phrase.isEmpty ? words[0] : phrase
    }

    /// This anchor's findable phrase.
    var findPhrase: String { Self.findPhrase(from: text) }

    private static func intValue(_ value: Any?) -> Int? {
        if let int = value as? Int { return int }
        if let number = value as? NSNumber { return number.intValue }
        return nil
    }
}

/// The most recently posted passage anchor, for a reader that mounts AFTER
/// the post.
///
/// The anchor rides a notification because several surfaces want it at once
/// (the preview's word boxes, the annotation bar, the reader). A notification
/// reaches only the surfaces that already exist, and selecting a search
/// result creates the reader and posts the anchor in the same turn — so the
/// pane read this on appear or it read nothing. Deliberately NOT observable:
/// it is a one-shot handoff read at mount, not a source of truth anything
/// renders from continuously.
@MainActor
enum ReaderPassageFocus {
    private(set) static var latest: ReaderPassageAnchor?

    static func record(_ anchor: ReaderPassageAnchor?) {
        latest = anchor
    }

    /// Forget the anchor once its passage has been shown, so a later,
    /// unrelated mount of the reader does not re-land on a search the user
    /// has moved on from.
    static func consume(documentId: String) {
        if latest?.documentId == documentId { latest = nil }
    }

    /// Test seam: the latch is process-wide, so a test that writes it clears
    /// it rather than leaking into the next one.
    static func reset() { latest = nil }
}
