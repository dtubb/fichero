#if canImport(AppKit)
import AppKit
#endif
#if canImport(Quartz)
import Quartz
#endif
import FicheroAPIClient
import Foundation
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
    @State private var requestGate = PreviewDownloadService.RequestGate()

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
            requestGate.invalidate()
            PreviewDownloadService.removePreviewFile(fileURL)
        }
    }

    private func loadFile() async {
        let documentId = document.id
        let generation = requestGate.begin(for: documentId)
        let cacheKey = "\(documentId)-\(UUID().uuidString)"
        isLoading = true
        error = nil
        PreviewDownloadService.removePreviewFile(fileURL)
        fileURL = nil
        logger.info("Loading file from API for document: \(documentId)")

        let outcome = await downloadService.download(.init(
            documentId: documentId,
            cacheKey: cacheKey,
            fallbackFileName: PreviewDownloadService.fallbackFileName(
                name: document.name,
                path: document.path,
                fileType: document.fileType
            ),
            documentPath: document.path
        ))
        guard !Task.isCancelled, requestGate.isCurrent(documentId: documentId, generation: generation) else {
            if case .success(let url) = outcome { PreviewDownloadService.removePreviewFile(url) }
            return
        }

        switch outcome {
        case .success(let url):
            fileURL = url
        case .failure(let message):
            error = message
        case .cancelled:
            break
        }
        isLoading = false
    }
}

#elseif os(iOS)

struct QuickLookDownloadView: View {
    let document: Document

    @State private var fileURL: URL?
    @State private var isLoading = true
    @State private var error: String?
    @State private var requestGate = PreviewDownloadService.RequestGate()

    @Environment(StorageService.self) private var storageService

    private var downloadService: PreviewDownloadService {
        PreviewDownloadService(storage: storageService)
    }

    var body: some View {
        Group {
            if let fileURL {
                SmartPreviewView(url: fileURL, documentId: document.id)
            } else if isLoading {
                ProgressView("Loading preview...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error {
                ContentUnavailableView {
                    Label("Preview unavailable", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(error)
                } actions: {
                    Button("Retry") {
                        Task { await loadFile() }
                    }
                }
            }
        }
        .task(id: document.id) {
            await loadFile()
        }
        .onDisappear {
            requestGate.invalidate()
            PreviewDownloadService.removePreviewFile(fileURL)
        }
    }

    private func loadFile() async {
        let documentId = document.id
        let generation = requestGate.begin(for: documentId)
        let cacheKey = "\(documentId)-\(UUID().uuidString)"
        isLoading = true
        error = nil
        PreviewDownloadService.removePreviewFile(fileURL)
        fileURL = nil

        let outcome = await downloadService.download(.init(
            documentId: documentId,
            cacheKey: cacheKey,
            fallbackFileName: PreviewDownloadService.fallbackFileName(
                name: document.name,
                path: document.path,
                fileType: document.fileType
            ),
            documentPath: document.path
        ))
        guard !Task.isCancelled, requestGate.isCurrent(documentId: documentId, generation: generation) else {
            if case .success(let url) = outcome { PreviewDownloadService.removePreviewFile(url) }
            return
        }

        switch outcome {
        case .success(let url):
            fileURL = url
        case .failure(let message):
            error = message
        case .cancelled:
            break
        }
        isLoading = false
    }
}
#else

struct QuickLookDownloadView: View {
    let document: Document

    var body: some View {
        ContentUnavailableView(
            document.name,
            systemImage: "doc.richtext",
            description: Text("Preview is not available on this platform.")
        )
    }
}
#endif
