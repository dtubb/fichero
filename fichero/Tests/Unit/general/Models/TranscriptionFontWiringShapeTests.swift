@testable import Fichero
import XCTest

/// `layers.text.font-from-script-and-period` (#5438): the library's transcription family is asked of the engine
/// when a workspace opens, and both transcription surfaces draw through it. Source-shape guard.
@MainActor
final class TranscriptionFontWiringShapeTests: XCTestCase {
    func testWorkspaceLoadsTheFamilyAfterTheFaces() throws {
        let root = try AppSource.code("Views/Library/Workspace/LibraryWorkspaceRoot.swift")
        let faces = try XCTUnwrap(root.range(of: "BundledFonts.shared.load(from:"))
        let family = try XCTUnwrap(root.range(of: "BundledFonts.shared.loadTranscriptionFont(from:"))
        XCTAssertLessThan(faces.lowerBound, family.lowerBound)
    }

    func testReaderLinesAndInlineWordsDrawThroughTheFamily() throws {
        XCTAssertTrue(try AppSource.code("Views/Reader/Page/ReaderLinesView.swift").contains("family: BundledFonts.shared.transcriptionFamily"))
        XCTAssertTrue(try AppSource.code("Views/Preview/ImageViewer/Regions/InlineWords.swift").contains("BundledFonts.loadedTranscriptionFamily"))
    }

    func testTheScriptIsTheFirstOfTheSavedAnswers() {
        let data = Data(#"{"scripts":["Latn","Grek"],"period":"1250"}"#.utf8)
        XCTAssertEqual(BundledFonts.firstScript(inAnswers: data), "Latn")
        XCTAssertNil(BundledFonts.firstScript(inAnswers: Data("{}".utf8)))
    }
}
