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

    /// WHY (#6082): with 3 lines selected the section described their common parent; it must describe the lines.
    @Test("a selection reads Mixed where the lines differ, and the value where they agree")
    func selectionMixed() {
        let one = [setting("language", "es", source: "user", level: "segment"), setting("direction", "ltr", source: "fallback")]
        let two = [setting("language", "la", source: "user", level: "segment"), setting("direction", "ltr", source: "fallback")]
        let rows = InspectorLanguage.rows(selection: [one, two, one])
        #expect(rows.map(\.key) == ["language", "direction"])
        #expect(rows[0].value == InspectorLanguage.mixed && rows[0].origin == "differs between the selected lines")
        #expect(rows[1].value == "Left to Right", "the lines agree: the value, not Mixed")
        #expect(InspectorLanguage.rows(selection: [one]) == InspectorLanguage.rows(one), "one line is its own rows")
        let missing = InspectorLanguage.rows(selection: [one, [setting("direction", "ltr", source: "fallback")]])
        #expect(missing.first { $0.key == "language" }?.value == InspectorLanguage.mixed, "a line without the fact differs")
        #expect(InspectorLanguage.rows(selection: []).isEmpty)
    }

    /// WHY (## 1075): a failed read counted as a line with no settings (Mixed), and past the cap the first lines stood for all.
    @Test("a selection says why it shows nothing: a failed read, or too many lines")
    func selectionNotes() {
        let one = [setting("language", "es", source: "user")]
        #expect(InspectorLanguage.selection([one, one], total: 2, cap: 200) == .rows(InspectorLanguage.rows(selection: [one, one])))
        guard case .note(let failed) = InspectorLanguage.selection([one, nil], total: 2, cap: 200) else { return Issue.record("a failed read must say so") }
        #expect(failed.contains("could not be read"))
        guard case .note(let many) = InspectorLanguage.selection([], total: 201, cap: 200) else { return Issue.record("past the cap must say so") }
        #expect(many.contains("201 lines"))
    }
}
