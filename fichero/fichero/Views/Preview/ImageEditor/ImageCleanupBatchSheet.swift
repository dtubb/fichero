import SwiftUI

/// The sheet for a cleanup step copied to the whole folder (`image.enhance.batch-preview-undo`, #6192): three pages before and
/// after, one Apply, then the pages changed each with Undo, and Undo all for the batch.
struct ImageCleanupBatchSheet: View {
    @State var model: ImageCleanupBatchModel
    var undoPage: (String, String) async -> Bool = { _, _ in true }
    var onChanged: () -> Void = {}
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Apply \(model.step.title) to this folder").font(.headline)
            Text(model.summary).font(.callout).foregroundStyle(.secondary)
                .accessibilityIdentifier("imageCleanupBatch.summary")
            HStack(alignment: .top, spacing: 8) {
                ForEach(model.preview.samples) { page in
                    VStack {
                        pair(page)
                        Text(page.name).font(.caption).lineLimit(1)
                    }
                    .accessibilityIdentifier("imageCleanupBatch.preview")
                }
            }
            if !model.appliedPages.isEmpty { appliedList }
            if case .failed(let words) = model.phase { Text(words).font(.caption).foregroundStyle(.red) }
            buttons
        }
        .padding(20)
        .frame(width: 560)
        .task { await model.loadPreview() }
    }

    private func pair(_ page: CleanupPreviewPage) -> some View {
        HStack(spacing: 4) {
            picture(page.before)
            picture(page.after)
        }
    }

    @ViewBuilder private func picture(_ data: Data) -> some View {
        if let image = PlatformImage(data: data) {
            Image(platformImage: image).resizable().scaledToFit().frame(maxHeight: 140)
        }
    }

    private var appliedList: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Applied to \(model.appliedPages.count) pages:").font(.caption)
            ScrollView {
                ForEach(model.appliedPages) { page in
                    HStack {
                        Text(page.name).font(.callout).lineLimit(1)
                        Spacer()
                        Button("Undo") {
                            Task { if await undoPage(page.id, batchId) { model.pageUndone(page.id); onChanged() } }
                        }
                        .controlSize(.small)
                        .accessibilityIdentifier("imageCleanupBatch.undoPage")
                    }
                }
            }
            .frame(maxHeight: 120)
        }
    }

    private var batchId: String {
        if case .applied(let id) = model.phase { return id }
        return ""
    }

    private var buttons: some View {
        HStack {
            if case .applied = model.phase {
                Button("Undo All") { Task { await model.undoAll(); onChanged() } }
                    .accessibilityIdentifier("imageCleanupBatch.undoAll")
            }
            Spacer()
            Button(model.phase == .ready || model.phase == .loading ? "Cancel" : "Done") { dismiss() }
                .keyboardShortcut(.cancelAction)
            if model.phase == .ready {
                Button("Apply to \(model.preview.pages) Pages") {
                    Task { await model.apply(); onChanged() }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(model.preview.pages == 0)
                .accessibilityIdentifier("imageCleanupBatch.apply")
            }
        }
    }
}

extension ImageEditorView {
    /// The toolbar's menu of cleanup steps that can be copied to the folder: shown for a page that sits in one.
    @ViewBuilder var cleanupToFolderMenu: some View {
        if compareMode == .single, activeDocument.parentId != nil {
            Menu {
                ForEach(CleanupStep.all) { step in
                    Button(step.title) { cleanupBatchStep = step }
                }
            } label: {
                Label("Clean up the folder", systemImage: "wand.and.stars")
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Apply a cleanup step to every page of this folder, after a look at three of them")
            .accessibilityIdentifier("imageEditCleanupFolder")
        }
    }
}

extension ImageEditorView {
    /// One page leaves the batch, the others keep it: the audited action the folder-correction sheet uses too.
    func undoCleanupPage(_ documentId: String, batchId: String) async -> Bool {
        guard let actionsService = actionStore?.actionsService else { return false }
        do {
            try await AuditedAction.run(
                "image.undo_batch_page", params: ImageUndoBatchPageRequest(documentId: documentId, batchId: batchId),
                actionName: "Undo for One Page", actionsService: actionsService, steps: windowSteps)
            return true
        } catch {
            return false
        }
    }
}

private struct PreviewCleanupService: ImageCleanupBatching {
    func preview(folderId: String, step: CleanupStep) async throws -> CleanupPreview { CleanupPreview(pages: 12, samples: []) }
    func apply(folderId: String, step: CleanupStep) async throws -> String { "batch" }
    func undo(batchId: String) async throws {}
}

#Preview("Apply a cleanup step to a folder") {
    ImageCleanupBatchSheet(model: ImageCleanupBatchModel(
        folderId: "folder", step: CleanupStep.all[0], pages: [.init(id: "p1", name: "Page 1")],
        service: PreviewCleanupService()))
}
