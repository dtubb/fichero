import SwiftUI

/// A native `List(selection:)` of artifacts (#2003, EPIC #2002).
///
/// Replaces the "stacked text boxes" overview: each row is a *lightweight*
/// summary (type icon + title + provider/model + a small version/reviewed
/// badge), NOT the artifact's full content. Selecting a row drives the shared
/// `FocusedArtifact`, which the detail view (inline and detached window)
/// observes — so the detail "follows selection".
///
/// Conventions honoured:
/// - Native `List(selection:)`, not a hand-rolled `VStack` of tappable rows,
///   so single-click selection, keyboard arrows, and multi-window selection
///   sync all come for free (and we don't fight `List` with custom gestures —
///   see the `no-wholesale-list-rerender` rule).
/// - Semantic system fonts only (`.body`, `.caption`), so rows scale with the
///   system text size.
/// - Rows key off the stable `Artifact.id`, so a single artifact's update
///   re-renders that row in place rather than reloading the whole list.
struct ArtifactListView: View {
    /// The reactive data source — the document-scoped store (#1997). The list
    /// reads `store.items`; it never fetches independently.
    let store: ArtifactStore
    let inspectedDocument: Document
    let documentsById: [String: Document]

    /// Shared selection holder the rows write to.
    @Bindable var focused: FocusedArtifact

    /// Open the selected artifact in a separate, draggable window. `nil` hides
    /// the affordance (e.g. if a host doesn't support the detached scene).
    var onOpenInWindow: (() -> Void)?

    /// Native multi-selection set the `List` drives (#2519). Single-click selects
    /// one (and the detail follows via `focused`); ⇧/⌘-click extend; ⌫ / the
    /// context-menu "Delete" remove the whole selection. Kept in sync with the
    /// shared `focused` id below so detail-follow and multi-window selection
    /// still work — we don't fight `List(selection:)` with custom gestures.
    @State private var selectedIDs: Set<String> = []
    @State private var artifactsToDelete: [Artifact] = []
    @State private var showingDeleteConfirmation = false

    /// Sort: group raw + cleaned pairs together (people / people_clean) by base
    /// type with the cleaned canonical entry first, then newest-first within a
    /// type. Mirrors `DocumentInspectorContentV2.sortedArtifacts` so the list
    /// order matches what the old stacked view showed.
    private var sortedArtifacts: [Artifact] {
        store.items.sorted {
            let aBase = baseType(of: $0.artifactType)
            let bBase = baseType(of: $1.artifactType)
            if aBase != bBase { return aBase < bBase }
            let aClean = $0.artifactType.hasSuffix("_clean")
            let bClean = $1.artifactType.hasSuffix("_clean")
            if aClean != bClean { return aClean }
            return $0.createdAt > $1.createdAt
        }
    }

    private func baseType(of artifactType: String) -> String {
        artifactType.hasSuffix("_clean")
            ? String(artifactType.dropLast("_clean".count))
            : artifactType
    }

    var body: some View {
        List(selection: $selectedIDs) {
            ForEach(sortedArtifacts) { artifact in
                row(for: artifact)
            }
        }
        .listStyle(.inset)
        .overlay {
            if store.items.isEmpty {
                emptyState
            }
        }
        #if os(macOS)
        .onDeleteCommand(perform: promptDeleteSelection)
        #endif
        .alert("Delete Artifacts?", isPresented: $showingDeleteConfirmation) {
            Button("Cancel", role: .cancel) {}
            Button("Delete", role: .destructive) {
                let selection = artifactsToDelete
                Task { await deleteArtifacts(selection) }
            }
        } message: {
            Text(deletionPrompt)
        }
        .onAppear {
            // Seed the multi-selection from whatever the shared focus already holds.
            if let id = focused.id { selectedIDs = [id] }
        }
        // Selection → shared focus: the detail follows a single selection; during
        // a multi-select (for delete) keep the last single focus rather than
        // jumping. The detached window reads the resolved snapshot, so resolve too.
        .onChange(of: selectedIDs) { _, ids in
            let newFocus = ArtifactSelection.focusedID(for: ids, current: focused.id)
            if newFocus != focused.id {
                focused.select(newFocus, in: store.items)
            } else {
                focused.resolve(in: store.items)
            }
        }
        // Shared focus → selection: another window (or the detail) changing the
        // focus reflects here. Guard prevents a feedback loop with the above.
        .onChange(of: focused.id) { _, id in
            if let id, !selectedIDs.contains(id) {
                selectedIDs = [id]
            }
            focused.resolve(in: store.items)
        }
        // And keep the snapshot current when the store reloads (workflow re-run,
        // live edit echoed back) without the selection id itself changing.
        .onChange(of: store.items) { _, items in
            focused.resolve(in: items)
        }
    }

