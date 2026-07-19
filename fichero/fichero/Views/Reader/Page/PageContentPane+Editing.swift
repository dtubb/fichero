import SwiftUI

// MARK: - Editing

extension PageContentPane {

    func toggleEditing() {
        guard pageDoc != nil else { return }
        saveError = nil

        if editState.isEditing {
            commitDraft(exitAfterSave: true)
        } else {
            editState.beginEditing(from: pageContent)
            isEditorFocused = true
        }
    }

    func commitDraft(exitAfterSave: Bool) {
        guard let doc = pageDoc else { return }
        guard editState.isEditing else { return }

        let draft = editState.draftContent
        guard draft != editState.savedContent else {
            if exitAfterSave {
                editState.isEditing = false
                isEditorFocused = false
            }
            saveError = nil
            return
        }

        guard !isSaving else { return }
        isSaving = true
        saveError = nil

        Task {
            let error = await persistPageContent(
                document: doc,
                content: draft,
                documentService: documentService,
                documentStore: documentStore
            )
            await MainActor.run {
                isSaving = false
                saveError = error
                if error == nil {
                    editState.markSaved()
                    if exitAfterSave {
                        editState.isEditing = false
                        isEditorFocused = false
                    }
                }
            }
        }
    }
}
