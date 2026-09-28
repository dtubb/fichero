import CoreText
@testable import Fichero
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
        let fonts = try AppSource.root().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("fichero-server/src/fichero_server/resources/fonts")
        let faces = try BundledFonts.names.flatMap { name in
            BundledFonts.descriptors(in: try Data(contentsOf: fonts.appendingPathComponent(name)))
        }
        XCTAssertEqual(faces.count, BundledFonts.names.count, "every file the engine serves loads as a face, the woff2 too")
        return faces
    }

    private func family(of text: String, in font: CTFont) -> String {
        let used = CTFontCreateForString(font, text as CFString, CFRange(location: 0, length: (text as NSString).length))
        return CTFontCopyFamilyName(used) as String
    }

    func testAMufiLetterFindsJunicodeThroughTheCascade() throws {
        let base = BundledFonts.systemDescriptor(.body)
        let font = BundledFonts.ctFont(base: base, size: 0, cascade: try cascade())
        XCTAssertEqual(family(of: "\u{F1AC}", in: font), "Junicode VF", "MUFI U+F1AC must not fall to LastResort (⍰)")
        XCTAssertNotEqual(
            family(of: "\u{F1AC}", in: BundledFonts.ctFont(base: base, size: 0, cascade: [])), "Junicode VF",
            "without the cascade the system has no MUFI font: this is the defect the cascade fixes"
        )
    }

    func testTheSystemsOwnScriptsKeepTheirFonts() throws {
        let font = BundledFonts.ctFont(base: BundledFonts.systemDescriptor(.body), size: 0, cascade: try cascade())
        XCTAssertNotEqual(family(of: "登", in: font), "Junicode VF", "Chinese keeps the system's font")
        XCTAssertNotEqual(family(of: "a", in: font), "Junicode VF", "Latin keeps the system font")
    }

    func testWithNoEngineTheFontIsTheSystemsStyle() {
        XCTAssertEqual(BundledFonts.font(.body, cascade: []), Font.system(.body), "no faces fetched: nothing changes")
    }
}
