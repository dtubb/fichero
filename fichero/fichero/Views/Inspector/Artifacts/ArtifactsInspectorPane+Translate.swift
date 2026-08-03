import SwiftUI

// MARK: - Translate (#4306)

extension ArtifactsInspectorPane {
    /// The library this pane's services were injected from, matched by service
    /// IDENTITY — so actions run against the library that owns `document`.
    /// Reaching for `globalLibrary` here was #4306: translate ran against the
    /// global db, where a non-global document does not exist, and errored.
    ///
    /// #4461 folded this pane's hand-rolled match into the shared
    /// `library(owningService:)`, so every document-scoped surface asks the
    /// same question the same way — and dropped the `?? globalLibrary` tail
    /// with it. That tail read as harmless because the global library matches
    /// itself, but it also meant an unresolvable pane silently translated
    /// against the global database instead of saying it could not.
    var owningLibrary: LibraryManager.LibraryReference? {
        libraryManager.library(owningService: artifactService)
    }

    func translate(to language: TranslationLanguage) {
        guard let actionsService = owningLibrary?.actionsService else {
            actionError = "No library available to translate."
            return
        }
        isTranslating = true
        Task { @MainActor in
            defer { isTranslating = false }
            do {
                _ = try await actionsService.invokeAction(
                    name: "artifact.translate",
                    params: ArtifactTranslateActionParams(
                        documentId: document.id,
                        targetLang: language.code,
                        sourceLang: "auto",
                        provider: nil
                    )
                )
                actionError = nil
                // The new translation artifact also arrives via the change stream;
                // reload so it shows immediately in the list.
                await store.reload()
            } catch {
                actionError = "Couldn't translate: \(error.localizedDescription)"
            }
        }
    }

}
