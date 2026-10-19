//
//  CodeListSourceTests.swift
//  FicheroTests
//
//  About the Material: one grey line under Languages and one under Writing system, naming where the list comes
//  from, with links (#5834, `source.onboard.list-sources-shown`).
//

@testable import Fichero
import Foundation
import Testing

@Suite("Where the language and script lists come from")
struct CodeListSourceTests {
    private func links(_ scripts: Bool) -> [String] {
        CodeListSource.note(scripts: scripts).runs.compactMap { $0.link?.absoluteString }
    }

    @Test("Languages name ISO 639-3, Glottolog and Unicode CLDR, each a link")
    func languages() {
        let text = String(CodeListSource.note(scripts: false).characters)
        for name in ["ISO 639-3", "Glottolog", "Unicode CLDR", "historical languages and dialects"] {
            #expect(text.contains(name), "\(name)")
        }
        #expect(links(false).count == 3)
    }

    @Test("Writing system names ISO 15924 as a link")
    func scripts() {
        #expect(String(CodeListSource.note(scripts: true).characters).contains("ISO 15924"))
        #expect(links(true) == ["https://www.unicode.org/iso15924/"])
    }
}
