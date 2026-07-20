import SwiftUI

extension ImmersiveReaderView {
    /// Fetch the current page's `translation` artifacts and index them by
    /// language (#3329). One entry per language (first wins). Reaches the service
    /// via the window's library (the reader isn't in the artifact-service
    /// environment). If the persisted selection points at a language that's no
    /// longer present, fall back to Source.
    func loadTranslations() async {
        guard let service = LibraryManager.shared.getLibrary(id: windowState.libraryId)?.artifactService else {
            translations = []
            return
        }
        do {
            let artifacts = try await service.getArtifacts(forDocumentId: document.id, type: "translation")
            var seen = Set<String>()
            translations = artifacts.compactMap { artifact -> TranslationRep? in
                guard let data = artifact.data,
                      let lang = data["target_lang"]?.value as? String,
                      let content = artifact.content,
                      seen.insert(lang).inserted else { return nil }
                return TranslationRep(
                    lang: lang,
                    content: content,
                    provider: artifact.provider,
                    model: artifact.model,
                    reviewed: artifact.reviewed
                )
            }
        } catch {
            translations = []
        }
        if representationKey.hasPrefix("lang:") {
            let lang = String(representationKey.dropFirst("lang:".count))
            if !translations.contains(where: { $0.lang == lang }) {
                representationKey = "source"
            }
        }
    }
}
