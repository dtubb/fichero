import SwiftUI

extension ImmersiveReaderView {
    /// The canvas content for the chosen representation. Source is the storage
    /// page image; Diplomatic is the raw page_content; a `lang:xx` key shows that
    /// language's translation. All reuse existing DocumentCanvas cases — no
    /// parallel view. Falls back to Source if a selected translation is gone.
    var canvasContent: DocumentCanvas.Content {
        if representationKey == "diplomatic" {
            return .markdown(text: document.pageContent ?? "")
        }
        if representationKey.hasPrefix("lang:") {
            let lang = String(representationKey.dropFirst("lang:".count))
            if let translation = translations.first(where: { $0.lang == lang }) {
                return .markdown(text: translation.content)
            }
        }
        // A conversion rendition is an alternate view of the SAME page (#4329):
        // Markdown renders natively, HTML/SVG render in WebKit.
        if let rendition = currentRendition {
            return DocumentCanvas.renditionContent(for: rendition)
        }
        return .imageStorageDisplay(documentId: document.id)
    }

    var currentRepresentationLabel: String {
        if representationKey == "diplomatic" { return "Diplomatic" }
        if representationKey.hasPrefix("lang:") {
            let lang = String(representationKey.dropFirst("lang:".count))
            return translations.first(where: { $0.lang == lang })?.displayName
                ?? (Locale.current.localizedString(forLanguageCode: lang)?.capitalized ?? lang.uppercased())
        }
        if let rendition = currentRendition {
            return Self.renditionTitle(forFormat: renditionFormat(rendition))
        }
        return "Source"
    }

    // MARK: - Renditions (#4329)

    /// The conversion artifact the current representation key points at, if any.
    var currentRendition: Artifact? {
        guard representationKey.hasPrefix("rendition:") else { return nil }
        let id = String(representationKey.dropFirst("rendition:".count))
        return renditions.first { $0.id == id }
    }

    /// A rendition's format — the server stamp when present, sniffed otherwise
    /// (legacy conversion artifacts predate the stamp).
    func renditionFormat(_ artifact: Artifact) -> String {
        (artifact.data?["target_format"]?.value as? String)
            ?? DocumentCanvas.sniffRenditionFormat(artifact.content ?? "")
    }

    static func renditionTitle(forFormat format: String) -> String {
        switch format {
        case "markdown": return "Markdown"
        case "html": return "HTML"
        case "svg": return "SVG"
        default: return format.capitalized
        }
    }

    /// Fetch the page's `conversion` artifacts — newest per format — so the
    /// rendition switcher is populated from the page itself. Falls back to
    /// Source when a persisted selection no longer resolves.
    func loadRenditions() async {
        guard let service = LibraryManager.shared.getLibrary(id: windowState.libraryId)?.artifactService else {
            renditions = []
            return
        }
        do {
            let artifacts = try await service.getArtifacts(
                forDocumentId: document.id,
                type: "conversion",
                includeDescendants: false
            )
            var seenFormats = Set<String>()
            renditions = artifacts
                .sorted { $0.createdAt > $1.createdAt }
                .filter { artifact in
                    guard let content = artifact.content,
                          !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    else { return false }
                    return seenFormats.insert(renditionFormat(artifact)).inserted
                }
        } catch {
            renditions = []
        }
        if representationKey.hasPrefix("rendition:"), currentRendition == nil {
            representationKey = "source"
        }
    }

    /// The translation currently being viewed, if the selection is a language.
    var currentTranslation: TranslationRep? {
        guard representationKey.hasPrefix("lang:") else { return nil }
        let lang = String(representationKey.dropFirst("lang:".count))
        return translations.first { $0.lang == lang }
    }

    /// Provenance + AI badge for the shown representation (#3325 step 4). Only a
    /// translation is a derived AI representation here — Source/Diplomatic aren't.
    @ViewBuilder
    var provenanceCaption: some View {
        if let translation = currentTranslation {
            HStack(spacing: 6) {
                if !translation.reviewed {
                    Image(systemName: "sparkles").foregroundStyle(.purple)
                }
                Text(translation.reviewed ? "Translation" : "AI translation · unreviewed")
                if !translation.provenance.isEmpty {
                    Text("· \(translation.provenance)").foregroundStyle(.white.opacity(0.7))
                }
            }
            .font(.caption)
            .foregroundStyle(.white)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(.ultraThinMaterial, in: Capsule())
            .help("This representation is an AI-generated translation; review before citing.")
        } else if let rendition = currentRendition {
            HStack(spacing: 6) {
                Image(systemName: "sparkles").foregroundStyle(.purple)
                Text("AI rendition")
                if let provider = rendition.provider, !provider.isEmpty {
                    Text("· \(provider)\(rendition.model.map { " / \($0)" } ?? "")")
                        .foregroundStyle(.white.opacity(0.7))
                }
            }
            .font(.caption)
            .foregroundStyle(.white)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(.ultraThinMaterial, in: Capsule())
            .help("This representation was generated by a model from the page image; review before citing.")
        }
    }
}
