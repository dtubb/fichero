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
    /// The entities selected in a table for Merge (#5129, ruled 2026-09-27): the person picks which
    /// one survives, `absorbingEntity` only proposes it, and the others are the ones absorbed.
    /// Empty when the sheet opens on one entity ("Merge Into…").
    var survivorChoices: [Components.Schemas.KnowledgeEntity] = []
    let onMerge: () -> Void

    @Environment(\.dismiss) private var dismiss
    @Environment(EntityService.self) private var entityService: EntityService?

    /// The library this sheet is MUTATING, resolved from the service it was
    /// handed, by object identity. See `merge()` for why it is the library and
    /// not a service that is resolved here.
    private var owningLibrary: LibraryManager.LibraryReference? {
        entityService.flatMap { LibraryManager.shared.library(owningService: $0) }
    }
    @State private var selectedIds: Set<String> = []
    /// The survivor the person chose from `survivorChoices`; nil keeps `absorbingEntity`.
    @State private var chosenSurvivorId: String?
    @State private var mergedDescription: String = ""
    @State private var isSaving = false
    @State private var errorText: String?

    private var survivorId: String? { chosenSurvivorId ?? absorbingEntity.id }

    private var survivor: Components.Schemas.KnowledgeEntity {
        survivorChoices.first { $0.id == survivorId } ?? absorbingEntity
    }

    private var availableEntities: [Components.Schemas.KnowledgeEntity] {
        (survivorChoices.isEmpty ? allEntities : survivorChoices).filter {
            $0.id != survivorId && $0.mergedIntoId == nil
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            Form {
                Section {
                    if survivorChoices.count >= 2 {
                        Picker("Keep", selection: Binding(
                            get: { survivorId ?? "" },
                            set: { chosenSurvivorId = $0 }
                        )) {
                            ForEach(survivorChoices, id: \.id) { entity in
                                Text(entity.canonicalName).tag(entity.id ?? "")
                            }
                        }
                    } else {
                        Text("Absorbing entity: **\(survivor.canonicalName)**")
                            .font(.body)
                    }
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
        // From a table selection every other selected entity is absorbed, whichever one is kept.
        .task(id: survivorId) {
            guard !survivorChoices.isEmpty else { return }
            selectedIds = Set(availableEntities.compactMap(\.id))
        }
    }

    private func merge() {
        guard let absorberId = survivorId else { return }
        // MERGE is the verb Daniel's dedupe program is built on, and it ran
        // against the RESERVED-id library: a merge is a write, so this was not
        // an empty view but a change to a graph the user was not looking at.
        // The library is resolved from the service this sheet was handed, by
        // object identity — `actionsService` is deliberately not in
        // `libraryServiceEnvironment` and nothing reads it from the
        // environment, so going through the owning library is the route, and
        // adding a 30th entry to that list for one call site is the worse
        // trade. nil fails visibly: a sheet that cannot name the library it is
        // about to change must not guess one (#4306/#4461).
        guard let library = owningLibrary else {
            errorText = "This window has no library to merge the entities in."
            return
        }
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

// #5110: this sheet was complete and unreachable, so nobody had ever looked at it.
// Now that the entity table presents it, it gets a preview — this project's way of
// verifying a surface renders (RenderPreview), and the only verification available
// for declarative wiring that no unit test can reach.
//
// No EntityService in the environment: that is the deliberate honest state. The
// sheet's service is optional precisely so a host injecting none fails VISIBLY
// rather than guessing a library (#4306/#4461), and the preview shows the form the
// user would see before any service is consulted.
#Preview("Merge — three candidates") {
    EntityMergeSheet(
        absorbingEntity: Components.Schemas.KnowledgeEntity(
            id: "ent-survivor",
            canonicalName: "Ana María Restrepo"
        ),
        allEntities: [
            Components.Schemas.KnowledgeEntity(id: "ent-survivor", canonicalName: "Ana María Restrepo"),
            Components.Schemas.KnowledgeEntity(id: "ent-dup-1", canonicalName: "A. M. Restrepo"),
            Components.Schemas.KnowledgeEntity(id: "ent-dup-2", canonicalName: "Ana Restrepo"),
            Components.Schemas.KnowledgeEntity(id: "ent-dup-3", canonicalName: "Restrepo, Ana María")
        ],
        onMerge: {}
    )
}

// The empty case renders differently and is the one a user hits by accident, so it
// gets its own preview rather than being assumed from the populated one.
#Preview("Merge — nothing to absorb") {
    EntityMergeSheet(
        absorbingEntity: Components.Schemas.KnowledgeEntity(id: "ent-only", canonicalName: "Bogotá"),
        allEntities: [
            Components.Schemas.KnowledgeEntity(id: "ent-only", canonicalName: "Bogotá")
        ],
        onMerge: {}
    )
}

// #5129: Merge from the entities table. The selection arrives as the survivor choices; the
// proposal is the richest row, and the Keep picker lets the person choose another.
#Preview("Merge — choose which to keep") {
    let duplicates = [
        Components.Schemas.KnowledgeEntity(id: "ent-a", canonicalName: "Ana María Restrepo"),
        Components.Schemas.KnowledgeEntity(id: "ent-b", canonicalName: "A. M. Restrepo"),
        Components.Schemas.KnowledgeEntity(id: "ent-c", canonicalName: "Ana Restrepo")
    ]
    EntityMergeSheet(
        absorbingEntity: duplicates[0],
        allEntities: duplicates,
        survivorChoices: duplicates,
        onMerge: {}
    )
}
