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

    /// Persist edited content. `nil` → read-only (the `AttributedTextEditor`
    /// becomes non-editable, matching `ArtifactPanel`'s `onSave == nil` path).
    var onSave: ((Artifact, String) async -> Void)?

    /// Delete this artifact. `nil` hides the trash affordance.
    var onDelete: ((Artifact) -> Void)?

    var body: some View {
        Group {
            if let artifact {
                ScrollView {
                    ArtifactPanel(
                        kind: .artifact(artifact),
                        // The detail always shows its body — there's no sibling
                        // competing for height, so default to expanded.
                        defaultExpanded: true,
                        onDelete: onDelete.map { delete in { delete(artifact) } },
                        onSave: onSave.map { save in
                            { content in await save(artifact, content) }
                        }
                    )
                    .padding(.horizontal, 4)
                    .frame(maxWidth: .infinity, alignment: .top)
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
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.vertical, 32)
    }
}
