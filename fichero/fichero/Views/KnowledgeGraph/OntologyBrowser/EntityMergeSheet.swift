import FicheroAPIClient
import SwiftUI

/// Sheet for merging one or more entities into a primary absorbing entity (#1135).
///
/// On confirm this routes through the audited action choke point —
/// `POST /api/actions/invoke` with `name: "entity.merge"` (#1848 exhibit A) —
/// so the UI merge button runs the *same* named, audited action the chat agent,
/// App Intents, and tests use. The `invokeAction` central seam records the
/// returned `audit_id` on the per-library `LastAction` to seed ⌘Z
/// (`audit/{id}/undo`). The observable change stream still emits `entity.merged`,
/// so the list refresh is unchanged.
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
                // Route through the audited action choke point (#1848): same
                // named `entity.merge` action the chat agent + tests invoke.
                // Reuse the OpenAPI-generated params schema so the wire body
                // matches the backend Pydantic model exactly (rule #4).
                let params = Components.Schemas.EntityMergeRequest(
                    absorbingEntityId: absorberId,
                    absorbedEntityIds: Array(selectedIds),
                    mergedDescription: desc.isEmpty ? nil : desc
                )
                _ = try await library.actionsService.invokeAction(
                    name: "entity.merge",
                    params: params
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
