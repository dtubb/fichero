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

    @Environment(StorageService.self) var storageService

    /// The download/temp-file flow lives in the service (#3207/#3726); the view
    /// keeps only fileURL/isLoading/error state. Built from the environment's
    /// storage service so transport stays on the generated client.
    private var downloadService: PreviewDownloadService {
        PreviewDownloadService(storage: storageService)
    }

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
            downloadService.removePreviewFile(fileURL)
        }
    }

    private func loadFile() async {
        isLoading = true
        error = nil
        downloadService.removePreviewFile(fileURL)
        fileURL = nil
        logger.info("Loading file from API for document: \(document.id)")

        let outcome = await downloadService.download(.init(
            documentId: document.id,
            fallbackFileName: fileNameWithExtension(),
            documentPath: document.path
        ))
        switch outcome {
        case .success(let url):
            fileURL = url
        case .failure(let message):
            error = message
        }
        isLoading = false
    }

    // Get filename with proper extension
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
            return "\(name).\(fallbackExtension(for: fileType))"
        }

        return name
    }

    // Default extension per file type, used only when the document has neither
    // a dotted name nor a path to infer one from.
    private func fallbackExtension(for fileType: FileType) -> String {
        switch fileType {
        case .image: return "jpg"
        case .pdf: return "pdf"
        case .audio: return "mp3"
        case .video: return "mp4"
        case .text: return "txt"
        case .json: return "json"
        case .word: return "docx"
        case .epub: return "epub"
        case .spreadsheet: return "xlsx"
        case .presentation: return "pptx"
        case .csv: return "csv"
        case .rtf: return "rtf"
        case .mobi: return "mobi"
        case .other: return "bin"
        }
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
