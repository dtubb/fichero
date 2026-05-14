import OSLog
import SwiftUI

/// Image view that loads from backend with proper library path headers
/// Replacement for AsyncImage which doesn't support custom headers
struct LibraryImageView: View {
    enum ImageType {
        case thumbnail
        case display
    }

    let documentId: String
    let imageType: ImageType

    // Access the shared services from the current library
    @EnvironmentObject var storageService: StorageServiceGenerated

    @State private var image: Image?
    @State private var isLoading = false
    @State private var loadError: Error?

    private static let logger = Logger(subsystem: "com.fichero.fichero", category: "LibraryImageView")

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
        .task {
            guard !Task.isCancelled else { return }
            await loadImage()
        }
    }

    private func loadImage() async {
        guard image == nil else { return }

        isLoading = true
        loadError = nil

        let imageTypeLabel = self.imageType == .thumbnail ? "thumbnail" : "display"
        Self.logger.info("Loading \(imageTypeLabel) for document: \(self.documentId)")

        do {
            switch imageType {
            case .thumbnail:
                image = try await storageService.getThumbnail(documentId)
                Self.logger.info("Successfully loaded thumbnail for: \(self.documentId)")
            case .display:
                image = try await storageService.getDisplayImage(documentId)
                Self.logger.info("Successfully loaded display image for: \(self.documentId)")
            }
        } catch {
            loadError = error
            if case StorageServiceError.notFound = error {
                Self.logger.info("No \(imageTypeLabel) yet for \(self.documentId): \(error.localizedDescription)")
            } else {
                Self.logger.error("Failed to load image for \(self.documentId): \(error.localizedDescription)")
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
