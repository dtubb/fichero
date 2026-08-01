import SwiftUI

// MARK: - Translate (#4306)

extension ArtifactsInspectorPane {
    /// The library this pane's services were injected from, matched by service
    /// IDENTITY — so actions run against the library that owns `document`.
    /// Reaching for `globalLibrary` here was #4306: translate ran against the
    /// global db, where a non-global document does not exist, and errored.
    /// The fallback survives only for the global library, where it is the
    /// same object. Siblings of this reach are tracked in #4461.
    var owningLibrary: LibraryManager.LibraryReference? {
        libraryManager.openLibraries.first { $0.artifactService === artifactService }
            ?? libraryManager.globalLibrary
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
