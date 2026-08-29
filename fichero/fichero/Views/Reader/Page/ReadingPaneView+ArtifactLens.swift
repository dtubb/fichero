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

/// The artifact types the reader can read a document THROUGH — the text
/// representations (Daniel, 2026-08-29: Content / Transcript / Translate…).
/// A closed display list over the types that actually exist; structural
/// artifact types (segmentation, grouping, entities, text_geometry) are not
/// readings of the text and never appear in the switcher.
enum ReaderRepresentation {
    /// Artifact types that ARE text representations, in display order.
    static let textTypes = [
        "transcription", "normalized_text", "translation",
        "transliteration", "markdown", "html", "summary", "conversion"
    ]

    static func title(for type: String) -> String {
        switch type {
        case "transcription": return "Transcript"
        case "translation": return "Translation"
        case "normalized_text": return "Normalized"
        case "transliteration": return "Transliteration"
        case "markdown": return "Markdown"
        case "html": return "HTML"
        case "summary": return "Summary"
        case "conversion": return "Conversion"
        default: return type.capitalized
        }
    }

    /// The distinct representation types present in a scope's artifacts, in
    /// the fixed display order — file-scope so tests can call it directly.
    static func availableTypes(in artifactTypes: [String]) -> [String] {
        let present = Set(artifactTypes)
        return textTypes.filter { present.contains($0) }
    }
}

extension ReadingPaneView {

    /// The head's representation switcher (Daniel, 2026-08-29): Content plus
    /// each representation type this document's scope actually has. Picking
    /// one re-requests the SAME WebKit page with `?representation=` — one
    /// renderer, several readings. Hidden when there is nothing to switch to.
    @ViewBuilder
    var readerRepresentationControl: some View {
        if !readerRepresentationChoices.isEmpty {
            Menu {
                Button {
                    readerRepresentation = nil
                } label: {
                    if readerRepresentation == nil {
                        Label("Content", systemImage: "checkmark")
                    } else {
                        Text("Content")
                    }
                }
                Divider()
                ForEach(readerRepresentationChoices, id: \.self) { type in
                    Button {
                        readerRepresentation = type
                    } label: {
                        if readerRepresentation == type {
                            Label(ReaderRepresentation.title(for: type), systemImage: "checkmark")
                        } else {
                            Text(ReaderRepresentation.title(for: type))
                        }
                    }
                }
            } label: {
                Text(readerRepresentation.map { ReaderRepresentation.title(for: $0) } ?? "Content")
                    .font(.caption)
                    .foregroundStyle(readerRepresentation == nil ? Color.secondary : Color.accentColor)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Read this document as its content or one of its representations")
            .accessibilityIdentifier("readerRepresentationSwitcher")
        }
    }

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
        readerRepresentation = nil
        readerRepresentationChoices = []
        guard let doc = effectiveDocument,
              let service = LibraryManager.shared
                  .getLibrary(id: LibraryManager.shared.currentLibraryId ?? LibraryManager.globalLibraryId)?
                  .artifactService
        else { return }
        // ONE fetch answers both head controls: the whole scope's artifacts
        // (pages included) drive the representation switcher; the document's
        // OWN artifacts drive the per-artifact lens, as before.
        guard let artifacts = try? await service.getArtifacts(
            forDocumentId: doc.id, includeDescendants: true
        ) else { return }
        readerRepresentationChoices = ReaderRepresentation.availableTypes(
            in: artifacts.map(\.artifactType)
        )
        let formatter = RelativeDateTimeFormatter()
        artifactLensChoices = artifacts
            .filter { $0.documentId == doc.id }
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
