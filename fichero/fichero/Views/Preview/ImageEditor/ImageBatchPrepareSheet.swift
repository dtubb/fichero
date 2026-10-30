import FicheroAPIClient
import SwiftUI

/// Pure rules for "Apply to the rest of this folder" (`prep.check.apply-correction-to-the-folder`): which correction a
/// page's chain holds that can be copied, and the words around it.
enum BatchPrepare {
    /// The last correction a person made on the page that the engine can copy as fractions or degrees: a squaring or a turn.
    static func correction(in operations: [ImageEditOperation]) -> BatchPrepareOperation? {
        for operation in operations.reversed() {
            let raw = operation.raw.value as? [String: Any] ?? [:]
            guard (raw["who"] as? String) == "person" || operation.opKind == "rotate" else { continue }
            let params = operation.params
            switch operation.opKind {
            case "square":
                if let quad = quad(params["quad"]) { return .init(kind: "square", quad: quad) }
            case "rotate":
                if let angle = number(params["angle"]) { return .init(kind: "rotate", angle: angle) }
            default:
                continue
            }
        }
        return nil
    }

    /// A JSON number as the chain holds it: Int or Double (a whole number decodes as an Int).
    static func number(_ value: Any?) -> Double? {
        if let double = value as? Double { return double }
        if let int = value as? Int { return Double(int) }
        return nil
    }

    static func quad(_ value: Any?) -> [[Double]]? {
        guard let corners = value as? [Any], corners.count == 4 else { return nil }
        let points = corners.compactMap { corner -> [Double]? in
            guard let pair = corner as? [Any], pair.count == 2, let across = number(pair[0]), let down = number(pair[1]) else { return nil }
            return [across, down]
        }
        return points.count == 4 ? points : nil
    }

    static func title(_ operation: BatchPrepareOperation) -> String {
        operation.kind == "square" ? "this page's four corners" : "a turn of \(Int(operation.angle ?? 0))°"
    }

    /// The sheet's sentence before it runs: how many pages it would change.
    static func summary(pages: Int, operation: BatchPrepareOperation) -> String {
        "Copies \(title(operation)) to \(pages) other page\(pages == 1 ? "" : "s") in this folder."
    }
}

/// The sheet: three previews (first, middle and last page with the correction applied, nothing written), Apply, and after it
/// a list of the pages changed, each with Undo for that page alone. The whole batch is the window's ⌘Z.
struct ImageBatchPrepareSheet: View {
    let folderId: String
    let sourceDocumentId: String
    let correction: BatchPrepareOperation
    let documents: [Document]
    var onApplied: ([String]) -> Void = { _ in }

    @Environment(APIClient.self) private var apiClient
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?
    @Environment(\.dismiss) private var dismiss
    @State private var previews: [Components.Schemas.BatchPreparePreviewItem] = []
    @State private var pages = 0
    @State private var batchId: String?
    @State private var applied: [String] = []
    @State private var failure: String?

    private var request: ImageBatchPrepareRequest {
        .init(folderId: folderId, operation: correction, sourceDocumentId: sourceDocumentId)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Apply to the rest of this folder").font(.headline)
            Text(BatchPrepare.summary(pages: pages, operation: correction))
                .font(.callout).foregroundStyle(.secondary)
                .accessibilityIdentifier("imageBatchPrepare.summary")
            HStack(alignment: .top, spacing: 8) {
                ForEach(previews, id: \.documentId) { item in
                    VStack {
                        if let data = Data(base64Encoded: item.imageBase64), let image = PlatformImage(data: data) {
                            Image(platformImage: image).resizable().scaledToFit().frame(maxHeight: 160)
                        }
                        Text(item.name).font(.caption).lineLimit(1)
                    }
                    .accessibilityIdentifier("imageBatchPrepare.preview")
                }
            }
            if !applied.isEmpty { appliedList }
            if let failure { Text(failure).font(.caption).foregroundStyle(.red) }
            HStack {
                Spacer()
                Button(batchId == nil ? "Cancel" : "Done") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                if batchId == nil {
                    Button("Apply to \(pages) Pages") { Task { await apply() } }
                        .keyboardShortcut(.defaultAction)
                        .disabled(pages == 0)
                        .accessibilityIdentifier("imageBatchPrepare.apply")
                }
            }
        }
        .padding(20)
        .frame(width: 520)
        .task { await loadPreviews() }
    }

    private var appliedList: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Applied to \(applied.count) pages. ⌘Z undoes all of them; or undo one page:").font(.caption)
            ScrollView {
                ForEach(applied, id: \.self) { id in
                    HStack {
                        Text(documents.first { $0.id == id }?.name ?? id).font(.callout).lineLimit(1)
                        Spacer()
                        Button("Undo") { Task { await undo(page: id) } }
                            .controlSize(.small)
                            .accessibilityIdentifier("imageBatchPrepare.undoPage")
                    }
                }
            }
            .frame(maxHeight: 120)
        }
    }

    private func loadPreviews() async {
        let body = Components.Schemas.BatchPrepareRequest(
            folderId: folderId,
            operation: .init(op: correction.kind == "square" ? .square : .rotate, quad: correction.quad, angle: correction.angle),
            sourceDocumentId: sourceDocumentId)
        do {
            if case .ok(let answer) = try await apiClient.api.batchPreparePreviewApiImagesBatchPreparePreviewPost(body: .json(body)) {
                let result = try answer.body.json
                previews = result.previews
                pages = result.pages
            }
        } catch {
            failure = "Couldn't preview: \(error.localizedDescription)"
        }
    }

    private func apply() async {
        guard let actionsService = actionStore?.actionsService else { return }
        do {
            let result = try await AuditedAction.run(
                "image.batch_prepare", params: request, actionName: "Apply to Folder",
                actionsService: actionsService, steps: windowSteps)
            batchId = result.auditId  // the engine's batch id is the audit's id
            applied = previews.isEmpty ? [] : documents.map(\.id).filter { $0 != sourceDocumentId }
            onApplied(applied)
            failure = nil
        } catch {
            failure = "Couldn't apply: \(error.localizedDescription)"
        }
    }

    private func undo(page: String) async {
        guard let actionsService = actionStore?.actionsService, let batchId else { return }
        do {
            try await AuditedAction.run(
                "image.undo_batch_page", params: ImageUndoBatchPageRequest(documentId: page, batchId: batchId),
                actionName: "Undo for One Page", actionsService: actionsService, steps: windowSteps)
            applied.removeAll { $0 == page }
            onApplied([page])
        } catch {
            failure = "Couldn't undo that page: \(error.localizedDescription)"
        }
    }
}

extension ImageEditorView {
    /// The toolbar's button for the sheet: shown when the page holds a correction that can be copied and sits in a folder.
    @ViewBuilder var applyToFolderButton: some View {
        if compareMode == .single, activeDocument.parentId != nil, BatchPrepare.correction(in: model.chain.operations) != nil {
            toolButton("square.stack.3d.down.right", help: "Apply this correction to the rest of this folder") {
                showBatchPrepare = true
            }
            .accessibilityIdentifier("imageEditApplyToFolder")
        }
    }
}
