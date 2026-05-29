import FicheroAPIClient
import SwiftUI

/// Sheet for merging one or more entities into a primary absorbing entity (#1135).
/// Calls POST /api/kg/entity-curation/merge on confirm.
struct EntityMergeSheet: View {
    /// The entity that will absorb others.
    let absorbingEntity: Components.Schemas.KnowledgeEntity
    /// All entities available to absorb (excludes absorbingEntity itself).
    let allEntities: [Components.Schemas.KnowledgeEntity]
    let onMerge: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var selectedIds: Set<String> = []
    @State private var mergedDescription: String = ""
    @State private var isSaving = false
    @State private var errorText: String?

    private var availableEntities: [Components.Schemas.KnowledgeEntity] {
        allEntities.filter {
            $0.id != absorbingEntity.id && $0.mergedIntoId == nil
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            Form {
                Section {
                    Text("Absorbing entity: **\(absorbingEntity.canonicalName)**")
                        .font(.body)
                    Text(
                        "Selected entities will be merged into it. "
                        + "Their claims will be re-pointed and their aliases merged."
                    )
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Entities to Absorb") {
                    if availableEntities.isEmpty {
                        Text("No other entities available.")
                            .foregroundStyle(.secondary)
                            .font(.caption)
                    } else {
                        ForEach(availableEntities, id: \.id) { entity in
                            let id = entity.id ?? ""
                            Toggle(isOn: Binding(
                                get: { selectedIds.contains(id) },
                                set: { isOn in
                                    if isOn { selectedIds.insert(id) } else { selectedIds.remove(id) }
                                }
                            )) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(entity.canonicalName)
                                    if let aliases = entity.aliases, !aliases.isEmpty {
                                        Text(aliases.joined(separator: ", "))
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }
                        }
                    }
                }

                Section("Merged Description (optional)") {
                    TextField("Override absorbing entity description…", text: $mergedDescription)
                }

                if let errorText {
                    Section {
                        Text(errorText)
                            .foregroundStyle(.red)
                            .font(.caption)
                    }
                }
            }
            .formStyle(.grouped)

            Divider()

            HStack {
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Spacer()
                Button("Merge \(selectedIds.count) entit\(selectedIds.count == 1 ? "y" : "ies")", action: merge)
                    .keyboardShortcut(.defaultAction)
                    .disabled(selectedIds.isEmpty || isSaving)
            }
            .padding()
        }
        .frame(width: 460, height: 440)
    }

    private func merge() {
        guard let library = LibraryManager.shared.globalLibrary,
              let absorberId = absorbingEntity.id else { return }
        isSaving = true
        errorText = nil
        Task {
            do {
                let desc = mergedDescription.trimmingCharacters(in: .whitespacesAndNewlines)
                _ = try await library.entityService.mergeEntities(
                    absorbingEntityId: absorberId,
                    absorbedEntityIds: Array(selectedIds),
                    mergedDescription: desc.isEmpty ? nil : desc
                )
                onMerge()
                dismiss()
            } catch {
                errorText = error.localizedDescription
                isSaving = false
            }
        }
    }
}
