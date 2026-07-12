@testable import Fichero
import SwiftUI
import XCTest
#if canImport(AppKit)
import AppKit
#endif

/// Tests for `ArtifactRichTextCodec` — the encode/decode boundary the inspector
/// rich-text editor (`ArtifactPanel`'s `TextEditor(text:)`) uses to persist
/// content.
///
/// Regression cover for #2494 (#2416): the macOS 26 format ribbon records bold /
/// italic / underline / strikethrough as SwiftUI *semantic* attributes
/// (`inlinePresentationIntent` + the `SwiftUI.*` scope keys). A plain
/// `NSAttributedString(attr)` bridge keeps those as opaque keys that RTF can't
/// serialize, so formatting was silently dropped on save — bold typed in the
/// inspector round-tripped back as plain text. `encodeAttributed` now folds the
/// semantic attributes onto concrete AppKit attributes before RTF encoding.
@MainActor
final class ArtifactRichTextCodecTests: XCTestCase {

    // MARK: - Formatting round-trip (#2494)

    /// THE bug: bold applied via the native ribbon (`inlinePresentationIntent`)
    /// must survive encode (RTF) → decode. Before the fix the decoded "bold"
    /// word carried no bold font trait.
    func testBoldSurvivesEncodeDecodeRoundTrip() throws {
        var attr = AttributedString("Hello bold world")
        let range = try XCTUnwrap(attr.range(of: "bold"))
        attr[range].inlinePresentationIntent = .stronglyEmphasized

        let encoded = ArtifactRichTextCodec.encodeAttributed(attr)
        XCTAssertTrue(encoded.hasPrefix("{\\rtf"),
                      "formatted content must encode as inline RTF, not plain text")

        let decoded = ArtifactRichTextCodec.decode(encoded)
        XCTAssertEqual(decoded.string, "Hello bold world", "text must be intact")
        XCTAssertTrue(fontTrait(decoded, word: "bold", trait: .boldFontMask),
                      "the bold word must still be bold after the round-trip (#2494)")
    }

    /// Italic via `inlinePresentationIntent.emphasized` round-trips.
    func testItalicSurvivesRoundTrip() throws {
        var attr = AttributedString("plain italic plain")
        let range = try XCTUnwrap(attr.range(of: "italic"))
        attr[range].inlinePresentationIntent = .emphasized

        let decoded = ArtifactRichTextCodec.decode(ArtifactRichTextCodec.encodeAttributed(attr))
        XCTAssertTrue(fontTrait(decoded, word: "italic", trait: .italicFontMask),
                      "italic must survive the round-trip")
    }

    /// Underline (a `SwiftUI.UnderlineStyle` scope key, not a font trait)
    /// round-trips via `.underlineStyle`.
    func testUnderlineSurvivesRoundTrip() throws {
        var attr = AttributedString("plain under plain")
        let range = try XCTUnwrap(attr.range(of: "under"))
        attr[range].underlineStyle = .single

        let decoded = ArtifactRichTextCodec.decode(ArtifactRichTextCodec.encodeAttributed(attr))
        XCTAssertTrue(lineStyle(decoded, word: "under", key: .underlineStyle),
                      "underline must survive the round-trip")
    }

    /// Strikethrough (`inlinePresentationIntent.strikethrough` or the SwiftUI
    /// scope key) round-trips via `.strikethroughStyle`.
    func testStrikethroughSurvivesRoundTrip() throws {
        var attr = AttributedString("plain struck plain")
        let range = try XCTUnwrap(attr.range(of: "struck"))
        attr[range].strikethroughStyle = .single

        let decoded = ArtifactRichTextCodec.decode(ArtifactRichTextCodec.encodeAttributed(attr))
        XCTAssertTrue(lineStyle(decoded, word: "struck", key: .strikethroughStyle),
                      "strikethrough must survive the round-trip")
    }

    /// Plain text stays plain: no RTF wrapper, so stored content remains
    /// human-readable and unformatted edits aren't needlessly promoted to RTF.
    func testPlainTextEncodesAsPlainString() {
        let attr = AttributedString("just plain unformatted text")
        let encoded = ArtifactRichTextCodec.encodeAttributed(attr)
        XCTAssertEqual(encoded, "just plain unformatted text",
                       "unformatted text must encode as the bare plain string")
    }

