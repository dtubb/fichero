import SwiftUI

// MARK: - The reader's ARTIFACT lens (artifact-compare P1, Daniel 2026-08-26:
// "the reader can show different artifacts — an original, diplomatic, and
// translation — user can choose"). The pane head's controls slot gains a
// picker over the shown document's artifacts; picking one renders THAT
// artifact's text in place of the live transcript. Two panes side by side,
// each pinned to a different artifact, IS the comparison — the pane system
// already does the hard part (per the artifact-compare design ruling:
// compare splits the current window).

/// What the reader pane is pinned to instead of the live transcript.
struct ReaderArtifactLens: Equatable {
    let artifactId: String
    let label: String
}

extension ReadingPaneView {

    /// The head's artifact-lens control: a menu of this document's artifacts
    /// plus "Live Transcript" to return. Hidden entirely for documents with
    /// no artifacts — absent beats present-and-useless (#4421).
    @ViewBuilder
    var artifactLensControl: some View {
        if !artifactLensChoices.isEmpty {
            Menu {
                Button {
                    artifactLens = nil
                } label: {
                    if artifactLens == nil {
                        Label("Live Transcript", systemImage: "checkmark")
                    } else {
                        Text("Live Transcript")
                    }
                }
                Divider()
                ForEach(artifactLensChoices, id: \.artifactId) { choice in
                    Button {
                        artifactLens = choice
                    } label: {
                        if artifactLens == choice {
                            Label(choice.label, systemImage: "checkmark")
                        } else {
                            Text(choice.label)
                        }
                    }
                }
            } label: {
                Image(systemName: "doc.on.doc")
                    .foregroundStyle(artifactLens == nil ? Color.secondary : Color.accentColor)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help(artifactLens.map { "Showing artifact: \($0.label)" }
                ?? "Show one of this document's artifacts instead of the live transcript")
        }
    }

    /// Load the artifact choices for the shown document. Newest first, labeled
    /// "type · model · date" the way the inspector's list reads.
    func loadArtifactLensChoices() async {
        artifactLens = nil
        artifactLensChoices = []
        guard let doc = effectiveDocument,
              let service = LibraryManager.shared
                  .getLibrary(id: LibraryManager.shared.currentLibraryId ?? LibraryManager.globalLibraryId)?
                  .artifactService
        else { return }
        guard let artifacts = try? await service.getArtifacts(
            forDocumentId: doc.id, includeDescendants: false
        ) else { return }
        let formatter = RelativeDateTimeFormatter()
        artifactLensChoices = artifacts
            .sorted { $0.createdAt > $1.createdAt }
            .prefix(12)
            .map { artifact in
                let when = formatter.localizedString(for: artifact.createdAt, relativeTo: Date())
                return ReaderArtifactLens(
                    artifactId: artifact.id,
                    label: "\(artifact.artifactType) · \(when)"
                )
            }
    }
}

/// The pinned artifact's text, full height, reader typography. Fetches the
/// FULL artifact (list rows carry truncated content).
struct ArtifactLensContentView: View {
    let lens: ReaderArtifactLens

    @Environment(ArtifactService.self) private var artifactService: ArtifactService?
    @State private var text: String?
    @State private var failed = false

    var body: some View {
        ScrollView {
            if let text {
                Text(text)
                    .font(.body)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
            } else if failed {
                ContentUnavailableView(
                    "Couldn’t Load Artifact",
                    systemImage: "exclamationmark.triangle",
                    description: Text(lens.label)
                )
                .padding(.top, 40)
            } else {
                ProgressView().padding(.top, 40)
            }
        }
        .background(Color(.textBackgroundColor))
        .task(id: lens.artifactId) {
            failed = false
            text = nil
            guard let artifactService,
                  let full = try? await artifactService.getArtifact(id: lens.artifactId),
                  let content = full.content, !content.isEmpty
            else {
                failed = true
                return
            }
            text = content
        }
    }
}
