import FicheroAPIClient
import SwiftUI

// MARK: - Prototype-declared attributes (datasets Stage 1)

/// The node's structured data: every attribute the prototype chain declares,
/// rendered as a typed row (toggle / picker / text), editable in place.
///
/// Renders nothing when the node has no prototype and no own attributes —
/// the section heading follows its rows (#4422). An unresolvable prototype
/// shows the resolver's error, never partial data.
struct DocumentAttributesSection: View {
    let documentId: String
    let entityService: EntityService?

    @State private var resolved: EntityService.EffectiveAttributes?
    @State private var drafts: [String: String] = [:]
    @State private var errorText: String?
    @State private var isSaving = false
    @State private var showTypeEditor = false

    var body: some View {
        // Always render the section (Daniel 2026-08-13 ruling on the empty
        // state): a node with nothing declared says so, with the editor one
        // click away — hiding the section made the whole feature
        // undiscoverable on exactly the nodes that need types defined.
        VStack(alignment: .leading, spacing: 4) {
            Text("Attributes")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
            if let resolved, !resolved.declarations.isEmpty || hasLooseValues {
                rows(resolved)
            } else if errorText == nil {
                HStack(spacing: 6) {
                    Text("None declared")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                    Button("Define…") {
                        showTypeEditor = true
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.tint)
                    .font(.caption)
                    .help("Declare typed attributes on this node's document type")
                }
            }
            if let errorText {
                Text(errorText)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
        .task(id: documentId) { await load() }
        .sheet(isPresented: $showTypeEditor) {
            PrototypeEditorSheet(entityService: entityService) {
                Task { await load() }
            }
        }
    }

    /// Own values with no declaration behind them (loose data on a node
    /// without a prototype) — still shown, as plain text rows.
    private var hasLooseValues: Bool {
        guard let resolved else { return false }
        let declared = Set(resolved.declarations.map(\.name))
        return resolved.ownValues.keys.contains { !declared.contains($0) }
    }

    @ViewBuilder
    private func rows(_ resolved: EntityService.EffectiveAttributes) -> some View {
        ForEach(resolved.declarations) { decl in
            attributeRow(decl)
        }
        let declared = Set(resolved.declarations.map(\.name))
        ForEach(resolved.ownValues.keys.filter { !declared.contains($0) }.sorted(), id: \.self) { name in
            LabeledContent(name) {
                textField(name: name, prompt: "")
            }
        }
    }

    @ViewBuilder
    private func attributeRow(_ decl: EntityService.AttributeDeclaration) -> some View {
        LabeledContent(decl.required ? "\(decl.name) *" : decl.name) {
            switch decl.type {
            case "checkbox":
                Toggle("", isOn: boolBinding(for: decl.name))
                    .labelsHidden()
                    .toggleStyle(.switch)
                    .controlSize(.mini)
            case "select" where !decl.options.isEmpty:
                Picker("", selection: selectBinding(for: decl.name)) {
                    Text("—").tag("")
                    ForEach(decl.options, id: \.self) { Text($0).tag($0) }
                }
                .labelsHidden()
                .controlSize(.small)
            default:
                textField(name: decl.name, prompt: inheritedPrompt(for: decl.name))
            }
        }
        .disabled(isSaving)
    }

    private func textField(name: String, prompt: String) -> some View {
        TextField("", text: draftBinding(for: name), prompt: prompt.isEmpty ? nil : Text(prompt))
            .textFieldStyle(.plain)
            .multilineTextAlignment(.trailing)
            .foregroundStyle(.primary)
            .onSubmit { Task { await save(name: name) } }
    }

    /// The inherited default, shown as placeholder when the node has no own
    /// value — visible without being baked into the node on save.
    private func inheritedPrompt(for name: String) -> String {
        guard let resolved, resolved.ownValues[name] == nil else { return "" }
        return displayString(resolved.values[name] ?? nil)
    }

    // MARK: - Bindings

    private func draftBinding(for name: String) -> Binding<String> {
        Binding(
            get: { drafts[name] ?? "" },
            set: { drafts[name] = $0 }
        )
    }

    private func boolBinding(for name: String) -> Binding<Bool> {
        Binding(
            get: { (effectiveValue(name) as? Bool) ?? false },
            set: { newValue in Task { await save(name: name, typed: newValue) } }
        )
    }

    private func selectBinding(for name: String) -> Binding<String> {
        Binding(
            get: { displayString(effectiveValue(name)) },
            set: { newValue in
                Task { await save(name: name, typed: newValue.isEmpty ? nil : newValue) }
            }
        )
    }

    private func effectiveValue(_ name: String) -> (any Sendable)? {
        resolved?.values[name] ?? nil
    }

    // MARK: - Load / save

    private func load() async {
        guard let entityService else { return }
        errorText = nil
        do {
            let fetched = try await entityService.effectiveAttributes(documentId: documentId)
            resolved = fetched
            drafts = fetched.ownValues.mapValues { displayString($0) }
        } catch {
            resolved = EntityService.EffectiveAttributes(
                prototypeKey: nil, declarations: [], values: [:], ownValues: [:]
            )
            errorText = error.localizedDescription
        }
    }

    /// Save a text draft: typed per its declaration, removed when cleared so
    /// the node falls back to the inherited default. A number that does not
    /// parse is an error, never silently sent as text.
    private func save(name: String) async {
        let draft = drafts[name]?.trimmingCharacters(in: .whitespaces) ?? ""
        guard let decl = resolved?.declarations.first(where: { $0.name == name }),
              decl.type == "number" else {
            await save(name: name, typed: draft.isEmpty ? nil : draft)
            return
        }
        guard !draft.isEmpty else {
            await save(name: name, typed: nil)
            return
        }
        guard let number = Double(draft) else {
            errorText = "“\(name)” must be a number"
            return
        }
        await save(name: name, typed: number)
    }

    /// Merge one key into the node's own dict and send it wholesale — the
    /// PATCH contract mirrors `metadata`. `nil` removes the key.
    private func save(name: String, typed: (any Sendable)?) async {
        guard let entityService, let current = resolved else { return }
        var own = current.ownValues
        if typed == nil {
            own.removeValue(forKey: name)
        } else {
            own[name] = typed
        }
        isSaving = true
        defer { isSaving = false }
        errorText = nil
        do {
            try await entityService.updateDocumentAttributes(documentId: documentId, attributes: own)
            await load()
        } catch {
            errorText = error.localizedDescription
        }
    }

    private func displayString(_ value: (any Sendable)?) -> String {
        switch value {
        case nil: return ""
        case let string as String: return string
        case let bool as Bool: return bool ? "true" : "false"
        case let int as Int: return String(int)
        case let double as Double:
            return double == double.rounded() ? String(Int(double)) : String(double)
        default: return String(describing: value!)
        }
    }
}
