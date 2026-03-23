import SwiftUI
import Quartz
import AppKit
import OSLog

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "QuickLookComponents")

// MARK: - Quick Look Components

struct QuickLookDownloadView: View {
    let document: Document

    @StateObject private var folderAccess = FolderAccessManager.shared
    @State private var fileURL: URL?
    @State private var isLoading = true
    @State private var needsAccess = false
    @State private var error: String?

    @EnvironmentObject var apiClient: APIClient

    var body: some View {
        Group {
            if let url = fileURL {
                SmartPreviewView(url: url, documentId: document.id)
            } else if needsAccess {
                // Prompt user to grant folder access
                accessRequiredView
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
                    // Show thumbnail in background if available
                    AsyncImage(url: apiClient.thumbnailURL(for: document.id)) { phase in
                        switch phase {
                        case .success(let image):
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .opacity(0.3)
                        default:
                            Color.clear
                        }
                    }

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
    }

    /// The folder we need access to (immediate parent of the file)
    private var neededFolderName: String {
        guard let path = document.path else { return "this folder" }
        return URL(fileURLWithPath: path).deletingLastPathComponent().lastPathComponent
    }

    private var accessRequiredView: some View {
        VStack(spacing: 16) {
            Image(systemName: "folder.badge.questionmark")
                .font(.system(size: 48))
                .foregroundColor(.orange)

            Text("Grant Access to \(neededFolderName)")
                .font(.headline)

            Text("Fichero needs permission to read files from this folder. You only need to do this once.")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)

            Button("Grant Access to \(neededFolderName)...") {
                FolderAccessManager.shared.requestFolderAccess(suggestedPath: document.path) { success in
                    if success {
                        Task { await loadFile() }
                    }
                }
            }
            .buttonStyle(.borderedProminent)
            .padding(.top, 8)

            // Show currently accessible folders
            if !folderAccess.accessedFolders.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Already accessible:")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    ForEach(folderAccess.accessedFolders, id: \.path) { url in
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.caption2)
                                .foregroundColor(.green)
                            Text(url.lastPathComponent)
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                    }
                }
                .padding(.top, 8)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func loadFile() async {
        isLoading = true
        error = nil
        fileURL = nil
        needsAccess = false

        // First try local path if we have access
        if let path = document.path {
            let localURL = URL(fileURLWithPath: path)

            // Check if readable (either directly or via granted folder access)
            if FolderAccessManager.shared.hasAccess(to: path) {
                logger.info("Has folder access to: \(path)")

                // Verify the file can actually be read before using it
                if FileManager.default.isReadableFile(atPath: path) {
                    logger.info("File is readable, using local path")
                    await MainActor.run {
                        self.fileURL = localURL
                        self.isLoading = false
                    }
                    return
                } else {
                    logger.warning("File exists but is not readable, falling back to API download: \(path)")
                    // Fall through to API download
                }
            } else {
                // File exists but no access - prompt user
                if FileManager.default.fileExists(atPath: path) {
                    logger.info("File exists but no folder access granted")
                    await MainActor.run {
                        self.needsAccess = true
                        self.isLoading = false
                    }
                    return
                }
            }
        }

        // No local path or file doesn't exist - download from API
        logger.info("Loading file from API for document: \(document.id)")
        await downloadFromAPI()
    }

    // swiftlint:disable:next function_body_length
    private func downloadFromAPI() async {
        let sourceURL = apiClient.sourceURL(for: document.id)

        do {
            // Create request with required header
            var request = URLRequest(url: sourceURL)
            if let libraryPath = apiClient.currentLibraryPath {
                request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
            } else {
                logger.warning("Downloading source without library path - API may reject request")
            }

            // Download file from API
            let (tempURL, response) = try await URLSession.shared.download(for: request)

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

            // Verify file exists and has size
            let attrs = try FileManager.default.attributesOfItem(atPath: destURL.path)
            let fileSize = attrs[.size] as? Int64 ?? 0
            logger.info("Downloaded to: \(destURL.path) (size: \(fileSize) bytes, extension: \(destURL.pathExtension))")

            // Verify it's actually valid, not an error response
            if fileSize < 1000 {
                logger.warning("Downloaded file is very small (\(fileSize) bytes), likely an error response")
                // Try to read as JSON error
                if let content = try? String(contentsOf: destURL, encoding: .utf8) {
                    logger.error("Error response: \(content)")

                    // Parse error message if possible
                    var errorMessage = "Source file not available"
                    if content.contains("Source file not available") {
                        errorMessage = "External file not accessible"
                    } else if content.contains("Field required") {
                        errorMessage = "API error: Missing required field"
                    }

                    // Check if this is a linked file
                    if let path = document.path, path.starts(with: "/Volumes/") {
                        errorMessage += "\n\nThis file is linked to an external drive:\n\(path)"
                        errorMessage += "\n\nMount the drive to view the full resolution file."
                    }

                    await MainActor.run {
                        self.error = errorMessage
                        self.isLoading = false
                    }
                    return
                }
            }

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
            case .word: ext = "docx"
            case .epub: ext = "epub"
            case .other: ext = "bin"
            }
            return "\(name).\(ext)"
        }

        return name
    }
}

struct SmartPreviewView: View {
    let url: URL
    var documentId: String?

    private var isImage: Bool {
        let imageExtensions = ["jpg", "jpeg", "png", "gif", "tiff", "tif", "bmp", "heic", "webp"]
        let ext = url.pathExtension.lowercased()
        let result = imageExtensions.contains(ext)
        logger.info("SmartPreviewView: \(url.lastPathComponent) extension='\(ext)' isImage=\(result)")
        return result
    }

    var body: some View {
        if isImage {
            ZoomableImagePreview(url: url, documentId: documentId)
        } else {
            QuickLookPreviewView(url: url)
        }
    }
}

struct QuickLookPreviewView: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> NSView {
        let previewView = QLPreviewView(frame: .zero, style: .normal)!
        previewView.translatesAutoresizingMaskIntoConstraints = false
        previewView.previewItem = url as QLPreviewItem
        previewView.autostarts = true

        let container = NSView()
        container.wantsLayer = true
        container.addSubview(previewView)

        NSLayoutConstraint.activate([
            previewView.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            previewView.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            previewView.topAnchor.constraint(equalTo: container.topAnchor),
            previewView.bottomAnchor.constraint(equalTo: container.bottomAnchor)
        ])

        context.coordinator.previewView = previewView
        return container
    }

    func updateNSView(_ container: NSView, context: Context) {
        if let previewView = context.coordinator.previewView {
            let currentURL = previewView.previewItem as? URL
            if currentURL != url {
                previewView.previewItem = url as QLPreviewItem
            }
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    class Coordinator {
        var previewView: QLPreviewView?
    }
}
