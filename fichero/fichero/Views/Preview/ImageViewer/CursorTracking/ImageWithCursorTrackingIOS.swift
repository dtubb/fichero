#if canImport(UIKit)
import CoreImage
import ImageIO
import OSLog
import SwiftUI
import UIKit

/// UIViewRepresentable wrapper for an image view with basic zoom/pan on iOS.
/// Loupe drawing is stubbed through `TrackingImageView` to keep the same API
/// surface as macOS; the loupe is not yet rendered on iOS.
struct ImageWithCursorTracking: UIViewRepresentable {
    static let logger = Logger(subsystem: "app.fichero.fichero", category: "ImageWithCursorTracking")

    let url: URL?
    var overrideImage: PlatformImage?
    @Binding var scale: CGFloat
    @Binding var cursorPosition: CGPoint
    @Binding var imageSize: CGSize
    @Binding var visibleRect: CGRect
    let minScale: CGFloat
    let maxScale: CGFloat
    let loupeEnabled: Bool
    let loupeLocked: Bool
    @Binding var loupeMagnification: CGFloat
    @Binding var loupeSize: CGFloat
    @Binding var coordinator: Coordinator?

    func makeUIView(context: Context) -> UIScrollView {
        let scrollView = UIScrollView()
        scrollView.backgroundColor = UIColor(white: 0.88, alpha: 1)
        scrollView.delegate = context.coordinator
        scrollView.minimumZoomScale = minScale
        scrollView.maximumZoomScale = maxScale
        scrollView.zoomScale = scale
        scrollView.showsHorizontalScrollIndicator = true
        scrollView.showsVerticalScrollIndicator = true
        scrollView.alpha = 0

        let imageView = TrackingImageView()
        imageView.contentMode = .topLeft
        imageView.isUserInteractionEnabled = true

        imageView.onCursorMoved = { normalizedPos in
            Task { @MainActor in
                let clampedPos = CGPoint(
                    x: max(0, min(1, normalizedPos.x)),
                    y: max(0, min(1, normalizedPos.y))
                )
                self.cursorPosition = clampedPos
            }
        }
        imageView.onLoupeMagnificationChanged = { newMag in
            Task { @MainActor in
                self.loupeMagnification = newMag
            }
        }
        imageView.onLoupeSizeChanged = { newSize in
            Task { @MainActor in
                self.loupeSize = newSize
            }
        }
        imageView.loupeMagnification = loupeMagnification
        imageView.loupeSize = loupeSize

        scrollView.addSubview(imageView)
        context.coordinator.scrollView = scrollView
        context.coordinator.imageView = imageView

        // Override images are already decoded; a URL is decoded OFF-main (#3864).
        context.coordinator.currentOverrideImage = overrideImage
        if let overrideImage {
            imageView.image = overrideImage
            imageView.frame = CGRect(origin: .zero, size: overrideImage.size)
            scrollView.contentSize = overrideImage.size
            Self.logger.info("makeUIView: Set image size=\(overrideImage.size.width)x\(overrideImage.size.height)")
            Task { @MainActor in
                self.imageSize = overrideImage.size
            }
        } else if let url {
            loadImageAsync(url: url, into: imageView, scrollView: scrollView, coordinator: context.coordinator)
        }

        context.coordinator.onVisibleRectChanged = { rect in
            Task { @MainActor in
                self.visibleRect = rect
            }
        }
        context.coordinator.onScaleChanged = { newScale in
            Task { @MainActor in
                if abs(self.scale - newScale) > 0.01 {
                    self.scale = newScale
                }
            }
        }
        context.coordinator.needsInitialCenter = true

        return scrollView
    }

