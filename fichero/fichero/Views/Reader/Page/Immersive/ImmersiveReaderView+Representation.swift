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
        return .imageStorageDisplay(documentId: document.id)
    }

    var currentRepresentationLabel: String {
        if representationKey == "diplomatic" { return "Diplomatic" }
        if representationKey.hasPrefix("lang:") {
            let lang = String(representationKey.dropFirst("lang:".count))
            return translations.first(where: { $0.lang == lang })?.displayName
                ?? (Locale.current.localizedString(forLanguageCode: lang)?.capitalized ?? lang.uppercased())
        }
        return "Source"
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
        }
    }
}