    /// Editing plain text round-trips losslessly through encode/decode — the
    /// edited string is exactly what comes back (proves plain edits persist).
    func testPlainEditRoundTripsLosslessly() {
        let edited = AttributedString("the user typed a fresh sentence")
        let encoded = ArtifactRichTextCodec.encodeAttributed(edited)
        let decoded = ArtifactRichTextCodec.decodeAttributed(encoded)
        XCTAssertEqual(String(decoded.characters), "the user typed a fresh sentence")
    }

    // MARK: - Plain-text projection (#2317)

    /// THE #2317 bug: page content stored as RTF must render as resolved text in
    /// the native reader — accented escapes (`\'e1` → á, `\'f1` → ñ) resolved and
    /// no stray control words / backslashes leaking through.
    func testPlainTextResolvesRTFEscapes() {
        let rtf = "{\\rtf1\\ansi C\\'e1rmen se\\'f1or Jos\\'e9}"
        let plain = ArtifactRichTextCodec.plainText(rtf)
        XCTAssertTrue(plain.contains("Cármen"), "\\'e1 must resolve to á")
        XCTAssertTrue(plain.contains("señor"), "\\'f1 must resolve to ñ")
        XCTAssertTrue(plain.contains("José"), "\\'e9 must resolve to é")
        XCTAssertFalse(plain.contains("\\'"), "no raw escape codes may leak")
        XCTAssertFalse(plain.contains("\\rtf"), "no RTF control words may leak")
    }

    /// Plain text short-circuits unchanged — the common (non-RTF) case pays no
    /// decode cost and is returned verbatim, backslashes and all.
    func testPlainTextPassesNonRTFThrough() {
        let plain = "just plain text with a \\ backslash and no rtf header"
        XCTAssertEqual(ArtifactRichTextCodec.plainText(plain), plain)
        XCTAssertEqual(ArtifactRichTextCodec.plainText(""), "")
    }

    // MARK: - Save path (stubbed service)

    /// An edit fires the save with the *encoded* content, and that encoded
    /// payload preserves bold — mirrors `ArtifactPanel.performSave` handing
    /// `encodeAttributed(draftText)` to its `onSave` closure. Uses the
    /// store-owned save path (#2466) with a stubbed persistence closure so no
    /// live backend is needed.
    func testSaveFiresWithEncodedBoldContent() async throws {
        var draft = AttributedString("Hello bold world")
        let range = try XCTUnwrap(draft.range(of: "bold"))
        draft[range].inlinePresentationIntent = .stronglyEmphasized

        // What ArtifactPanel.performSave computes and passes to onSave.
        let encoded = ArtifactRichTextCodec.encodeAttributed(draft)

        let captured = Captured()
        let store = DocumentStore(apiClient: APIClient())
        let error = await store.savePageContent(documentId: "doc-1") {
            captured.set(encoded)
            return Document(id: "doc-1", parentId: "root", docType: .file, name: "Doc")
        }

        XCTAssertNil(error, "the stubbed save must succeed")
        let sent = try XCTUnwrap(captured.value, "the save closure must have fired")
        XCTAssertEqual(sent, encoded, "the save must receive the encoded content verbatim")

        // The persisted payload still carries bold when read back.
        XCTAssertTrue(fontTrait(ArtifactRichTextCodec.decode(sent), word: "bold", trait: .boldFontMask),
                      "the saved content must preserve bold (#2494)")
    }

    // MARK: - Helpers

    private func fontTrait(_ attr: NSAttributedString, word: String, trait: NSFontTraitMask) -> Bool {
        #if canImport(AppKit)
        let range = (attr.string as NSString).range(of: word)
        guard range.location != NSNotFound else { return false }
        var found = false
        attr.enumerateAttribute(.font, in: range) { value, _, _ in
            if let font = value as? NSFont,
               NSFontManager.shared.traits(of: font).contains(trait) {
                found = true
            }
        }
        return found
        #else
        return false
        #endif
    }

    private func lineStyle(_ attr: NSAttributedString, word: String, key: NSAttributedString.Key) -> Bool {
        let range = (attr.string as NSString).range(of: word)
        guard range.location != NSNotFound else { return false }
        var found = false
        attr.enumerateAttribute(key, in: range) { value, _, _ in
            if let raw = value as? Int, raw != 0 { found = true }
        }
        return found
    }
}

/// Thread-safe capture box for the value the stubbed save closure receives.
private final class Captured: @unchecked Sendable {
    private let lock = NSLock()
    private var _value: String?
    var value: String? { lock.lock(); defer { lock.unlock() }; return _value }
    func set(_ value: String) { lock.lock(); _value = value; lock.unlock() }
}
