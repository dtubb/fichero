import FicheroAPIClient
import OSLog
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Entities Tab: List Rows & Chrome
//
// Members here are `internal` (not `private`) where the core file's `body` or
// another `DocumentInspectorEntitiesTab+*.swift` extension references them — a
// same-type extension in a different file cannot see a `private` member.
// `entitiesToolbarStatusText`, `filterMenu`, `entityRow`, `entityNameView`, and
// `dropTargetHighlight` stay `private`: they are used only within this file.

extension DocumentInspectorEntitiesTab {
    var entitiesMiniToolbar: some View {
        InspectorBottomMiniToolbar(statusText: entitiesToolbarStatusText) {
            filterMenu

            Button {
                Task { await loadScopedEntities(force: true) }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .help("Reload entities")
            .accessibilityLabel("Reload entities")

            Button {
                showReconcile = true
            } label: {
                Image(systemName: "arrow.triangle.merge")
            }
            .buttonStyle(.plain)
            .help("Reconcile duplicate entities — choose a scope (folder or library)")
            .accessibilityLabel("Reconcile entities")

            if entitySelection.count > 1 {
                bulkActionMenu(title: "Approve", systemImage: "checkmark.circle", action: .approve)
                bulkActionMenu(title: "Reject", systemImage: "xmark.circle", action: .reject)
                bulkActionMenu(title: "Suppress", systemImage: "eye.slash", action: .suppress)
                mergeActionMenu(targetEntities: selectedEntities, menuTitle: "Merge")
                deleteActionButton(targetEntities: selectedEntities)
            }
        }
    }

    // `private`: only `entitiesMiniToolbar` (same file) reads this.
    private var entitiesToolbarStatusText: String {
        if let selectedEntity {
            return selectedEntity.canonicalName
        }
        return "\(scopedEntities.count) entities"
    }

    @ViewBuilder
    var entityDetailPane: some View {
        if let entity = selectedEntity {
            EntityDigestContent(entity: entity, entityService: entityService)
                .frame(minHeight: 180, maxHeight: .infinity)
        } else if entitySelection.count > 1 {
            ContentUnavailableView(
                "Multiple Entities Selected",
                systemImage: "person.2",
                description: Text("Select a single entity to inspect it below.")
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ContentUnavailableView(
                "No Entity Selected",
                systemImage: "person.crop.circle",
                description: Text("Select an entity above to inspect it below.")
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ViewBuilder
    var emptyVisibleGroupsState: some View {
        if hasActiveKindFilter {
            VStack(alignment: .leading, spacing: 6) {
                Text("Loaded \(scopedEntities.count) entities, but the current filter hides every kind.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button("Show all kinds") {
                    hiddenKindsCSV = ""
                }
                #if os(macOS)
                .buttonStyle(.plain)
                    .foregroundStyle(.tint)
                #endif
                .font(.caption)
            }
        } else {
            VStack(alignment: .leading, spacing: 6) {
                Label(
                    "Loaded \(scopedEntities.count) entities, but none mapped into a visible section.",
                    systemImage: "exclamationmark.triangle"
                )
                .font(.caption)
                .foregroundStyle(.orange)
                .padding(.horizontal)

                List(selection: $entitySelection) {
                    entityKindSection(kind: .other, entities: scopedEntities)
                }
                .listStyle(.inset)
                .frame(maxHeight: .infinity)
            }
        }
    }

    // `private`: only `entitiesMiniToolbar` (same file) reads this.
    private var filterMenu: some View {
        Menu {
            // Folder aggregation scope (#3450) — only meaningful for a folder.
            if isFolder {
                Section("Scope") {
                    Button {
                        includeChildren = false
                    } label: {
                        HStack {
                            Text("This folder only")
                            Spacer(minLength: 0)
                            if !includeChildren { Image(systemName: "checkmark") }
                        }
                    }
                    Button {
                        includeChildren = true
                    } label: {
                        HStack {
                            Text("Include children")
                            Spacer(minLength: 0)
                            if includeChildren { Image(systemName: "checkmark") }
                        }
                    }
                }
            }
            ForEach(EntityKind.displayOrder, id: \.self) { kind in
                let isHidden = hiddenKinds.contains(kind)
                Button {
                    setHidden(kind, hidden: !isHidden)
                } label: {
                    Label(kind.label, systemImage: isHidden ? "" : "checkmark")
                }
            }
            Divider()
            Button("Show all") { hiddenKindsCSV = "" }
            Button("Hide all") {
                hiddenKindsCSV = EntityKind.displayOrder
                    .map(\.rawValue)
                    .sorted()
                    .joined(separator: ",")
            }
        } label: {
            Image(systemName: hiddenKinds.isEmpty
                    ? "line.3.horizontal.decrease.circle"
                    : "line.3.horizontal.decrease.circle.fill")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Filter entity kinds")
        .accessibilityLabel("Filter entity kinds")
    }

    func entityKindSection(
        kind: EntityKind,
        entities: [Components.Schemas.KnowledgeEntity]
    ) -> some View {
        Section {
            ForEach(entities, id: \.stableInspectorId) { entity in
                entityRow(entity)
            }
        } header: {
            Label("\(kind.label.uppercased()) \(entities.count)", systemImage: kind.systemImage)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
        }
    }

    // `private`: only `entityKindSection` (same file) reads this.
    private func entityRow(
        _ entity: Components.Schemas.KnowledgeEntity
    ) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                entityNameView(for: entity)
                if let curationState = entity.curationState, curationState != .unreviewed {
                    EntityCurationBadge(state: curationState)
                }
                if let count = entity.sourceDocumentIds?.count, count > 1 {
                    Text("Includes children")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }
            if let aliases = entity.aliases, !aliases.isEmpty {
                Text(aliases.prefix(3).joined(separator: ", "))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            if let description = entity.description, !description.isEmpty {
                Text(description)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
        .background(dropTargetHighlight(for: entity))
        .inspectorListRowTarget()
        // Stable XCUITest hook (InspectorFlowsUITests): every entity row carries
        // this identifier so a UI test can assert the loaded entity list is
        // non-empty — the regression guard for the EntityService transport fix
        // (a document that used to show "0 entities" over the broken transport).
        .accessibilityIdentifier("inspector.entity.row")
        .tag(entity.stableInspectorId)
        .draggable(entityDragPayload(for: entity))
        .dropDestination(
            for: InspectorEntityDragID.self,
            action: { payloads, _ in
                handleEntityDrop(payloads: payloads, onto: entity)
            },
            isTargeted: dropTargetHandler(for: entity)
        )
        .simultaneousGesture(
            TapGesture(count: 2).onEnded { openEntity(entity) }
        )
        // Plain-click fallback (Daniel 2026-08-12: "you can't click on a list
        // item for an entity, you have to click on the left of the name") —
        // same seam as the sidebar's childPlainClickFallback: `.draggable`
        // claims the press over most of the row, so List(selection:) never
        // commits. Plain clicks select directly; shift/command clicks stay
        // with the List for range/toggle selection.
        .simultaneousGesture(plainClickSelectFallback(entity))
        .contextMenu { entityContextMenu(for: entity) }
        .help("Inspect \(entity.canonicalName)")
    }

    // `private`: only `entityRow` (same file) reads this.
    /// Dragging a row that belongs to the current multi-selection carries the
    /// WHOLE selection (Daniel 2026-08-13); a row outside it drags alone,
    /// matching Finder.
    private func entityDragPayload(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> InspectorEntityDragID {
        InspectorEntityDragID(
            id: entity.stableInspectorId,
            text: entity.canonicalName,
            selectedIds: entitySelection.contains(entity.stableInspectorId)
                ? Array(entitySelection)
                : []
        )
    }

    // `private`: only `entityRow` (same file) reads this.
    private func plainClickSelectFallback(
        _ entity: Components.Schemas.KnowledgeEntity
    ) -> some Gesture {
        TapGesture().onEnded {
            #if os(macOS)
            guard !NSEvent.modifierFlags.contains(.shift),
                  !NSEvent.modifierFlags.contains(.command) else { return }
            #endif
            entitySelection = [entity.stableInspectorId]
        }
    }

    // `private`: only `entityRow` (same file) reads this.
    /// Canonical name — double-click the name (or use the Rename context
    /// action) to swap in an inline TextField. Enter commits, Esc cancels.
    /// `highPriorityGesture` so the name's double-click beats the row's
    /// double-click-to-open. (#1865)
    @ViewBuilder
    private func entityNameView(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> some View {
        if renamingEntityId == entity.stableInspectorId {
            TextField("Name", text: $renameDraft)
                .textFieldStyle(.plain)
                .font(.caption.weight(.semibold))
                .focused($renameFieldFocused)
                .onSubmit { commitRename(for: entity) }
                #if os(macOS)
                .onExitCommand { cancelRename() }
                #endif
                .onAppear { renameFieldFocused = true }
        } else {
            // Plain, readable name — no link styling. The accent-underlined
            // button was unreadable when the row highlight inverted, and its
            // single-click search intercepted the row's hit target so only a
            // narrow strip selected. The name is now plain text: the whole row
            // selects (List + tag), double-click renames, and "Find in Library"
            // moved to the context menu.
            Text(entity.canonicalName)
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundStyle(.primary)
                .help("Double-click to rename \"\(entity.canonicalName)\"")
                .simultaneousGesture(
                    TapGesture(count: 2).onEnded { beginRename(entity) }
                )
        }
    }

    // `private`: only `entityRow` (same file) reads this.
    @ViewBuilder
    private func dropTargetHighlight(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> some View {
        RoundedRectangle(cornerRadius: 8)
            .fill(
                dropTargetEntityId == entity.stableInspectorId
                    ? Color.accentColor.opacity(0.14)
                    : Color.clear
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(
                        dropTargetEntityId == entity.stableInspectorId
                            ? Color.accentColor
                            : Color.clear,
                        lineWidth: 1
                    )
            )
            .allowsHitTesting(false)
    }
}
