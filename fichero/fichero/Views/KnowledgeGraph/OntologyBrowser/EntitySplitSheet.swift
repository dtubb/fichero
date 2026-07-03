import FicheroAPIClient
import SwiftUI

/// Sheet for splitting previously-merged entities back out from a primary entity (#1135).
/// Shows all entities where `mergedIntoId == primary.id` and lets the user
/// select which to un-merge. Also lets the user move aliases back.
/// Calls POST /api/kg/entity-curation/split on confirm.
struct EntitySplitSheet: View {
    let primaryEntity: Components.Schemas.KnowledgeEntity
    /// Full entity list — filtered client-side for those merged into primary.
    let allEntities: [Components.Schemas.KnowledgeEntity]
    let onSplit: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var selectedSplitIds: Set<String> = []
    @State private var selectedAliases: Set<String> = []
    @State private var isSaving = false
    @State private var errorText: String?

    private var mergedEntities: [Components.Schemas.KnowledgeEntity] {
        allEntities.filter { $0.mergedIntoId == primaryEntity.id }
    }

    var body: some View {
        VStack(spacing: 0) {
            Form {
                Section {
                    Text("Primary entity: **\(primaryEntity.canonicalName)**")
                    Text(
                        "Select entities to split off (un-merge). "
                        + "Their merged_into_id will be cleared, making them independent again."
                    )
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Merged Entities to Split Off") {
                    if mergedEntities.isEmpty {
                        Text("No merged entities — nothing to split.")
                            .foregroundStyle(.secondary)
                            .font(.caption)
                    } else {
                        ForEach(mergedEntities, id: \.id) { entity in
                            let id = entity.id ?? ""
                            Toggle(isOn: Binding(
                                get: { selectedSplitIds.contains(id) },
                                set: { isOn in
                                    if isOn { selectedSplitIds.insert(id) } else { selectedSplitIds.remove(id) }
                                }
                            )) {
                                Text(entity.canonicalName)
                            }
                        }
                    }
                }

                if let primaryAliases = primaryEntity.aliases, !primaryAliases.isEmpty {
                    Section("Aliases to Move Back") {
                        Text("Select aliases to remove from the primary and restore to split-off entities.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        ForEach(primaryAliases, id: \.self) { alias in
                            Toggle(isOn: Binding(
                                get: { selectedAliases.contains(alias) },
                                set: { isOn in
                                    if isOn { selectedAliases.insert(alias) } else { selectedAliases.remove(alias) }
                                }
                            )) {
                                Text(alias)
                                    .font(.body)
                            }
                        }
                    }
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
                Button("Split", action: split)
                    .keyboardShortcut(.defaultAction)
                    .disabled((selectedSplitIds.isEmpty && selectedAliases.isEmpty) || isSaving)
            }
            .padding()
        }
        // Mac-only fixed size; iPhone/iPad sheets size to the screen (#2802).
        #if os(macOS)
        .frame(width: 460, height: 440)
        #endif
    }

    private func split() {
        guard let library = LibraryManager.shared.globalLibrary,
              let primaryId = primaryEntity.id else { return }
        isSaving = true
        errorText = nil
        Task {
            do {
                _ = try await library.entityService.splitEntity(
                    primaryEntityId: primaryId,
                    splitOffEntityIds: Array(selectedSplitIds),
                    aliasesToMove: Array(selectedAliases)
                )
                onSplit()
                dismiss()
            } catch {
                errorText = error.localizedDescription
                isSaving = false
            }
        }
    }
}
