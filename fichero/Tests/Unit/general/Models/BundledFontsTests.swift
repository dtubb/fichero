import CoreText
@testable import Fichero
import FicheroAPIClient
import SwiftUI
import XCTest

/// The engine's bundled fonts as the app uses them (#5210, #5206). Daniel's clm 13027 page drew MUFI's
/// U+F1AC as ⍰ in the Inspector, the Segments rows and on the image: no system font has it, and registering
/// a font with the process does not add it to the system's fallback. What breaks without these: the
/// cascade is dropped or built wrong, MUFI goes back to boxes, or the bundled faces shadow a script the
/// system already draws.
@MainActor
final class BundledFontsTests: XCTestCase {
    /// The faces from the SAME files the engine serves, so this cannot pass on a copy that drifted.
    private func cascade() throws -> [CTFontDescriptor] {
        let fonts = try AppSource.sibling("../fichero-server/src/fichero_server/resources/fonts").standardized
        let otf = try FileManager.default.contentsOfDirectory(atPath: fonts.path).filter { $0.hasSuffix(".otf") }.sorted()
        let files = otf.filter { $0.hasPrefix("Junicode") } + otf.filter { !$0.hasPrefix("Junicode") }
        XCTAssertFalse(files.isEmpty, "the engine bundles its fonts under resources/fonts")
        let faces = try files.flatMap { name in
            BundledFonts.descriptors(in: try Data(contentsOf: fonts.appendingPathComponent(name)))
        }
        XCTAssertEqual(faces.count, files.count, "every font file the engine serves loads as a face")
        return faces
    }

    private func family(of text: String, in font: CTFont) -> String {
        let used = CTFontCreateForString(font, text as CFString, CFRange(location: 0, length: (text as NSString).length))
        return CTFontCopyFamilyName(used) as String
    }

    func testAMufiLetterFindsJunicodeThroughTheCascade() throws {
        let base = BundledFonts.systemDescriptor(.body)
        let font = BundledFonts.ctFont(base: base, size: 0, cascade: try cascade())
        XCTAssertEqual(family(of: "\u{F1AC}", in: font), "Junicode", "MUFI U+F1AC must not fall to LastResort (⍰)")
        XCTAssertNotEqual(
            family(of: "\u{F1AC}", in: BundledFonts.ctFont(base: base, size: 0, cascade: [])), "Junicode",
            "without the cascade the system has no MUFI font: this is the defect the cascade fixes"
        )
    }

    func testTheSystemsOwnScriptsKeepTheirFonts() throws {
        let font = BundledFonts.ctFont(base: BundledFonts.systemDescriptor(.body), size: 0, cascade: try cascade())
        XCTAssertNotEqual(family(of: "登", in: font), "Junicode", "Chinese keeps the system's font")
        XCTAssertNotEqual(family(of: "a", in: font), "Junicode", "Latin keeps the system font")
    }

    func testWithNoEngineTheFontIsTheSystemsStyle() {
        XCTAssertEqual(BundledFonts.font(.body, cascade: []), Font.system(.body), "no faces fetched: nothing changes")
    }

    /// The app reads the engine's own list (`GET /api/fonts`, fonts.py `BundledFont`), never a hard-coded one:
    /// the list names each font's url, so a font the engine adds reaches the app with no app change.
    /// Since #5263 the list is the `{items, count}` envelope, read through the generated client.
    func testTheEnginesFontListIsReadInItsOrder() {
        let list = Components.Schemas.BundledFontList(
            items: [
                .init(family: "Junicode", url: "/api/fonts/Junicode-Regular.otf", covers: "MUFI", licenceUrl: "/api/fonts/OFL-Junicode.txt"),
                .init(family: "Noto Sans Syriac", url: "/api/fonts/NotoSansSyriac-Regular.otf", covers: "Syriac", licenceUrl: "/api/fonts/OFL-NotoSansSyriac.txt")
            ],
            count: 2
        )
        XCTAssertEqual(
            BundledFonts.fontURLs(in: list),
            ["/api/fonts/Junicode-Regular.otf", "/api/fonts/NotoSansSyriac-Regular.otf"]
        )
    }
}
