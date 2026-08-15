import FicheroAPIClient
import SwiftUI

// MARK: - Prototype editor (datasets Stage 1, slice B)

/// Library-level editor for document prototypes (Tinderbox-style classes):
/// create/edit/delete prototypes and their TYPED attribute declarations with
/// renderer roles, with the parent chain's inherited attributes previewed
/// read-only. A sheet, not a sidebar mode (spec §3) — reached from the
/// prototype picker, so the affordance lives where the need appears.
struct PrototypeEditorSheet: View {
    let entityService: EntityService?
    /// Called on dismiss so the presenting picker can reload its list.
    var onDismiss: () -> Void = {}

    @Environment(\.dismiss) private var dismiss

    @State var prototypes: [Components.Schemas.ClassificationValue] = []
    @State var selectedKey: String?
    @State var errorText: String?
    @State var isSaving = false
    @State private var confirmingDelete = false

    // Detail draft state, seeded from the selected prototype.
    @State var draftLabel = ""
    @State var draftParentKey = ""
    @State var draftColor = ""
    @State var draftAttributes: [EntityService.PrototypeAttributeDraft] = []
    /// Chain-merged declarations of the PARENT — the inheritance preview.
    @State var inheritedDeclarations: [EntityService.AttributeDeclaration] = []
    /// Non-nil while creating: the key being typed for the new prototype.
    @State var creatingKey: String?

    var selectedPrototype: Components.Schemas.ClassificationValue? {
        prototypes.first { $0.key == selectedKey }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 0) {
                prototypeList
                    .frame(width: 190)
                Divider()
                detailPane
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
            Divider()
            footer
        }
        .frame(minWidth: 660, minHeight: 460)
        .task { await reload() }
        .onChange(of: selectedKey) { _, _ in seedDraft() }
        .onDisappear { onDismiss() }
    }

    private var prototypeList: some View {
        List(selection: $selectedKey) {
            ForEach(prototypes, id: \.key) { proto in
                HStack(spacing: 6) {
                    PrototypeBadge(proto: proto)
                    Spacer(minLength: 0)
                    if proto.isBuiltin == true {
                        Image(systemName: "lock")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                            .help("Built-in prototype — editable, not deletable")
                    }
                }
                .tag(proto.key)
            }
        }
        .listStyle(.inset)
        .overlay {
            if prototypes.isEmpty && creatingKey == nil {
                ContentUnavailableView(
                    "No Types",
                    systemImage: "tag",
                    description: Text("Create a document type to declare its attributes.")
                )
            }
        }
    }

    private var footer: some View {
        HStack(spacing: 12) {
            Button {
                startCreate()
            } label: {
                Image(systemName: "plus")
            }
            .help("New document type")
            .accessibilityLabel("New document type")

            Button {
                confirmingDelete = true
            } label: {
                Image(systemName: "minus")
            }
            .accessibilityLabel("Delete the selected type")
            .disabled(selectedPrototype == nil || selectedPrototype?.isBuiltin == true)
            .help("Delete the selected type")
            .confirmationDialog(
                "Delete “\(selectedPrototype?.label ?? "")”?",
                isPresented: $confirmingDelete
            ) {
                Button("Delete", role: .destructive) {
                    Task { await deleteSelected() }
                }
            } message: {
                Text("Documents keep their attribute values; the declarations go.")
            }

            if let errorText {
                Text(errorText)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .lineLimit(2)
            }
            Spacer()
            if isSaving { ProgressView().controlSize(.small) }
            Button("Done") { dismiss() }
                .keyboardShortcut(.defaultAction)
        }
        .padding(10)
    }

    // MARK: - Data

    @MainActor
    func reload(selecting key: String? = nil) async {
        guard let entityService else { return }
        do {
            prototypes = try await entityService.listDocumentPrototypes()
                .sorted { $0.label.localizedCaseInsensitiveCompare($1.label) == .orderedAscending }
            errorText = nil
            if let key {
                selectedKey = key
            } else if selectedKey == nil {
                selectedKey = prototypes.first?.key
            }
            seedDraft()
        } catch {
            errorText = error.localizedDescription
        }
    }

    func seedDraft() {
        creatingKey = nil
        guard let proto = selectedPrototype else {
            draftLabel = ""
            draftParentKey = ""
            draftColor = ""
            draftAttributes = []
            inheritedDeclarations = []
            return
        }
        draftLabel = proto.label
        draftParentKey = proto.parentKey ?? ""
        draftColor = proto.color ?? ""
        draftAttributes = EntityService.attributeDrafts(from: proto)
        Task { await loadInheritedPreview() }
    }

    private func startCreate() {
        selectedKey = nil
        creatingKey = ""
        draftLabel = ""
        draftParentKey = ""
        draftColor = ""
        draftAttributes = []
        inheritedDeclarations = []
    }

    @MainActor
    private func deleteSelected() async {
        guard let entityService, let proto = selectedPrototype, let id = proto.id else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            try await entityService.deleteDocumentPrototype(valueId: id)
            selectedKey = nil
            await reload()
        } catch {
            errorText = error.localizedDescription
        }
    }
}

/// One editable typed-attribute declaration row.
struct PrototypeAttributeRow: View {
    @Binding var draft: EntityService.PrototypeAttributeDraft
    let onDelete: () -> Void

    var body: some View {
        HStack(spacing: 6) {
            TextField("name", text: $draft.name)
                .textFieldStyle(.roundedBorder)
                .frame(width: 120)
            Picker("", selection: $draft.type) {
                ForEach(EntityService.PrototypeSchema.attributeTypes, id: \.self) { Text($0).tag($0) }
            }
            .labelsHidden()
            .fixedSize()
            Picker("", selection: $draft.role) {
                Text("no role").tag("")
                ForEach(EntityService.PrototypeSchema.attributeRoles, id: \.self) { Text($0).tag($0) }
            }
            .labelsHidden()
            .fixedSize()
            .help("Renderer role: which views (timeline, map, cards…) key on this attribute")
            if draft.type.contains("select") {
                TextField("options, comma-separated", text: $draft.optionsCSV)
                    .textFieldStyle(.roundedBorder)
            } else {
                TextField("default", text: $draft.defaultValue)
                    .textFieldStyle(.roundedBorder)
            }
            Toggle("req", isOn: $draft.required)
                .toggleStyle(.checkbox)
                .help("Required")
            Button {
                onDelete()
            } label: {
                Image(systemName: "minus.circle")
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .accessibilityLabel("Remove attribute \(draft.name)")
        }
    }
}
