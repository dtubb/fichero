import FicheroAPIClient
import SwiftUI

/// Sheet for splitting previously-merged entities back out from a primary entity (#1135).
/// Shows all entities where `mergedIntoId == primary.id` and lets the user
/// select which to un-merge. Also lets the user move aliases back.
/// Runs the audited `entity.split` action on confirm (#5129).
struct EntitySplitSheet: View {
    let primaryEntity: Components.Schemas.KnowledgeEntity
    /// Full entity list — filtered client-side for those merged into primary.
    let allEntities: [Components.Schemas.KnowledgeEntity]
    let onSplit: () -> Void

    @Environment(\.dismiss) private var dismiss
    /// THIS sheet's entity service — the library it is MUTATING.
    ///
    /// It resolved `LibraryManager.shared.globalLibrary`, the library
    /// holding the RESERVED id rather than the one on screen, so the
    /// write landed in a graph the user was not looking at. Optional so
    /// a host that injects none fails VISIBLY: a sheet that cannot name
    /// the library it is about to change must not guess one
    /// (#4306/#4461).
    @Environment(EntityService.self) private var entityService: EntityService?
    @State private var selectedSplitIds: Set<String> = []
    @State private var selectedAliases: Set<String> = []
    @State private var isSaving = false
    @State private var errorText: String?

    private var mergedEntities: [Components.Schemas.KnowledgeEntity] {
        allEntities.filter { $0.mergedIntoId == primaryEntity.id }
    }

    var body: some View {
        NavigationStack {
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
            .navigationTitle("Split Entity")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            // Native sheet actions in the toolbar so they land in the right
            // place on iOS (nav bar) as well as macOS (#2806).
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Split", action: split)
                        .disabled((selectedSplitIds.isEmpty && selectedAliases.isEmpty) || isSaving)
                }
            }
        }
        // Mac-only fixed size; iPhone/iPad sheets size to the screen (#2802).
        #if os(macOS)
        .frame(width: 460, height: 440)
        #endif
    }

    private func split() {
        guard let primaryId = primaryEntity.id else { return }
        // The library from the service this sheet was handed, by object identity, as
        // EntityMergeSheet resolves it: its `actionsService` is the audited seam (#5129).
        guard let library = entityService.flatMap({ LibraryManager.shared.library(owningService: $0) }) else {
            errorText = "This window has no library to split the entity in."
            return
        }
        isSaving = true
        errorText = nil
        Task {
            do {
                // The audited `entity.split` action, not the curation route: the route handed back
                // no `audit_id`, so ⌘Z could not take a split back (#5129).
                try await library.actionsService.invokeAction(
                    name: "entity.split",
                    params: Components.Schemas.EntitySplitRequest(
                        primaryEntityId: primaryId,
                        splitOffEntityIds: Array(selectedSplitIds),
                        aliasesToMove: Array(selectedAliases)
                    )
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

// #5110: complete, unreachable until the entity table gained a door, and therefore
// never looked at. See the note on EntityMergeSheet's previews for why there is no
// EntityService here.
//
// Split is the INVERSE of a merge, not a division: it lists the entities whose
// `mergedIntoId` points at the primary and clears it. So the populated preview has
// to set that field — an entity list without it renders the empty state and would
// quietly prove nothing.
#Preview("Split — two merged in") {
    EntitySplitSheet(
        primaryEntity: Components.Schemas.KnowledgeEntity(
            id: "ent-primary",
            canonicalName: "Ana María Restrepo",
            aliases: ["A. M. Restrepo", "Ana Restrepo"]
        ),
        allEntities: [
            Components.Schemas.KnowledgeEntity(id: "ent-primary", canonicalName: "Ana María Restrepo"),
            Components.Schemas.KnowledgeEntity(
                id: "ent-absorbed-1",
                canonicalName: "A. M. Restrepo",
                mergedIntoId: "ent-primary"
            ),
            Components.Schemas.KnowledgeEntity(
                id: "ent-absorbed-2",
                canonicalName: "Ana Restrepo",
                mergedIntoId: "ent-primary"
            ),
            // Merged into something else — must NOT appear in this sheet.
            Components.Schemas.KnowledgeEntity(
                id: "ent-elsewhere",
                canonicalName: "Bogotá D.C.",
                mergedIntoId: "ent-other-primary"
            )
        ],
        onSplit: {}
    )
}

// The state a user reaches by right-clicking an entity nothing was merged into —
// which is most of them, and is why the menu item is always offered rather than
// gated on this pane's possibly folder-scoped rows.
#Preview("Split — nothing merged in") {
    EntitySplitSheet(
        primaryEntity: Components.Schemas.KnowledgeEntity(id: "ent-plain", canonicalName: "Medellín"),
        allEntities: [
            Components.Schemas.KnowledgeEntity(id: "ent-plain", canonicalName: "Medellín")
        ],
        onSplit: {}
    )
}
