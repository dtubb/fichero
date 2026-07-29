import SwiftUI

/// The shared renderer for ONE artifact (#2003, EPIC #2002).
///
/// This is the detail surface shown both **inline** in the inspector (below
/// the `ArtifactListView`) and in the **detached window** torn off from it.
/// It deliberately reuses the existing `ArtifactPanel` — the component that
/// already owns RTF decode/encode (`ArtifactRichTextCodec`), the structured-
/// output JSON view, and the auto-saving `AttributedTextEditor` — rather than
/// reinventing artifact rendering (iterate-never-replace). The only thing
/// changing in Track B is that *one* of these renders at a time instead of a
/// vertical stack of them.
///
/// Editing is opt-in: pass `onSave`/`onDelete` for the inline inspector pane
/// (it has the services in scope); pass `nil` for the detached window, which
/// renders the artifact read-only (no service environment to plumb).
struct ArtifactDetailView: View {
    /// The artifact to render. `nil` shows the empty state (nothing selected).
    let artifact: Artifact?
    var provenance: ArtifactProvenanceDisplay? = nil
    var onOpenSource: (() -> Void)? = nil

    /// Persist edited content. `nil` → read-only (the `AttributedTextEditor`
    /// becomes non-editable, matching `ArtifactPanel`'s `onSave == nil` path).
    /// Returns nil on success or a user-facing error message on failure so
    /// the embedded panel keeps its draft dirty and retries (#4285).
    var onSave: ((Artifact, String) async -> String?)? = nil

    /// Delete this artifact. `nil` hides the trash affordance.
    var onDelete: ((Artifact) -> Void)? = nil

    var body: some View {
        Group {
            if let artifact {
                VStack(spacing: 0) {
                    if let provenance {
                        ArtifactProvenanceSection(
                            provenance: provenance,
                            onOpenSource: onOpenSource
                        )
                        Divider()
                    }

                    // #2495: the selected artifact's text must fill the full
                    // available inspector height — not sit at intrinsic height in a
                    // scroll view (the old "small bottom strip" whose size tracked
                    // panel content). `fillsHeight` makes the editor claim all
                    // remaining vertical space; every content path (editor /
                    // read-only Text / structured JSON) already scrolls internally,
                    // so no outer ScrollView is needed — and a nested ScrollView
                    // wrapping a maxHeight:.infinity editor would fight over height.
                    ArtifactPanel(
                        kind: .artifact(artifact),
                        // The detail always shows its body — there's no sibling
                        // competing for height, so default to expanded.
                        defaultExpanded: true,
                        fillsHeight: true,
                        onDelete: onDelete.map { delete in { delete(artifact) } },
                        onSave: onSave.map { save in
                            { content in await save(artifact, content) }
                        }
                    )
                    .padding(.horizontal, 4)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                }
            } else {
                emptyState
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "sparkles")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No artifact selected")
                .font(.callout)
            Text("Pick an artifact from the list to see its contents.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .padding(.vertical, 32)
    }
}

private struct ArtifactProvenanceSection: View {
    let provenance: ArtifactProvenanceDisplay
    var onOpenSource: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            LabeledContent("Source") {
                if let onOpenSource {
                    Button(action: onOpenSource) {
                        Text(provenance.sourceLabel)
                    }
                    // `.link` is macOS-only; `.borderless` is the cross-platform
                    // accent-tinted equivalent on iOS/iPadOS (iOS build gate).
                    #if os(macOS)
                    .buttonStyle(.link)
                    #else
                    .buttonStyle(.borderless)
                    #endif
                    .accessibilityLabel("Open artifact source")
                } else {
                    Text(provenance.sourceLabel)
                        .textSelection(.enabled)
                }
            }

            if let workflowLabel = provenance.workflowLabel {
                LabeledContent("Workflow") {
                    Text(workflowLabel)
                        .textSelection(.enabled)
                }
            }

            if let providerLabel = provenance.providerLabel {
                LabeledContent("Provider") {
                    Text(providerLabel)
                        .textSelection(.enabled)
                }
            }
        }
        .font(.caption)
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.35))
    }
}
