@testable import Fichero
import XCTest

/// `layers.text.font-from-script-and-period` (#5438): the transcription family belongs to the LIBRARY (two windows
/// on libraries with different scripts keep their own face), is asked of the engine when a workspace opens, and
/// both transcription surfaces and the pane menu read it from the environment. No app-wide or unsafe static copy.
/// Source-shape guard.
@MainActor
final class TranscriptionFontWiringShapeTests: XCTestCase {
    func testTheFamilyIsOwnedPerLibraryAndInjectedByTheWorkspace() throws {
        XCTAssertTrue(try AppSource.code("Models/LibraryManager.swift").contains("lazy var transcriptionFontStore = TranscriptionFontStore("))
        let root = try AppSource.code("Views/Library/Workspace/LibraryWorkspaceRoot.swift")
        XCTAssertTrue(root.contains("await library.transcriptionFontStore.load()"))
        XCTAssertTrue(root.contains(".environment(library.transcriptionFontStore)"))
    }

    func testNoAppWideOrUnsafeStaticHoldsTheFamily() throws {
        let fonts = try AppSource.code("Models/BundledFonts.swift")
        XCTAssertFalse(fonts.contains("transcriptionFamily"), "BundledFonts went back to one app-wide family")
        XCTAssertFalse(fonts.contains("loadedTranscriptionFamily"))
        let inline = try AppSource.code("Views/Preview/ImageViewer/Regions/InlineWords.swift")
        XCTAssertFalse(inline.contains("loadedTranscriptionFamily"), "the off-main drawer reads a static again")
        XCTAssertTrue(inline.contains("family: String?"), "the family is passed in")
    }

    func testSurfacesReadTheLibrarysFamily() throws {
        XCTAssertTrue(try AppSource.code("Views/Reader/Page/ReaderLinesView.swift").contains("family: transcriptionFont?.family"))
        XCTAssertTrue(try AppSource.code("Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+Regions.swift")
            .contains("overlay.transcriptionFamily = transcriptionFont?.family"))
        XCTAssertTrue(try AppSource.code("Views/Preview/ImageViewer/Regions/DocumentOverlayView.swift")
            .contains("family: overlay.transcriptionFamily"))
    }

    func testThePaneMenuOffersFontOnlyOnTranscriptionPanes() throws {
        let menu = try AppSource.code("Views/Shell/PaneHead/PaneChromeMenu.swift")
        XCTAssertTrue(menu.contains("if offersFont, let fontStore {"))
        XCTAssertTrue(try AppSource.code("Views/Reader/Page/ReadingPaneView.swift").contains(".environment(\\.offersTranscriptionFont, true)"))
        XCTAssertTrue(try AppSource.code("Views/Shell/ContentView/Layout/ContentView+PreviewPaneHead.swift")
            .contains(".environment(\\.offersTranscriptionFont, true)"))
    }

    func testTheScriptIsTheFirstOfTheSavedAnswers() {
        let data = Data(#"{"scripts":["Latn","Grek"],"period":"1250"}"#.utf8)
        XCTAssertEqual(TranscriptionFontStore.firstScript(inAnswers: data), "Latn")
        XCTAssertNil(TranscriptionFontStore.firstScript(inAnswers: Data("{}".utf8)))
    }
}
