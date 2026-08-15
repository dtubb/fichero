import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "RunArtifactRow")

/// One artifact produced by a run: what it is, where it came from, and — when
/// the server sent a clipped preview — the fact that it is clipped (#4284).
///
/// The server sends `content_preview` capped at 2,000 characters together with
/// `content_truncated` and the true `content_chars`; the full content stays at
/// `GET /api/artifacts/{id}`. Rendering that preview as though it were the
/// whole artifact would silently misreport a transcription — the reader would
/// have no way to tell a short document from a clipped one. So the clip is
/// always stated, and the full text is always one click away.
struct RunArtifactRow: View {
    let artifact: WorkflowRunArtifact

    @Environment(APIClient.self) private var apiClient: APIClient?

    @State private var fullContent: String?
    @State private var isLoadingFull = false
    @State private var loadError: String?

    /// The preview is superseded once the full content has been fetched, and
    /// only then does the truncation notice come down.
    private var isStillTruncated: Bool { artifact.isTruncated && fullContent == nil }

    private var displayedText: String? { fullContent ?? artifact.contentPreview }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            header
            provenance
            if let text = displayedText, !text.isEmpty {
                Text(text)
                    // Fetched-full content shows WHOLE (#22, no-truncation
                    // mandate): capping "Show Full" at 12 lines re-clipped
                    // the very text the user just asked to see in full.
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(isStillTruncated ? 4 : (fullContent != nil ? nil : 12))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            if isStillTruncated {
                truncationNotice
            }
            if let loadError {
                Text(loadError)
                    .font(.caption2)
                    .foregroundStyle(.red)
            }
        }
        .padding(.vertical, 2)
    }

    private var header: some View {
        HStack(spacing: 6) {
            Image(systemName: "sparkles")
                .foregroundStyle(.secondary)
            Text(artifact.artifactType)
                .font(.caption)
            if let name = artifact.documentName ?? artifact.sourceDocumentName {
                Text(name)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
        }
    }

    /// Which step and which model actually produced this. Facts with an
    /// origin: an artifact whose provider/model the server never recorded
    /// says so, rather than inheriting the node's configured model and
    /// implying a certainty the record does not have.
    @ViewBuilder
    private var provenance: some View {
        let step = artifact.nodeName ?? artifact.stepName
        HStack(spacing: 4) {
            Image(systemName: "point.topleft.down.to.point.bottomright.curvepath")
                .font(.caption2)
            if let step {
                Text(step)
            }
            if let providerModel = artifact.providerModelText {
                if step != nil { Text("·") }
                Text(providerModel)
            } else {
                if step != nil { Text("·") }
                Text("model not recorded")
                    .italic()
            }
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
        .lineLimit(1)
        .truncationMode(.middle)
        .textSelection(.enabled)
    }

    private var truncationNotice: some View {
        HStack(spacing: 6) {
            Label(
                artifact.truncationNotice ?? "Preview only — this is not the full text",
                systemImage: "scissors"
            )
            .font(.caption2)
            .foregroundStyle(.orange)
            Spacer(minLength: 4)
            if isLoadingFull {
                ProgressView().controlSize(.mini)
            } else {
                Button("Show Full") { Task { await loadFull() } }
                    .font(.caption2)
                    // `.link` is macOS-only. `.plain` reads the same here — the
                    // caption font and accent colour already carry the affordance
                    // — and works on both platforms.
                    .buttonStyle(.plain)
                    .foregroundStyle(.tint)
                    .disabled(apiClient == nil)
            }
        }
    }

    private func loadFull() async {
        guard let apiClient else { return }
        isLoadingFull = true
        defer { isLoadingFull = false }
        do {
            let full = try await ArtifactService(apiClient: apiClient)
                .getArtifact(id: artifact.artifactId)
            // A nil content is not "the full text is empty" — it is a fetch
            // that told us nothing. Keep the preview and the clip notice.
            guard let content = full.content else {
                loadError = "The server returned no content for this artifact."
                return
            }
            fullContent = content
            loadError = nil
        } catch {
            logger.error(
                "Failed to load full artifact \(artifact.artifactId): \(String(describing: error))"
            )
            loadError = error.localizedDescription
        }
    }
}
