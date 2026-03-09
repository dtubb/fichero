import SwiftUI

/// Content tab for DocumentInspector showing extracted text content
struct DocumentInspectorContentTab: View {
    let document: Document
    @EnvironmentObject private var documentService: DocumentServiceGenerated
    @EnvironmentObject private var documentStore: DocumentStore

    @State private var draftContent: String = ""
    @State private var isSaving = false
    @State private var saveError: String?

    private var originalContent: String {
        document.pageContent ?? ""
    }

    private var hasChanges: Bool {
        draftContent != originalContent
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Text")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                Spacer()

                if !draftContent.isEmpty {
                    Button(
                        action: { copyToClipboard(draftContent) },
                        label: {
                            Image(systemName: "doc.on.doc")
                        }
                    )
                    .buttonStyle(.plain)
                    .help("Copy to clipboard")
                }

                if hasChanges {
                    Button("Revert") {
                        draftContent = originalContent
                        saveError = nil
                    }
                    .buttonStyle(.borderless)
                    .disabled(isSaving)

                    Button("Save") {
                        saveContent()
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isSaving)
                }
            }

            ZStack(alignment: .topLeading) {
                TextEditor(text: $draftContent)
                    .font(.body)
                    .scrollContentBackground(.hidden)
                    .padding(6)
                    .frame(minHeight: 220)
                    .background(Color(.textBackgroundColor))
                    .cornerRadius(6)
                    .disabled(isSaving)

                if draftContent.isEmpty {
                    Text("Add notes or edit extracted text...")
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 14)
                        .allowsHitTesting(false)
                }
            }

            if let saveError {
                Text(saveError)
                    .font(.caption)
                    .foregroundStyle(.red)
            } else if isSaving {
                HStack(spacing: 6) {
                    ProgressView()
                        .controlSize(.small)
                    Text("Saving...")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .onAppear {
            draftContent = originalContent
        }
        .onChange(of: document.id) { _, _ in
            draftContent = originalContent
            saveError = nil
        }
    }

    // MARK: - Clipboard

    private func copyToClipboard(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    // MARK: - Persistence

    private func saveContent() {
        guard !isSaving else { return }
        isSaving = true
        saveError = nil

        Task { @MainActor in
            do {
                let updated = try await documentService.updateDocument(
                    document.id,
                    pageContent: draftContent
                )
                documentStore.updateLocal(updated)
                documentStore.publish(.documentsUpdated(documentStore.currentDocuments))
            } catch {
                saveError = "Failed to save text: \(error.localizedDescription)"
            }
            isSaving = false
        }
    }
}
