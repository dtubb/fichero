@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The Inspector as a form at every level (`source.editor.inspector-is-a-form-at-every-level`): the rows the engine
/// answers (`GET /api/segments/inspect`) become a grouped form, each control sends the existing `segment.update_many`
/// for the whole selection, and each row carries an identifier and an accessibility value that says its state.
struct SegmentInspectorFormTests {
    private func choice(_ value: String, _ label: String? = nil) -> InspectorForm.Choice {
        .init(value: value, label: label ?? value)
    }

    private func row(
        _ key: String, state: InspectorForm.State = .set, value: String? = nil, values: [String] = [],
        inheritedFrom: String? = nil, choices: [InspectorForm.Choice] = [], toggle: Bool = false, freeText: Bool = false
    ) -> InspectorForm.Row {
        .init(
            key: key, label: key.capitalized, isToggle: toggle, state: state, value: value, values: values,
            inheritedFrom: inheritedFrom, choices: choices, freeText: freeText
        )
    }

    private func segment(_ id: String, version: Int?) -> Segment {
        let anchor = SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: [0.1, 0.2, 0.5, 0.05]))
        return Segment(
            id: id, provisional: false, documentId: "page-1", passId: "imported",
            kind: "region", kindRaw: nil, version: version, provenanceKind: .externalImport, anchor: anchor,
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    private func updates(_ call: SegmentEdit.Call) throws -> [[String: Any]] {
        let data = try JSONEncoder().encode(call.params)
        let body = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        return try #require(body["updates"] as? [[String: Any]])
    }

    @Test("the form is titled by its level and the number picked")
    func title() {
        #expect(InspectorForm(level: "region", count: 1, withheld: 0, rows: []).title == "Region")
        #expect(InspectorForm(level: "line", count: 3, withheld: 0, rows: []).title == "3 lines")
        #expect(InspectorForm(level: "mixed", count: 2, withheld: 0, rows: []).title == "2 segments")
        #expect(InspectorForm(level: "word", count: 1, withheld: 0, rows: []).title == "Word")
    }

    @Test("a set value shows its label, an inherited one says where it came from, a mixed one says Mixed, none says Not set")
    func displayedValues() {
        let directions = [choice("rtl", "Right to Left"), choice("ltr", "Left to Right")]
        #expect(row("direction", value: "rtl", choices: directions).displayValue == "Right to Left")
        #expect(row("direction", state: .inherited, value: "ltr", inheritedFrom: "document", choices: directions).displayValue
                == "Left to Right")
        #expect(row("direction", state: .mixed, values: ["ltr", "rtl"], choices: directions).displayValue == "Mixed")
        #expect(row("direction", state: .none).displayValue == "Not set")
        #expect(row("language", value: "syc", freeText: true).displayValue == "syc")
    }

    @Test("the accessibility value says the state in words, for VoiceOver")
    func accessibilityValues() {
        let directions = [choice("rtl", "Right to Left"), choice("ltr", "Left to Right")]
        #expect(row("direction", value: "rtl", choices: directions).accessibilityValue == "Right to Left, set on this segment")
        #expect(row("direction", state: .inherited, value: "ltr", inheritedFrom: "document", choices: directions).accessibilityValue
                == "Left to Right, inherited from document")
        #expect(row("direction", state: .mixed, values: ["ltr", "rtl"], choices: directions).accessibilityValue
                == "Mixed: Left to Right, Right to Left")
        #expect(row("direction", state: .none).accessibilityValue == "Not set")
        #expect(row("furniture", value: "true", toggle: true).accessibilityValue == "On, set on this segment")
        #expect(row("furniture", value: "false", toggle: true).accessibilityValue == "Off, set on this segment")
        #expect(row("furniture", state: .mixed, values: ["false", "true"], toggle: true).accessibilityValue == "Mixed: Off, On")
    }

    @Test("each row has an identifier made from its key")
    func identifiers() {
        #expect(row("line_progression").identifier == "inspector.form.line-progression")
        #expect(row("type").identifier == "inspector.form.type")
        #expect(InspectorForm.identifier == "inspector.form")
    }

    @Test("a toggle is on only when every segment is, and a mixed one is not on")
    func toggleIsOn() {
        #expect(row("furniture", value: "true", toggle: true).isOn)
        #expect(!row("furniture", value: "false", toggle: true).isOn)
        #expect(!row("furniture", state: .mixed, values: ["false", "true"], toggle: true).isOn)
    }

    @Test("each control sends segment.update_many with the version read, one row per segment picked")
    func controlsSendTheExistingAction() throws {
        let picked = [segment("r1", version: 4), segment("r2", version: 7)]
        let call = try InspectorForm.edit(rowKey: "direction", to: "ttb", on: picked).get()
        #expect(call.action == "segment.update_many")
        let sent = try updates(call)
        #expect(sent.map { $0["segment_id"] as? String } == ["r1", "r2"])
        #expect(sent.map { $0["expected_version"] as? Int } == [4, 7])
        #expect(sent.allSatisfy { $0["direction"] as? String == "ttb" && $0["kind"] == nil })
    }

    @Test("Type is written to kind_raw and leaves kind alone; line progression and furniture have their own fields")
    func eachKeyHasItsField() throws {
        let one = [segment("r1", version: 1)]
        let type = try updates(InspectorForm.edit(rowKey: "type", to: "heading", on: one).get())
        #expect(type[0]["kind_raw"] as? String == "heading" && type[0]["kind"] == nil)
        let progression = try updates(InspectorForm.edit(rowKey: "line_progression", to: "rtl", on: one).get())
        #expect(progression[0]["line_progression"] as? String == "rtl")
        let furniture = try updates(InspectorForm.edit(rowKey: "furniture", to: "true", on: one).get())
        #expect(furniture[0]["is_furniture"] as? Bool == true)
        let language = try updates(InspectorForm.edit(rowKey: "language", to: "syc", on: one).get())
        #expect(language[0]["language"] as? String == "syc")
        let script = try updates(InspectorForm.edit(rowKey: "script", to: "Syrc", on: one).get())
        #expect(script[0]["script"] as? String == "Syrc")
    }

    @Test("a segment with no known version, an empty pick, an empty typed code and a key the form does not know send nothing")
    func nothingIsSentWhenItCannotBeChecked() {
        #expect(InspectorForm.edit(rowKey: "direction", to: "rtl", on: [segment("r1", version: nil)]) == .failure(.versionUnknown))
        #expect(InspectorForm.edit(rowKey: "direction", to: "rtl", on: []) == .failure(.tooFew))
        #expect(InspectorForm.edit(rowKey: "language", to: "  ", on: [segment("r1", version: 1)]) == .failure(.tooFew))
        #expect(InspectorForm.edit(rowKey: "colour", to: "red", on: [segment("r1", version: 1)]) == .failure(.tooFew))
    }

    @Test("the engine's answer becomes the form's rows, in the engine's order, with its choices")
    func drawnFromTheAnswer() throws {
        let json = """
        {"level":"region","count":1,"withheld":0,"rows":[
          {"key":"type","label":"Type","kind":"choice","state":"none","values":[],
           "choices":[{"value":"main text","label":"Main text"}],"free_text":false},
          {"key":"furniture","label":"Page furniture","kind":"toggle","state":"set","value":"false","values":[],"choices":[],"free_text":false},
          {"key":"language","label":"Language","kind":"choice","state":"inherited","value":"syc","values":[],
           "inherited_from":"document","choices":[{"value":"syc","label":"syc"}],"free_text":true}]}
        """
        let answer = try JSONDecoder().decode(Components.Schemas.SegmentInspectRead.self, from: Data(json.utf8))
        let form = InspectorForm(answer)
        #expect(form.rows.map(\.key) == ["type", "furniture", "language"])
        #expect(form.rows[0].choices.map(\.label) == ["Main text"])
        #expect(form.rows[1].isToggle && !form.rows[1].isOn)
        #expect(form.rows[2].state == .inherited && form.rows[2].inheritedFrom == "document" && form.rows[2].freeText)
    }
}
