#if canImport(AppKit)
import AppKit
#endif
#if canImport(Quartz)
import Quartz
#endif
import FicheroAPIClient
import OSLog
import SwiftUI

#if os(macOS)

private let logger = Logger(subsystem: "app.fichero.fichero", category: "QuickLookComponents")

// MARK: - Quick Look Components

struct QuickLookDownloadView: View {
    let document: Document

    @State private var fileURL: URL?
    @State private var isLoading = true
    @State private var error: String?

    @Environment(APIClient.self) var apiClient

    var body: some View {
        Group {
            if let url = fileURL {
                SmartPreviewView(url: url, documentId: document.id)
            } else if isLoading {
                VStack(spacing: 16) {
                    ProgressView()
                    Text("Loading preview...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = error {
                ZStack {
                    // Show thumbnail in background if available. AsyncImage(url:)
                    // can't pass the Bearer auth header (#742), so route through
                    // LibraryImageView which uses StorageService.fetchImageData.
                    LibraryImageView(documentId: document.id, imageType: .thumbnail)
                        .aspectRatio(contentMode: .fit)
                        .opacity(0.3)

                    // Error overlay
                    VStack(spacing: 16) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 48))
                            .foregroundColor(.orange)
                        Text("Preview unavailable")
                            .font(.headline)
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 32)
                            .padding(.vertical, 12)
                            .background(.ultraThinMaterial)
                            .cornerRadius(8)

                        Button("Retry") {
                            Task { await loadFile() }
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding()
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .task(id: document.id) {
            await loadFile()
        }
        .onDisappear {
            cleanupTemporaryFile()
        }
    }

    private func loadFile() async {
        isLoading = true
        error = nil
        fileURL = nil
        cleanupTemporaryFile()
        logger.info("Loading file from API for document: \(document.id)")
        await downloadFromAPI()
    }

    // swiftlint:disable:next function_body_length
    private func downloadFromAPI() async {
        let sourceURL = apiClient.sourceURL(for: document.id)

        do {
            if apiClient.currentLibraryPath == nil {
                logger.warning("Downloading source without library path - API may reject request")
            }
            var request = URLRequest(url: sourceURL)
            request.addEngineAuth(libraryPath: apiClient.currentLibraryPath)

            // Download file from API
            let session = RemoteCertificatePinning.configuredSession()
            let (tempURL, response) = try await session.download(for: request)

            // Branch on the HTTP status (#3206): a non-2xx body is the engine's
            // JSON error, not the document. Surface its `detail` instead of
            // handing an error page to Quick Look or guessing from byte size.
            if let httpResponse = response as? HTTPURLResponse,
               !(200..<300).contains(httpResponse.statusCode) {
                let message = Self.downloadErrorMessage(
                    statusCode: httpResponse.statusCode,
                    body: try? Data(contentsOf: tempURL),
                    documentPath: document.path
                )
                await MainActor.run {
                    self.error = message
                    self.isLoading = false
                }
                return
            }

            // Try to get filename from Content-Disposition header
            var fileName = fileNameWithExtension()
            if let httpResponse = response as? HTTPURLResponse,
               let contentDisposition = httpResponse.value(forHTTPHeaderField: "Content-Disposition"),
               let range = contentDisposition.range(of: "filename=\""),
               let endRange = contentDisposition.range(
                of: "\"",
                range: range.upperBound..<contentDisposition.endIndex
               ) {
                let serverFileName = String(contentDisposition[range.upperBound..<endRange.lowerBound])
                if !serverFileName.isEmpty {
                    fileName = serverFileName
                }
            }

            // Move to cache directory
            let cacheDir = FileManager.default.temporaryDirectory
                .appendingPathComponent("FicheroPreview")
            try FileManager.default.createDirectory(at: cacheDir, withIntermediateDirectories: true)

            let destURL = cacheDir.appendingPathComponent("\(document.id)_\(fileName)")

            // Remove existing
            if FileManager.default.fileExists(atPath: destURL.path) {
                try FileManager.default.removeItem(at: destURL)
            }
            try FileManager.default.moveItem(at: tempURL, to: destURL)

            logger.info("Downloaded to: \(destURL.path) (extension: \(destURL.pathExtension))")

            await MainActor.run {
                self.fileURL = destURL
                self.isLoading = false
            }
        } catch {
            logger.error("Download error: \(error.localizedDescription)")
            await MainActor.run {
                self.error = "Failed to load: \(error.localizedDescription)"
                self.isLoading = false
            }
        }
    }

    /// Human message for a non-2xx source download (#3206): the engine's JSON
    /// `detail` when present (get_source_file returns proper 404 detail), else a
    /// status-coded fallback, plus the linked-external-drive hint that helps a
    /// user mount an unplugged volume. Pure + static so it is unit-testable.
    static func downloadErrorMessage(statusCode: Int, body: Data?, documentPath: String?) -> String {
        var message = "Preview unavailable (HTTP \(statusCode))"
        if let body,
           let object = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
           let detail = object["detail"] as? String, !detail.isEmpty {
            message = detail
        }
        if let documentPath, documentPath.hasPrefix("/Volumes/") {
            message += "\n\nThis file is linked to an external drive:\n\(documentPath)"
            message += "\n\nMount the drive to view the full resolution file."
        }
        return message
    }

    private func cleanupTemporaryFile() {
        guard let fileURL else { return }
        let previewRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("FicheroPreview")
            .standardizedFileURL
        let candidate = fileURL.standardizedFileURL
        guard candidate.path.hasPrefix(previewRoot.path) else { return }
        try? FileManager.default.removeItem(at: candidate)
    }

    // Get filename with proper extension
    // swiftlint:disable:next cyclomatic_complexity
    private func fileNameWithExtension() -> String {
        let name = document.name
        if name.contains(".") {
            return name
        }

        if let path = document.path {
            let ext = (path as NSString).pathExtension
            if !ext.isEmpty {
                return "\(name).\(ext)"
            }
        }

        if let fileType = document.fileType {
            let ext: String
            switch fileType {
            case .image: ext = "jpg"
            case .pdf: ext = "pdf"
            case .audio: ext = "mp3"
            case .video: ext = "mp4"
            case .text: ext = "txt"
            case .json: ext = "json"
            case .word: ext = "docx"
            case .epub: ext = "epub"
            case .spreadsheet: ext = "xlsx"
            case .presentation: ext = "pptx"
            case .csv: ext = "csv"
            case .rtf: ext = "rtf"
            case .mobi: ext = "mobi"
            case .other: ext = "bin"
            }
            return "\(name).\(ext)"
        }

        return name
    }
}

#else

// iOS fallback: QuickLookDownloadView is referenced by EditorView; provide a
// placeholder that prompts the user until a native UIDocumentInteractionController
// or QLPreviewController replacement lands.
struct QuickLookDownloadView: View {
    let document: Document

    var body: some View {
        ContentUnavailableView(
            document.name,
            systemImage: docTypeIcon,
            description: Text("Preview is not available on iOS yet.")
        )
    }

    private var docTypeIcon: String {
        switch document.fileType {
        case .image: return "photo"
        case .pdf: return "doc.richtext"
        case .audio: return "waveform"
        case .video: return "film"
        case .text, .json, .csv, .rtf: return "doc.text"
        default: return "doc"
        }
    }
}

#endif
