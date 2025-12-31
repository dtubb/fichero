import SwiftUI
import Quartz
import AppKit
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "QuickLookComponents")

// MARK: - Quick Look Components

struct QuickLookDownloadView: View {
    let document: Document

    @StateObject private var folderAccess = FolderAccessManager.shared
    @State private var fileURL: URL?
    @State private var isLoading = true
    @State private var needsAccess = false
    @State private var error: String?

    var body: some View {
        Group {
            if let url = fileURL {
                SmartPreviewView(url: url)
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
                        .padding(.horizontal)

                    Button("Retry") {
                        Task { await loadFile() }
                    }
                    .buttonStyle(.bordered)
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
                await MainActor.run {
                    self.fileURL = localURL
                    self.isLoading = false
                }
                return
            }

            // File exists but no access - prompt user
            if FileManager.default.fileExists(atPath: path) {
                await MainActor.run {
                    self.needsAccess = true
                    self.isLoading = false
                }
                return
            }
        }

        // No local path or file doesn't exist - download from API
        await downloadFromAPI()
    }

    private func downloadFromAPI() async {
        let sourceURL = APIClient().sourceURL(for: document.id)

        do {
            // Download file from API
            let (tempURL, response) = try await URLSession.shared.download(from: sourceURL)

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

            logger.info("Downloaded to: \(destURL.path)")

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

    /// Get filename with proper extension
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

    private var isImage: Bool {
        let imageExtensions = ["jpg", "jpeg", "png", "gif", "tiff", "tif", "bmp", "heic", "webp"]
        return imageExtensions.contains(url.pathExtension.lowercased())
    }

    var body: some View {
        if isImage {
            ZoomableImagePreview(url: url)
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
