import SwiftUI

/// Reconciliation scope (#3318): the USER explicitly chooses where to look for
/// duplicate entities. Within-folder and within-library ship now; cross-library
/// (#3527) and external-authority / Wikidata (#3528) are deferred and shown
/// disabled ("coming soon") so the full scope ladder is visible.
enum EntityReconciliationScope: String, CaseIterable, Identifiable {
    case folder
    case library
    case crossLibrary
    case external

    var id: String { rawValue }

    var title: String {
        switch self {
        case .folder: return "Folder"
        case .library: return "Library"
        case .crossLibrary: return "Cross-Library"
        case .external: return "External"
        }
    }

    var icon: String {
        switch self {
        case .folder: return "folder"
        case .library: return "books.vertical"
        case .crossLibrary: return "square.stack.3d.up"
        case .external: return "globe"
        }
    }

    /// Folder + Library are implemented; the wider scopes are deferred.
    var isAvailable: Bool { self == .folder || self == .library }

    /// Tooltip for the disabled scopes so the deferral is discoverable.
    var help: String {
        switch self {
        case .folder: return "Find duplicate entities within this document / folder"
        case .library: return "Find duplicate entities across the whole library"
        case .crossLibrary: return "Cross-library reconciliation — coming soon (#3527)"
        case .external: return "External authority (Wikidata / Wikipedia) — coming soon (#3528)"
        }
    }
}

/// User-driven entity reconciliation (#3318). The user chooses a scope, the
/// sheet lists the graph-context duplicate candidate PAIRS the engine returns
/// for that scope (`/api/kg/entity-curation/candidates`, Jaccard over
/// co-occurrence), and each pair merges via the shared `EntityStore.merge`
/// action (audited + undoable) — the same merge the per-entity "Possible
/// Duplicates" affordance uses (#3317). The system never merges automatically.
struct EntityReconciliationSheet: View {
    /// The document/folder in focus — the target of `.folder` scope.
    let documentId: String

    @Environment(EntityStore.self) private var entityStore
    @Environment(\.dismiss) private var dismiss

    @State private var scope: EntityReconciliationScope = .folder
    @State private var candidates: [EntityReconciliationCandidate] = []
    @State private var isLoading = false
    @State private var message: String?

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            scopeBar
            Divider()
            content
            Divider()
            footer
        }
        .frame(minWidth: 420, minHeight: 440)
        .task(id: scope) { await load() }
    }

    private var header: some View {
        HStack {
            Label("Reconcile Entities", systemImage: "arrow.triangle.merge")
                .font(.headline)
            if isLoading { ProgressView().controlSize(.small) }
            Spacer()
        }
        .padding(12)
    }

    /// The scope ladder as a row of selectable chips; cross-library / external
    /// render disabled ("coming soon") but visible (#3318).
    private var scopeBar: some View {
        HStack(spacing: 8) {
            ForEach(EntityReconciliationScope.allCases) { option in
                Button {
                    scope = option
                } label: {
                    Label(option.title, systemImage: option.icon)
                        .font(.caption)
                }
                .buttonStyle(.bordered)
                .tint(scope == option ? .accentColor : nil)
                .disabled(!option.isAvailable)
                .help(option.help)
            }
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    @ViewBuilder
    private var content: some View {
        if let message {
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(12)
        }
        if candidates.isEmpty && !isLoading {
            ContentUnavailableView(
                "No likely duplicates",
                systemImage: "checkmark.seal",
                description: Text("No duplicate entities were found in the \(scope.title.lowercased()) scope.")
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            List(candidates) { candidate in
                candidateRow(candidate)
            }
            .listStyle(.inset)
        }
    }

    @ViewBuilder
    private func candidateRow(_ candidate: EntityReconciliationCandidate) -> some View {
        HStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 1) {
                Text("\(candidate.entityAName)  ↔  \(candidate.entityBName)")
                    .font(.body).lineLimit(1)
                if let type = candidate.entityType {
                    Text(type.capitalized).font(.caption2).foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 8)
            Text("\(Int((candidate.jaccard * 100).rounded()))%")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(candidate.jaccard >= 0.7 ? Color.orange : .secondary)
                .help("Graph-context similarity (Jaccard)")
            Menu {
                Button("Keep \"\(candidate.entityAName)\"") { merge(candidate, keepA: true) }
                Button("Keep \"\(candidate.entityBName)\"") { merge(candidate, keepA: false) }
            } label: {
                Label("Merge", systemImage: "arrow.triangle.merge").font(.caption)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
        }
    }

    private var footer: some View {
        HStack {
            Text(candidates.isEmpty ? "" : "\(candidates.count) pair\(candidates.count == 1 ? "" : "s")")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button("Done") { dismiss() }
                .keyboardShortcut(.defaultAction)
        }
        .padding(12)
    }

    // MARK: - Data

    /// Load the graph-context candidate pairs for the chosen scope from the
    /// engine (`/api/kg/entity-curation/candidates`) via the store. Folder scope
    /// passes the focused document as `folder_id`; library scope passes none.
    private func load() async {
        guard scope.isAvailable else { candidates = []; return }
        isLoading = true
        defer { isLoading = false }
        message = nil
        do {
            candidates = try await entityStore.reconciliationCandidates(
                scope: scope == .folder ? "folder" : "library",
                folderId: scope == .folder ? documentId : nil
            )
        } catch {
            candidates = []
            message = "Couldn't load candidates: \(error.localizedDescription)"
        }
    }

    /// Merge a candidate pair, keeping A or B as the survivor (user's choice) via
    /// the shared audited/undoable `EntityStore.merge`.
    private func merge(_ candidate: EntityReconciliationCandidate, keepA: Bool) {
        let survivorId = keepA ? candidate.entityAId : candidate.entityBId
        let absorbedId = keepA ? candidate.entityBId : candidate.entityAId
        let survivorName = keepA ? candidate.entityAName : candidate.entityBName
        Task {
            do {
                try await entityStore.merge(absorbedIds: [absorbedId], into: survivorId)
                message = "Merged into \"\(survivorName)\"."
                await load()
            } catch {
                message = "Merge failed: \(error.localizedDescription)"
            }
        }
    }
}
