import SwiftUI

/// Configuration view for extract_entities node.
/// Shows built-in entity types plus any user-defined types registered in the
/// library's entity-type registry (#874 / #1372). Users can add arbitrary
/// extraction targets (e.g. "fruit", "quotations") and remove custom ones.
struct ExtractEntitiesNodeConfig: View {
    @Binding var node: WorkflowNode

    @State private var entityTypes: Set<String> = ["people", "organizations", "locations", "dates"]
    @State private var includeContext: Bool = false
    @State private var customTypes: [LibraryEntityTypeItem] = []
    @State private var newTypeName: String = ""
    @State private var isAdding = false
    @State private var addError: String?

    private static let builtInTypes = ["people", "organizations", "locations", "dates", "events", "products"]

    private var allTypeKeys: [String] {
        let custom = customTypes.map(\.entityTypeKey)
        return (Self.builtInTypes + custom.filter { !Self.builtInTypes.contains($0) }).sorted()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            entityTypesSection
            ThinkingModePicker(node: $node)
            Toggle("Include Context", isOn: $includeContext)
                .font(.caption)
                .onChange(of: includeContext) { _, newValue in
                    writeConfig(key: "include_context", value: .bool(newValue))
                }
            Text("Shows surrounding text for each entity")
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .task { await loadRegistryTypes() }
        .onAppear { loadInitialState() }
    }

    // MARK: - Entity Types Section

    private var entityTypesSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Extraction Targets")
                .font(.caption)
                .foregroundColor(.secondary)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 6) {
                ForEach(allTypeKeys, id: \.self) { type in
                    HStack(spacing: 4) {
                        Toggle(type.capitalized.replacingOccurrences(of: "_", with: " "), isOn: Binding(
                            get: { entityTypes.contains(type) },
                            set: { isOn in
                                if isOn { entityTypes.insert(type) } else { entityTypes.remove(type) }
                                writeConfig(key: "entity_types",
                                            value: .array(entityTypes.sorted().map { .string($0) }))
                            }
                        ))
                        #if os(macOS)
                        .toggleStyle(.checkbox)
                        .font(.caption)
                        #else
                        .font(.caption)
                        #endif

                        if !Self.builtInTypes.contains(type) {
                            Button {
                                Task { await removeCustomType(type) }
                            } label: {
                                Image(systemName: "minus.circle")
                                    .foregroundStyle(.secondary)
                                    .font(.caption2)
                            }
                            .buttonStyle(.plain)
                            .help("Remove \(type) from this library's extraction targets")
                        }
                    }
                }
            }

            HStack(spacing: 6) {
                TextField("Add target (e.g. fruit, quotes)", text: $newTypeName)
                    .font(.caption)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { Task { await addCustomType() } }

                Button {
                    Task { await addCustomType() }
                } label: {
                    if isAdding {
                        ProgressView().controlSize(.mini)
                    } else {
                        Image(systemName: "plus.circle.fill")
                    }
                }
                .buttonStyle(.plain)
                .disabled(newTypeName.trimmingCharacters(in: .whitespaces).isEmpty || isAdding)
                .accessibilityLabel("Add extraction target")
                .help("Register this extraction target in your library")
            }

            if let err = addError {
                Text(err)
                    .font(.caption2)
                    .foregroundStyle(.red)
            }
        }
    }

    // MARK: - Actions

    private func loadRegistryTypes() async {
        guard let svc = LibraryManager.shared.globalLibrary?.entityService else { return }
        do {
            let types = try await svc.listLibraryEntityTypes()
            await MainActor.run { customTypes = types; addError = nil }
        } catch {
            // Surface the failure instead of rendering empty chips (#1672).
            await MainActor.run { addError = "Couldn't load entity types: \(error.localizedDescription)" }
        }
    }

    private func addCustomType() async {
        let key = newTypeName.trimmingCharacters(in: .whitespaces)
            .lowercased()
            .replacingOccurrences(of: " ", with: "_")
        guard !key.isEmpty,
              let svc = LibraryManager.shared.globalLibrary?.entityService else { return }
        isAdding = true
        addError = nil
        defer { isAdding = false }
        do {
            let added = try await svc.addLibraryEntityType(key: key)
            await MainActor.run {
                if !customTypes.contains(where: { $0.entityTypeKey == added.entityTypeKey }) {
                    customTypes.append(added)
                }
                entityTypes.insert(added.entityTypeKey)
                writeConfig(key: "entity_types",
                            value: .array(entityTypes.sorted().map { .string($0) }))
                newTypeName = ""
            }
        } catch {
            await MainActor.run { addError = error.localizedDescription }
        }
    }

    private func removeCustomType(_ key: String) async {
        guard let svc = LibraryManager.shared.globalLibrary?.entityService else { return }
        do {
            try await svc.removeLibraryEntityType(key: key)
            await MainActor.run {
                // Only drop the chip once the backend confirms the delete (#1672).
                customTypes.removeAll { $0.entityTypeKey == key }
                entityTypes.remove(key)
                writeConfig(key: "entity_types",
                            value: .array(entityTypes.sorted().map { .string($0) }))
                addError = nil
            }
        } catch {
            await MainActor.run { addError = "Couldn't remove \(key): \(error.localizedDescription)" }
        }
    }

    private func writeConfig(key: String, value: AnyCodableValue) {
        if node.config == nil { node.config = [:] }
        node.config?[key] = value
    }

    private func loadInitialState() {
        if let configValue = node.config?["entity_types"],
           case .array(let types) = configValue {
            entityTypes = Set(types.compactMap {
                if case .string(let typeStr) = $0 { return typeStr }
                return nil
            })
        }
        if let configValue = node.config?["include_context"],
           case .bool(let context) = configValue {
            includeContext = context
        }
    }
}
