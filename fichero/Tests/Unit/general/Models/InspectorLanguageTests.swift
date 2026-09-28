@testable import Fichero
import Testing

/// The Inspector's Language & script section (#5158). What breaks without these: a fallback shown as
/// if someone had set it, "unknown" and "never looked" shown as the same, or "rtl" where a person
/// reads "Right to Left".
struct InspectorLanguageTests {
    private func setting(_ key: String, _ value: String?, status: String = "resolved", source: String,
                         level: String? = nil) -> InspectorLanguage.Setting {
        .init(key: key, value: value, status: status, source: source, basis: "why \(key)", level: level)
    }

    @Test("each fact says where it came from; a fallback says it is one")
    func originsInWords() {
        let rows = InspectorLanguage.rows([
            setting("direction", "rtl", source: "derived-from-script"),
            setting("script", "Syrc", source: "user", level: "segment"),
            setting("language", "English", source: "fallback"),
            setting("encoding", nil, status: "unknown", source: "never_determined")
        ])
        #expect(rows.map(\.key) == ["language", "script", "direction", "encoding"])
        #expect(rows[0].value == "English" && rows[0].origin == "a fallback")
        #expect(rows[1].origin == "set by a person, on this segment")
        #expect(rows[2].value == "Right to Left" && rows[2].origin == "from the script")
        #expect(rows[3].value == "Not determined")
        #expect(rows[0].basis == "why language")
    }

    @Test("unknown after looking is not the same as never looked")
    func unknownIsNotUnexamined() {
        let examined = InspectorLanguage.rows([setting("script", nil, status: "unknown", source: "user", level: "page")])
        let never = InspectorLanguage.rows([setting("script", nil, status: "unknown", source: "never_determined")])
        #expect(examined[0].value == "Unknown")
        #expect(never[0].value == "Not determined")
        #expect(InspectorLanguage.origin(source: "metadata", level: "page") == "from the file, on the page")
    }
}
