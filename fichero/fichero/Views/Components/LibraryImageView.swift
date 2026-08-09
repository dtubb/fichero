import FicheroAPIClient
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

    // Access the shared services from the current library. OPTIONAL on
    // purpose (Daniel's live crash, 2026-08-08 22:44): the non-optional form
    // is a process-killing assertion — "No Observable object of type
    // StorageService found" took the whole app down over ONE thumbnail when
    // a presentation context (a panel, a detached sheet, a preview host)
    // didn't inherit the tab's injection. A missing service renders the
    // failure placeholder and logs an error naming the document instead;
    // every real surface still injects the service and is unaffected.
    @Environment(StorageService.self) var storageService: StorageService?

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
            } else if loadError != nil {
                Image(systemName: "photo")
                    .foregroundColor(.secondary)
            } else {
                // ★ EVERY FRAME PERFECT (#3616): a sized skeleton at the surface
                // color instead of a bare centered spinner, filling the reserved
                // cell so the thumbnail cross-fades in (below) with no pop.
                SkeletonPlaceholder()
            }
        }
        // Cross-fade the branch swap: the skeleton fades out as the loaded image
        // fades in, keyed to image presence (feeds #3619's precise transitions).
        .animation(FrameAnimation.crossfade, value: image == nil)
        .task(id: loadKey) {
            guard !Task.isCancelled else { return }
            await loadImage(for: loadKey)
        }
    }

    /// The synchronous cache seed (#3870), split from loadImage for the
    /// function-length budget. True = seeded; the load is done.
    private func seedFromCache(_ key: LibraryImageLoadKey, _ storage: StorageService) -> Bool {
        guard key.imageType == .thumbnail,
              let cached = storage.cachedThumbnail(for: key.documentId) else { return false }
        image = cached
        loadedKey = key
        isLoading = false
        loadError = nil
        return true
    }

    private func loadImage(for key: LibraryImageLoadKey) async {
        guard loadedKey != key || image == nil else { return }

        guard let storageService else {
            // The 2026-08-08 crash class, made self-diagnosing: name the view
            // and the document so the missing-injection surface can be found
            // from the log, then render the failure placeholder.
            Self.logger.error(
                """
                LibraryImageView: StorageService missing from the environment for \(key.documentId) \
                — rendering placeholder. The hosting surface needs .environment(library.storageService).
                """
            )
            loadError = CocoaError(.fileNoSuchFile)
            isLoading = false
            return
        }

        // Seed a cache hit synchronously so the first render shows the thumbnail with
        // no image=nil placeholder flash before the async fetch (#3870).
        if seedFromCache(key, storageService) { return }

        image = nil
        loadedKey = nil
        isLoading = true
        loadError = nil

        let imageTypeLabel = key.imageType == .thumbnail ? "thumbnail" : "display"
        // .debug, not .info: this fires per thumbnail during hot scroll (#3870).
        Self.logger.debug("Loading \(imageTypeLabel) for document: \(key.documentId)")

        do {
            let loadedImage: Image
            switch key.imageType {
            case .thumbnail:
                loadedImage = try await storageService.getThumbnail(key.documentId)
                Self.logger.debug("Successfully loaded thumbnail for: \(key.documentId)")
            case .display:
                loadedImage = try await storageService.getDisplayImage(key.documentId)
                Self.logger.debug("Successfully loaded display image for: \(key.documentId)")
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
            if Task.isCancelled || error.isCancellationError {
                // SwiftUI cancels the in-flight load when the row scrolls off or
                // the list refreshes; the transport surfaces that as a -999
                // "cancelled". A cancellation is not a load failure, so trace it
                // instead of logging an error (#3385) — the next load takes over.
                Self.logger.debug("\(imageTypeLabel) load cancelled for \(key.documentId)")
            } else if case StorageServiceError.notFound = error {
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
