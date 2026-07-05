import OSLog
import SwiftUI

struct LibraryImageLoadKey: Hashable {
    let documentId: String
    let imageType: LibraryImageView.ImageType
}

/// Image view that loads from backend with proper library path headers
/// Replacement for AsyncImage which doesn't support custom headers
struct LibraryImageView: View {
    enum ImageType: Hashable {
        case thumbnail
        case display
    }

    let documentId: String
    let imageType: ImageType

    // Access the shared services from the current library
    @Environment(StorageServiceGenerated.self) var storageService

    @State private var image: Image?
    @State private var loadedKey: LibraryImageLoadKey?
    @State private var isLoading = false
    @State private var loadError: Error?

    private static let logger = Logger(subsystem: "app.fichero.fichero", category: "LibraryImageView")
    private var loadKey: LibraryImageLoadKey { .init(documentId: documentId, imageType: imageType) }

    var body: some View {
        Group {
            if let image = image {
                image
                    .resizable()
            } else if isLoading {
                ProgressView()
                    .scaleEffect(0.6)
            } else if loadError != nil {
                Image(systemName: "photo")
                    .foregroundColor(.secondary)
            } else {
                Color.clear
            }
        }
        .task(id: loadKey) {
            guard !Task.isCancelled else { return }
            await loadImage(for: loadKey)
        }
    }

    private func loadImage(for key: LibraryImageLoadKey) async {
        guard loadedKey != key || image == nil else { return }

        image = nil
        loadedKey = nil
        isLoading = true
        loadError = nil

        let imageTypeLabel = key.imageType == .thumbnail ? "thumbnail" : "display"
        Self.logger.info("Loading \(imageTypeLabel) for document: \(key.documentId)")

        do {
            let loadedImage: Image
            switch key.imageType {
            case .thumbnail:
                loadedImage = try await storageService.getThumbnail(key.documentId)
                Self.logger.info("Successfully loaded thumbnail for: \(key.documentId)")
            case .display:
                loadedImage = try await storageService.getDisplayImage(key.documentId)
                Self.logger.info("Successfully loaded display image for: \(key.documentId)")
            }
            guard loadKey == key else {
                isLoading = false
                return
            }
            image = loadedImage
            loadedKey = key
        } catch {
            guard loadKey == key else {
                isLoading = false
                return
            }
            loadError = error
            if case StorageServiceError.notFound = error {
                Self.logger.info("No \(imageTypeLabel) yet for \(key.documentId): \(error.localizedDescription)")
            } else {
                Self.logger.error("Failed to load image for \(key.documentId): \(error.localizedDescription)")
            }
            // Will show placeholder icon
        }

        isLoading = false
    }
}

// MARK: - Preview

#Preview {
    VStack(spacing: 20) {
        LibraryImageView(documentId: "test-id", imageType: .thumbnail)
            .frame(width: 100, height: 100)

        LibraryImageView(documentId: "test-id", imageType: .display)
            .frame(width: 300, height: 400)
    }
    .padding()
}
