import FicheroAPIClient
import SwiftUI

// MARK: - New Entity Sheet (#916)

/// Simple form to create OR edit a KnowledgeEntity — fills the gap
/// where everything in the KG today comes from extractors. Backed by
/// `EntityService.upsertEntity` (create) or `patchEntity`
/// (edit, when `editing` is non-nil). Calls `onCommit` with the
/// new / updated entity so the browser can refresh.
struct NewEntitySheet: View {
    var editing: Components.Schemas.KnowledgeEntity?
    var onCommit: (Components.Schemas.KnowledgeEntity) -> Void

    init(
        editing: Components.Schemas.KnowledgeEntity? = nil,
        onCreated: @escaping (Components.Schemas.KnowledgeEntity) -> Void
    ) {
        self.editing = editing
        self.onCommit = onCreated
        _canonicalName = State(initialValue: editing?.canonicalName ?? "")
        _entityType = State(initialValue: editing?.entityType?.rawValue ?? "person")
        _aliasesText = State(initialValue: (editing?.aliases ?? []).joined(separator: "\n"))
    }

    @Environment(\.dismiss) private var dismiss
    @State private var canonicalName: String
    @State private var entityType: String
    @State private var aliasesText: String
    @State private var isSaving: Bool = false
    @State private var errorText: String?

    private var isEditing: Bool { editing != nil }

    private let kinds: [(key: String, label: String)] = [
        ("person", "Person"),
        ("location", "Place"),
        ("organization", "Organization"),
        ("event", "Event"),
        ("concept", "Concept"),
        ("other", "Other")
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(isEditing ? "Edit Entity" : "New Entity").font(.headline)
                Spacer()
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            .padding()
            Divider()
            form
            Spacer()
            footer
        }
        // Mac-only fixed size; iPhone/iPad sheets size to the screen (#2802).
        #if os(macOS)
        .frame(width: 420, height: 320)
        #endif
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Canonical name")
                .font(.caption)
                .foregroundStyle(.secondary)
            TextField("e.g. Eugenio Córdoba", text: $canonicalName)
                .textFieldStyle(.roundedBorder)

            Text("Type")
                .font(.caption)
                .foregroundStyle(.secondary)
            Picker("", selection: $entityType) {
                ForEach(kinds, id: \.key) { kind in
                    Text(kind.label).tag(kind.key)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()

            Text("Aliases (one per line)")
                .font(.caption)
                .foregroundStyle(.secondary)
            TextEditor(text: $aliasesText)
                .frame(minHeight: 60)
                .border(Color.gray.opacity(0.2))
        }
        .padding()
    }

    private var footer: some View {
        HStack {
            if let errorText = errorText {
                Text(errorText)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .lineLimit(2)
            }
            Spacer()
            Button(isEditing ? "Save" : "Create", action: save)
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
                .disabled(canonicalName.trimmingCharacters(in: .whitespaces).isEmpty || isSaving)
        }
        .padding()
    }

    private func save() {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        isSaving = true
        errorText = nil
        let name = canonicalName.trimmingCharacters(in: .whitespacesAndNewlines)
        let aliases = aliasesText
            .split(separator: "\n")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        Task {
            do {
                let result: Components.Schemas.KnowledgeEntity
                if let editing = editing, let entityId = editing.id {
                    result = try await library.entityService.patchEntity(
                        entityId,
                        canonicalName: name,
                        entityType: entityType,
                        aliases: aliases
                    )
                } else {
                    result = try await library.entityService.upsertEntity(
                        name: name,
                        entityType: entityType,
                        aliases: aliases
                    )
                }
                onCommit(result)
                dismiss()
            } catch {
                errorText = error.localizedDescription
            }
            isSaving = false
        }
    }
}