    /// One selectable row, tagged by artifact id, with an "Open in Window"
    /// context action. Extracted from the `ForEach` body so each expression
    /// stays cheap for the type-checker.
    @ViewBuilder
    private func row(for artifact: Artifact) -> some View {
        ArtifactRow(
            artifact: artifact,
            provenance: ArtifactProvenance.display(
                for: artifact,
                inspectedDocument: inspectedDocument,
                documentsById: documentsById
            )
        )
            .tag(artifact.id)
            .contentShape(Rectangle())
            .onTapGesture(count: 2) {
                guard let onOpenInWindow else { return }
                focused.select(artifact.id, in: store.items)
                onOpenInWindow()
            }
            .contextMenu {
                if let onOpenInWindow {
                    Button("Open in Window") {
                        focused.select(artifact.id, in: store.items)
                        onOpenInWindow()
                    }
                }
                Button("Delete", role: .destructive) {
                    // Right-clicking a row outside the selection acts on that row;
                    // right-clicking within a multi-selection acts on the whole set.
                    let targets = selectedIDs.contains(artifact.id)
                        ? ArtifactSelection.resolve(selectedIDs, in: store.items)
                        : [artifact]
                    confirmDelete(targets)
                }
            }
    }

    // MARK: - Multi-select delete (#2519)

    private var deletionPrompt: String {
        let count = artifactsToDelete.count
        return count == 1
            ? "Delete this artifact? This can't be undone."
            : "Delete \(count) artifacts? This can't be undone."
    }

    private func promptDeleteSelection() {
        confirmDelete(ArtifactSelection.resolve(selectedIDs, in: store.items))
    }

    private func confirmDelete(_ targets: [Artifact]) {
        guard !targets.isEmpty else { return }
        artifactsToDelete = targets
        showingDeleteConfirmation = true
    }

    private func deleteArtifacts(_ targets: [Artifact]) async {
        guard !targets.isEmpty else { return }
        await store.delete(targets)
        // Drop the deleted ids from the selection; clear focus if it was deleted.
        let deletedIDs = Set(targets.map(\.id))
        selectedIDs.subtract(deletedIDs)
        if let id = focused.id, deletedIDs.contains(id) {
            focused.select(selectedIDs.first, in: store.items)
        }
        artifactsToDelete = []
    }

    private var emptyState: some View {
        // Standardized on ContentUnavailableView (#3039).
        ContentUnavailableView(
            "No artifacts yet",
            systemImage: "sparkles",
            description: Text("Run a workflow to generate transcriptions, catalogues, or summaries.")
        )
    }
}

/// Pure selection helpers for the artifacts browser (#2519), factored out so the
/// "delete acts on the FULL selection" and "detail follows a single selection"
/// rules are unit-testable without a `List`.
enum ArtifactSelection {
    /// The artifacts a selection set refers to, in `items` order. Ids not present
    /// in `items` (already deleted, stale) are dropped; an empty set → `[]`.
    static func resolve(_ ids: Set<String>, in items: [Artifact]) -> [Artifact] {
        items.filter { ids.contains($0.id) }
    }

    /// The id the detail should focus for a given selection: the sole element of
    /// a single selection, `nil` when empty, and the unchanged `current` while
    /// 2+ rows are multi-selected (so the detail doesn't jump during a batch
    /// delete).
    static func focusedID(for selection: Set<String>, current: String?) -> String? {
        if selection.isEmpty { return nil }
        if selection.count == 1 { return selection.first }
        return current
    }
}

/// One lightweight artifact row — icon, title, provenance subtitle, and a
/// small trailing badge. Deliberately renders no content body (that's the
/// detail's job), so a long document's many artifacts stay scannable.
private struct ArtifactRow: View {
    let artifact: Artifact
    let provenance: ArtifactProvenanceDisplay

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: artifact.artifactTypeIcon)
                .foregroundStyle(.secondary)
                .frame(width: 18)
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.body)
                    .lineLimit(1)
                if let subtitle {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }
            Spacer(minLength: 4)
            Text(artifact.createdAt, format: .relative(presentation: .named))
                .font(.caption2)
                .foregroundStyle(.tertiary)
                .lineLimit(1)
            if artifact.reviewed {
                Image(systemName: "checkmark.seal.fill")
                    .font(.caption)
                    .foregroundStyle(.green.opacity(0.7))
                    .help("Reviewed")
                    .accessibilityLabel("Reviewed")
            } else if let provider = artifact.provider, !provider.isEmpty {
                // AI-generated and not yet human-reviewed — mark it as an
                // instrument output, not vetted fact (#2151/#2152, #3325 step 4).
                Image(systemName: "sparkles")
                    .font(.caption2)
                    .foregroundStyle(.purple.opacity(0.7))
                    .help("AI-generated · not yet reviewed")
                    .accessibilityLabel("AI-generated, not reviewed")
            }
            if artifact.version > 1 {
                Text("v\(artifact.version)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(.quaternary, in: Capsule())
            }
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
    }

    /// Title-cased artifact type (e.g. `key_people` → "Key People"). Matches
    /// `ArtifactPanel.title`.
    private var title: String {
        artifact.artifactType
            .split(separator: "_")
            .map { $0.prefix(1).uppercased() + $0.dropFirst() }
            .joined(separator: " ")
    }

    private var subtitle: String? {
        provenance.rowSubtitle
    }
}
