import SwiftUI

// MARK: - Page Content Pane (#1189)

struct PageContentPaneEditState {
    var isEditing = false
    var draftContent = ""
    var savedContent = ""

    mutating func synchronize(with content: String) {
        guard !isEditing else { return }
        draftContent = content
        savedContent = content
    }

    mutating func beginEditing(from content: String) {
        draftContent = content
        savedContent = content
        isEditing = true
    }

    mutating func markSaved() {
        savedContent = draftContent
    }

    var hasUnsavedChanges: Bool {
        draftContent != savedContent
    }

    func shouldSaveOnBlur(isFocused: Bool) -> Bool {
        isEditing && !isFocused && hasUnsavedChanges
    }
}

/// Displays the transcription / page_content text for the selected page document.
struct PageContentPane: View {
    let document: Document?

    @EnvironmentObject private var documentService: DocumentServiceGenerated
    @EnvironmentObject private var documentStore: DocumentStore
    @State private var editState = PageContentPaneEditState()
    @State private var isSaving = false
    @State private var saveError: String?
    @FocusState private var isEditorFocused: Bool

    private var pageDoc: Document? {
        guard let doc = document, doc.docType == .page else { return nil }
        return doc
    }

    private var pageContent: String {
        pageDoc?.pageContent ?? ""
    }

    var body: some View {
        VStack(spacing: 0) {
            MiniToolbar {
                Text("Content")
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundStyle(.secondary)
                Spacer(minLength: 0)
                if pageDoc != nil {
                    if isSaving {
                        ProgressView()
                            .controlSize(.small)
                    }
                    Button(editState.isEditing ? "Done" : "Edit") {
                        toggleEditing()
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .disabled(isSaving)
                }
            }
            Divider()
            if let doc = pageDoc {
                if editState.isEditing {
                    TextEditor(text: $editState.draftContent)
                        .font(.system(.body, design: .serif))
                        .lineSpacing(4)
                        .scrollContentBackground(.hidden)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                        .padding(8)
                        .focused($isEditorFocused)
                        .onChange(of: isEditorFocused) { _, focused in
                            if editState.shouldSaveOnBlur(isFocused: focused) {
                                commitDraft(exitAfterSave: false)
                            }
                        }
                } else if let content = doc.pageContent, !content.isEmpty {
                    ScrollView {
                        Text(content)
                            .font(.system(.body, design: .serif))
                            .lineSpacing(4)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .textSelection(.enabled)
                            .padding(12)
                    }
                } else {
                    emptyState(
                        title: "No content",
                        subtitle: "Switch to Edit to add notes or a transcription."
                    )
                }
            } else {
                emptyState(
                    title: "Select a page",
                    subtitle: "Choose a PDF page to view or edit its content."
                )
            }

            if let saveError {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                    Text(saveError)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(.orange.opacity(0.08))
            }
        }
        .background(Color(.textBackgroundColor))
        .onAppear {
            editState.synchronize(with: pageContent)
        }
        .onChange(of: pageDoc?.id ?? "") { _, _ in
            isSaving = false
            saveError = nil
            editState = PageContentPaneEditState()
            editState.synchronize(with: pageContent)
        }
        .onChange(of: pageContent) { _, newContent in
            guard !editState.isEditing else { return }
            editState.synchronize(with: newContent)
        }
        .onChange(of: editState.isEditing) { _, isEditing in
            if isEditing {
                isEditorFocused = true
            }
        }
    }

    private func toggleEditing() {
        guard let doc = pageDoc else { return }
        saveError = nil

        if editState.isEditing {
            commitDraft(exitAfterSave: true)
        } else {
            editState.beginEditing(from: doc.pageContent ?? "")
            isEditorFocused = true
        }
    }

    private func commitDraft(exitAfterSave: Bool) {
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

    @ViewBuilder
    private func emptyState(title: String, subtitle: String) -> some View {
        VStack(spacing: 8) {
            Spacer()
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(subtitle)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(12)
    }
}
