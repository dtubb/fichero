import SwiftUI

/// The enhancement controls on the Source pane while it only shows the page (`image.enhance.editor-enhance-is-the-new-step`,
/// `image.enhance.batch-preview-undo`, `image.enhance.show-through-only-verso`, #6362): Enhance in one click (the window's Undo takes
/// it back), Clean up the folder (the editor's sheet), and, for a show-through-only page, its sentence and Include / Leave Out.
struct SourcePaneImageControls: View {
    let document: Document

    @Environment(APIClient.self) private var apiClient
    @Environment(DocumentStore.self) private var documentStore
    @Environment(StorageService.self) private var storageService
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?
    @State private var cleanupStep: CleanupStep?
    @State private var failure: String?

    var body: some View {
        let items = SourcePaneImageActions.items(for: document)
        VStack(alignment: .trailing, spacing: 6) {
            if ShowThroughOnly.isMarked(document) {
                ShowThroughPageRow(page: document, documents: documentStore.currentDocuments, store: documentStore, failure: $failure)
                    .padding(8)
                    .background(.bar, in: RoundedRectangle(cornerRadius: 8))
                    .frame(maxWidth: 360)
            }
            if !items.isEmpty {
                HStack(spacing: 8) {
                    if items.contains(.enhance) {
                        Button("Enhance", systemImage: "wand.and.stars") { Task { await enhance() } }
                            .accessibilityIdentifier("sourcePane.enhance")
                            .help("Auto Enhance this page: local contrast, handwritten (⌘Z takes it back)")
                    }
                    if items.contains(.cleanUpFolder) {
                        Menu("Clean up the folder", systemImage: "square.stack.3d.up") {
                            ForEach(CleanupStep.all) { step in Button(step.title) { cleanupStep = step } }
                        }
                        .fixedSize()
                        .accessibilityIdentifier("sourcePane.cleanUpFolder")
                        .help("Apply a cleanup step to every page of this folder, after a look at three of them")
                    }
                }
                .controlSize(.small)
                .padding(6)
                .background(.bar, in: RoundedRectangle(cornerRadius: 8))
            }
            if let failure { Text(failure).font(.caption).foregroundStyle(.red) }
        }
        .padding(10)
        .sheet(item: $cleanupStep) { step in
            if let folderId = document.parentId {
                let pages = documentStore.currentDocuments.filter { $0.fileType == .image || $0.docType == .page }
                ImageCleanupBatchSheet(
                    model: ImageCleanupBatchModel(
                        folderId: folderId, step: step, pages: pages.map { CleanupPageRef(id: $0.id, name: $0.name) },
                        service: ImageCleanupBatchService(apiClient: apiClient)),
                    onChanged: { pages.forEach { storageService.invalidateImageCache(for: $0.id) } })
            }
        }
    }

    private func enhance() async {
        guard let actionsService = actionStore?.actionsService else { return }
        do {
            try await AuditedAction.run(
                "image.enhance", params: ImageEnhanceRequest(documentId: document.id), actionName: "Auto Enhance",
                actionsService: actionsService, steps: windowSteps,
                afterChange: { storageService.invalidateImageCache(for: document.id) })
            failure = nil
        } catch {
            failure = "Couldn't enhance: \(error.localizedDescription)"
        }
    }
}

extension View {
    /// The enhancement controls over the Source pane's page, for an image page only.
    func sourcePaneImageControls(_ document: Document, enabled: Bool) -> some View {
        overlay(alignment: .topTrailing) {
            if enabled { SourcePaneImageControls(document: document) }
        }
    }
}

#Preview("Source pane enhancement controls") {
    SourcePaneImageControls(document: Document(parentId: "folder", fileType: .image, name: "IMG_0007"))
        .environment(APIClient())
        .environment(DocumentStore.preview)
        .frame(width: 420, height: 120)
}
