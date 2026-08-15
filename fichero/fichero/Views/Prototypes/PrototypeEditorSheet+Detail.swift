import FicheroAPIClient
import SwiftUI

// MARK: - Prototype editor: the detail form

extension PrototypeEditorSheet {
    @ViewBuilder
    var detailPane: some View {
        if selectedPrototype != nil || creatingKey != nil {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    identityForm
                    attributeRowsSection
                    inheritedSection
                }
                .padding(14)
            }
        } else {
            ContentUnavailableView(
                "No Type Selected",
                systemImage: "tag",
                description: Text("Select a type on the left, or create one.")
            )
        }
    }

    @ViewBuilder
    private var identityForm: some View {
        Grid(alignment: .leading, verticalSpacing: 8) {
            if creatingKey != nil {
                GridRow {
                    Text("Key").foregroundStyle(.secondary)
                    TextField("diary_entry", text: creatingKeyBinding)
                        .textFieldStyle(.roundedBorder)
                        .help("Stable identifier — lowercase, underscores; cannot change later")
                }
            }
            GridRow {
                Text("Label").foregroundStyle(.secondary)
                TextField("Diary Entry", text: $draftLabel)
                    .textFieldStyle(.roundedBorder)
            }
            GridRow {
                Text("Parent").foregroundStyle(.secondary)
                Picker("", selection: $draftParentKey) {
                    Text("None").tag("")
                    ForEach(possibleParents, id: \.key) { proto in
                        Text(proto.label).tag(proto.key)
                    }
                }
                .labelsHidden()
                .fixedSize()
                .onChange(of: draftParentKey) { _, _ in
                    Task { await loadInheritedPreview() }
                }
            }
            GridRow {
                Text("Color").foregroundStyle(.secondary)
                HStack(spacing: 6) {
                    TextField("#8B5CF6", text: $draftColor)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 100)
                    if let color = Color(hex: draftColor) {
                        Circle().fill(color).frame(width: 14, height: 14)
                    }
                }
            }
        }

        HStack {
            Spacer()
            Button(creatingKey != nil ? "Create" : "Save") {
                Task { await save() }
            }
            .disabled(draftLabel.trimmingCharacters(in: .whitespaces).isEmpty || isSaving)
        }
    }

    /// A prototype cannot be its own parent; deeper cycle detection is the
    /// resolver's job and surfaces as its 422 on save.
    private var possibleParents: [Components.Schemas.ClassificationValue] {
        prototypes.filter { $0.key != selectedKey }
    }

    private var creatingKeyBinding: Binding<String> {
        Binding(
            get: { creatingKey ?? "" },
            set: { creatingKey = $0 }
        )
    }

    // MARK: - Attribute declarations

    @ViewBuilder
    private var attributeRowsSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Attributes")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
            ForEach($draftAttributes) { $draft in
                PrototypeAttributeRow(draft: $draft) {
                    draftAttributes.removeAll { $0.id == draft.id }
                }
            }
            Button {
                draftAttributes.append(.init())
            } label: {
                Label("Add Attribute", systemImage: "plus.circle")
            }
            .buttonStyle(.plain)
            .foregroundStyle(.tint)
            .font(.callout)
        }
    }

    @ViewBuilder
    private var inheritedSection: some View {
        let ownNames = Set(draftAttributes.map(\.name))
        let inherited = inheritedDeclarations.filter { !ownNames.contains($0.name) }
        if !inherited.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text("Inherited from “\(draftParentKey)”")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                ForEach(inherited) { decl in
                    HStack(spacing: 6) {
                        Text(decl.name).font(.callout)
                        Text(decl.type)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        if let role = decl.role {
                            Text(role)
                                .font(.caption2)
                                .padding(.horizontal, 4)
                                .background(Color.accentColor.opacity(0.15))
                                .clipShape(Capsule())
                        }
                        Spacer(minLength: 0)
                    }
                }
            }
        }
    }

    @MainActor
    func loadInheritedPreview() async {
        inheritedDeclarations = []
        guard let entityService, !draftParentKey.isEmpty else { return }
        do {
            inheritedDeclarations = try await entityService
                .resolvedPrototypeDeclarations(key: draftParentKey)
        } catch {
            errorText = error.localizedDescription
        }
    }

    // MARK: - Save

    @MainActor
    func save() async {
        guard let entityService else { return }
        isSaving = true
        defer { isSaving = false }
        errorText = nil
        let parent = draftParentKey.isEmpty ? nil : draftParentKey
        let color = draftColor.isEmpty ? nil : draftColor
        do {
            if let newKey = creatingKey {
                let key = newKey.trimmingCharacters(in: .whitespaces)
                guard !key.isEmpty else {
                    errorText = "A key is required"
                    return
                }
                let created = try await entityService.createDocumentPrototype(
                    key: key,
                    label: draftLabel,
                    parentKey: parent,
                    color: color,
                    attributes: draftAttributes
                )
                await reload(selecting: created.key)
            } else if let proto = selectedPrototype, let id = proto.id {
                try await entityService.updateDocumentPrototype(
                    valueId: id,
                    label: draftLabel,
                    parentKey: parent,
                    color: color,
                    attributes: draftAttributes
                )
                await reload(selecting: proto.key)
            }
        } catch {
            errorText = error.localizedDescription
        }
    }
}
