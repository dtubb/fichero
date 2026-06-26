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

    /// Shared selection holder the rows write to.
    @Bindable var focused: FocusedArtifact

    /// Open the selected artifact in a separate, draggable window. `nil` hides
    /// the affordance (e.g. if a host doesn't support the detached scene).
    var onOpenInWindow: (() -> Void)?

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
        List(selection: $focused.id) {
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
        // Keep the resolved snapshot in sync with selection changes so the
        // detached window (which reads the snapshot, not the store) follows.
        .onChange(of: focused.id) { _, _ in
            focused.resolve(in: store.items)
        }
        // And keep it current when the store reloads (workflow re-run, live
        // edit echoed back through the change-stream) without the selection id
        // itself changing.
        .onChange(of: store.items) { _, items in
            focused.resolve(in: items)
        }
    }

    /// One selectable row, tagged by artifact id, with an "Open in Window"
    /// context action. Extracted from the `ForEach` body so each expression
    /// stays cheap for the type-checker.
    @ViewBuilder
    private func row(for artifact: Artifact) -> some View {
        ArtifactRow(artifact: artifact)
            .tag(artifact.id)
            .contextMenu {
                if let onOpenInWindow {
                    Button("Open in Window") {
                        focused.select(artifact.id, in: store.items)
                        onOpenInWindow()
                    }
                }
            }
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "sparkles")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No artifacts yet")
                .font(.callout)
            Text("Run a workflow to generate transcriptions, catalogues, or summaries.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(.horizontal, 16)
    }
}

/// One lightweight artifact row — icon, title, provenance subtitle, and a
/// small trailing badge. Deliberately renders no content body (that's the
/// detail's job), so a long document's many artifacts stay scannable.
private struct ArtifactRow: View {
    let artifact: Artifact

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
        var parts: [String] = []
        if let provider = artifact.provider, !provider.isEmpty { parts.append(provider) }
        if let model = artifact.model, !model.isEmpty { parts.append(model) }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}