    func updateUIView(_ scrollView: UIScrollView, context: Context) {
        context.coordinator.owner = self

        let hasImage = (context.coordinator.imageView as? UIImageView)?.image != nil
        // Scale this pass applied automatically (initial fit or resize re-fit).
        // #4279: when set, the zoom↔scale sync below must NOT run — the `scale`
        // binding is still one turn behind and would undo the fit in the same pass.
        let autoAppliedScale = applyAutomaticFit(
            scrollView: scrollView,
            coordinator: context.coordinator,
            hasImage: hasImage
        )

        if autoAppliedScale == nil,
           !context.coordinator.isUserMagnifying,
           abs(scrollView.zoomScale - scale) > 0.01 {
            scrollView.zoomScale = scale
        }

        if let imageView = context.coordinator.imageView as? TrackingImageView {
            imageView.loupeEnabled = loupeEnabled

            if loupeEnabled && imageView.loupePosition == nil {
                Task { @MainActor [weak imageView] in
                    try? await Task.sleep(for: .milliseconds(50))
                    guard let imageView = imageView,
                          imageView.loupeEnabled,
                          imageView.loupePosition == nil else { return }
                    imageView.showLoupeAtCenter()
                }
            }

            imageView.loupeLocked = loupeLocked
            imageView.loupeMagnification = loupeMagnification
            imageView.loupeSize = loupeSize

            let overrideChanged = overrideImage !== context.coordinator.currentOverrideImage
            let urlChanged = context.coordinator.currentURL != url
            let needsImageUpdate = overrideImage != nil ? overrideChanged : urlChanged

            if needsImageUpdate {
                if let overrideImage {
                    imageView.image = overrideImage
                    imageView.frame = CGRect(origin: .zero, size: overrideImage.size)
                    scrollView.contentSize = overrideImage.size
                    imageView.loupePosition = nil
                    context.coordinator.currentURL = url
                    context.coordinator.currentOverrideImage = overrideImage
                    // A different item is on screen — auto-fit owns the zoom
                    // again until the user zooms this one manually (#4279).
                    // Deliberately no `noteAutoFitApplied()` here: this branch
                    // runs *after* this pass's zoom↔scale sync, so leaving the
                    // recorded pane size cleared makes the next pass re-assert
                    // the fit if the (one-turn-late) binding write hasn't landed.
                    context.coordinator.resetZoomOwnershipForNewItem()
                    Task { @MainActor in
                        self.imageSize = overrideImage.size
                    }
                    if let fitScale = context.coordinator.calculateFitScale() {
                        scrollView.zoomScale = fitScale
                        Task { @MainActor in
                            self.scale = fitScale
                        }
                    }
                    context.coordinator.centerContent()
                    if scrollView.alpha < 1 { scrollView.alpha = 1 }
                } else if let url {
                    // Decode the new page OFF-main (#3864); previous page stays until ready.
                    loadImageAsync(url: url, into: imageView, scrollView: scrollView, coordinator: context.coordinator)
                }
            }
        }

        context.coordinator.centerContent()
        context.coordinator.updateVisibleRect()

        if scrollView.alpha < 1,
           scrollView.bounds.width > 0,
           scrollView.bounds.height > 0,
           let imageView = context.coordinator.imageView as? UIImageView,
           imageView.image != nil {
            scrollView.alpha = 1
        }
    }

    func makeCoordinator() -> Coordinator {
        let coord = Coordinator(owner: self)
        Task { @MainActor in
            self.coordinator = coord
        }
        return coord
    }

    /// Decode `url` OFF the main thread, then wrap + apply the ready image (#3864),
    /// dropping a superseded page-flip's late decode via the coordinator's token and
    /// fitting in the same turn once bounds are known.
    func loadImageAsync(
        url: URL,
        into imageView: TrackingImageView,
        scrollView: UIScrollView,
        coordinator: Coordinator
    ) {
        coordinator.currentURL = url
        coordinator.currentOverrideImage = nil
        // A different item is on screen — auto-fit owns the zoom again (#4279).
        coordinator.resetZoomOwnershipForNewItem()
        let token = coordinator.beginImageLoad()
        Task { @MainActor in
            guard let decoded = await decodeCGImage(from: url),
                  coordinator.isCurrentImageLoad(token) else { return }
            let image = UIImage(cgImage: decoded.cgImage, scale: 1, orientation: decoded.orientation)
            imageView.image = image
            imageView.frame = CGRect(origin: .zero, size: image.size)
            scrollView.contentSize = image.size
            imageView.loupePosition = nil
            self.imageSize = image.size
            if let fitScale = coordinator.calculateFitScale() {
                scrollView.zoomScale = fitScale
                coordinator.noteAutoFitApplied()
                self.scale = fitScale
                coordinator.centerContent()
                if scrollView.alpha < 1 { scrollView.alpha = 1 }
            } else {
                coordinator.needsInitialCenter = true
            }
        }
    }
}

// MARK: - Automatic Fit (#4279)
// In an extension so the representable's own body stays within the
// type-body-length budget, mirroring the macOS file.

extension ImageWithCursorTracking {
    /// Apply this pass's automatic zoom, if one is due: the first-layout fit
    /// (and reveal), or a re-fit because the pane resized/rotated while the user
    /// hadn't taken manual control (#4279). Returns the scale applied, or `nil`
    /// when the zoom was left alone.
    private func applyAutomaticFit(
        scrollView: UIScrollView,
        coordinator: Coordinator,
        hasImage: Bool
    ) -> CGFloat? {
        // Only fit once the image has decoded (async now, #3864) so we don't consume
        // needsInitialCenter over an empty view.
        if coordinator.needsInitialCenter, hasImage,
           scrollView.bounds.width > 0,
           scrollView.bounds.height > 0 {
            coordinator.needsInitialCenter = false
            var applied: CGFloat?
            if let fitScale = coordinator.calculateFitScale() {
                scrollView.zoomScale = fitScale
                coordinator.noteAutoFitApplied()
                applied = fitScale
                Task { @MainActor in
                    self.scale = fitScale
                }
            }
            coordinator.centerContent()
            if scrollView.alpha < 1 {
                scrollView.alpha = 1
            }
            return applied
        }

        // Keep the fit current across pane resizes/rotation for as long as the
        // user hasn't zoomed manually.
        guard hasImage, let refit = coordinator.autoRefitScale() else { return nil }
        scrollView.zoomScale = refit
        Task { @MainActor in
            self.scale = refit
        }
        return refit
    }
}

#endif
