@testable import Fichero
import XCTest

/// The live-editor beachball guard (Daniel's backtrace, 2026-08-10): SwiftUI's
/// AttributedString TextEditor lays out the ENTIRE document synchronously in
/// sizeThatFits, so book-sized content froze the main thread for minutes.
/// Content above the limit renders a read-only preview; pages stay editable.
final class OversizeContentGuardTests: XCTestCase {
    func testTheLimitIsBookScaleNotPageScale() {
        // A long PAGE (a dense archival transcript runs a few thousand chars)
        // must stay comfortably editable; a BOOK must not reach the editor.
        XCTAssertGreaterThanOrEqual(ArtifactPanel.liveEditorCharacterLimit, 20_000)
        XCTAssertLessThanOrEqual(ArtifactPanel.liveEditorCharacterLimit, 500_000)
    }

    func testThePreviewShowsLessThanTheLimit() {
        // The preview must itself stay cheap — smaller than what we refused
        // to mount an editor for.
        XCTAssertLessThanOrEqual(
            ArtifactPanel.oversizePreviewCharacters,
            ArtifactPanel.liveEditorCharacterLimit
        )
    }

    func testTheGuardBranchesOnRawContentLength() throws {
        // Source pin: the branch must key on rawArtifactContent BEFORE the
        // TextEditor mounts — a guard after mount lays the book out once,
        // which is exactly the freeze.
        let source = try AppSource.text("Views/Inspector/Artifacts/ArtifactPanel+Content.swift")
        let guardRange = try XCTUnwrap(
            source.range(of: "rawArtifactContent.count > Self.liveEditorCharacterLimit")
        )
        let editorRange = try XCTUnwrap(source.range(of: "TextEditor(text: $draftText)"))
        XCTAssertLessThan(
            guardRange.lowerBound, editorRange.lowerBound,
            "the oversize branch must be checked before the live editor mounts"
        )
    }
}
