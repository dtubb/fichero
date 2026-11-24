import SwiftUI

/// The Inspector's form (`source.editor.inspector-is-a-form-at-every-level`): one labelled row per engine row, in the
/// engine's order (which is the Tab and VoiceOver order). It draws `InspectorForm` and reports `(rowKey, value)`; the
/// owner sends the edit.
struct InspectorFormView: View {
    let form: InspectorForm
    let onChange: (_ rowKey: String, _ value: String) -> Void

    var body: some View {
        Form {
            Section(form.title) {
                ForEach(form.rows) { row in
                    FormRow(row: row, onChange: { onChange(row.key, $0) })
                }
            }
        }
        .formStyle(.grouped)
        .scrollDisabled(true)
        .accessibilityIdentifier(InspectorForm.identifier)
    }
}

private struct FormRow: View {
    let row: InspectorForm.Row
    let onChange: (String) -> Void
    @State private var typed = ""

    var body: some View {
        LabeledContent(row.label) { control }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(row.identifier)
            .accessibilityLabel(row.label)
            .accessibilityValue(row.accessibilityValue)
    }

    @ViewBuilder private var control: some View {
        if row.isToggle {
            Toggle(row.label, isOn: Binding(get: { row.isOn }, set: { onChange($0 ? "true" : "false") }))
                .labelsHidden()
        } else {
            HStack(spacing: 4) {
                if row.freeText {
                    TextField(row.label, text: $typed, prompt: Text(row.displayValue))
                        .labelsHidden()
                        .multilineTextAlignment(.trailing)
                        .onSubmit {
                            onChange(typed)
                            typed = ""
                        }
                }
                Menu(row.freeText ? "Choose" : row.displayValue) {
                    ForEach(row.choices, id: \.value) { choice in
                        Button(choice.label) { onChange(choice.value) }
                    }
                }
                .menuStyle(.button)
                .buttonStyle(.borderless)
                .fixedSize()
            }
        }
    }
}
