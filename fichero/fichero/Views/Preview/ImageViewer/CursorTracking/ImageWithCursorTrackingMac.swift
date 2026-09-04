#if canImport(AppKit)
import AppKit
import CoreImage
import ImageIO
import OSLog
import SwiftUI

/// NSViewRepresentable wrapper for an image view with cursor tracking and loupe functionality
struct ImageWithCursorTracking: NSViewRepresentable {
    static let logger = Logger(subsystem: "app.fichero.fichero", category: "ImageWithCursorTracking")

    let url: URL?
    /// When non-nil, this image is used directly instead of loading from `url`.
    /// Enables editor mode where the canvas shows a backend-rendered preview (#1402).
    var overrideImage: PlatformImage?
    /// Stable identity of the ITEM on screen. `url` is nil for every
    /// backend-rendered preview, so URL comparison called a sibling step
    /// "same item, new pixels" and preserved the previous page's WIDTH —
    /// a tall page then overflowed vertically (Daniel, 2026-08-21: "it
    /// doesn't scale to fit height, just width"). The width-preserving
    /// branch is for the hi-res upgrade of the SAME item only.
    var itemKey: String?
    /// Normalized rect to open ON instead of fit-to-window (entry ladder,
    /// 2026-08-23): the entry's band on its source page. Applied at the same
    /// two fit sites a plain open uses; nil keeps fit-to-window.
    var focusRegion: [Double]?
    @Binding var scale: CGFloat
    @Binding var cursorPosition: CGPoint  // Normalized 0-1 position in image
    @Binding var imageSize: CGSize
    /// The visible window plus the image's on-screen rect, as ONE value.
    ///
    /// These were two bindings written from two independent `@MainActor`
    /// hops, which let SwiftUI render a frame pairing a new visible window
    /// with a stale drawn frame — every box off by the difference, on any
    /// frame during a pinch (2026-08-20 bbox review, D3). One binding, one
    /// write, one transaction.
    @Binding var geometry: PreviewImageGeometry
    let minScale: CGFloat
    let maxScale: CGFloat
    let loupeEnabled: Bool
    let loupeLocked: Bool
    @Binding var loupeMagnification: CGFloat
    @Binding var loupeSize: CGFloat
    @Binding var coordinator: Coordinator?  // Exposed for external scroll control
    /// Region-layer input (2026-09-01): clicks/drags the loupe left alone,
    /// already NORMALIZED to image space. nil in hosts without a region layer.
    var onPointer: ((PreviewPointerEvent) -> Void)?

    /// The scroll view's own configuration — zoom limits, Preview.app-style
    /// overlay scrollers, and the initial hidden state that prevents a flash
    /// before the first centring pass.
    private func makeScrollView() -> NSScrollView {
        let scrollView = SiblingSwipeScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = true
        scrollView.allowsMagnification = true  // Use built-in Mac zoom behavior
        scrollView.minMagnification = minScale
        scrollView.maxMagnification = maxScale
        scrollView.magnification = scale
        // Semantic, theme-following ground (user, 2026-08-19: dark mode showed
        // a light-grey field behind the page). underPageBackground is the
        // system's "behind a document" color in both appearances — the same
        // ground Preview.app uses.
        // windowBackgroundColor, not underPage (Daniel, 2026-08-23: "grey
        // background of preview is too grey … the black background [should be]
        // a bit subtler"): lighter grey in light mode, softer than near-black
        // in dark — the Preview.app-like ground in both appearances.
        scrollView.backgroundColor = .windowBackgroundColor
        scrollView.scrollerStyle = .overlay  // Auto-hiding overlay scrollers like Preview.app
        scrollView.automaticallyAdjustsContentInsets = false
        scrollView.alphaValue = 0  // Hidden until first center to prevent flash
        scrollView.postsBoundsChangedNotifications = true
        scrollView.contentView.postsBoundsChangedNotifications = true
        return scrollView
    }

    /// Pinch-to-zoom for the loupe (alongside NSScrollView's own magnification)
    /// and double-click to zoom. The coordinator keeps a reference to each so it
    /// can enable and disable them.
    private func attachGestures(to scrollView: NSScrollView, coordinator: Coordinator) {
        let magnifyGesture = NSMagnificationGestureRecognizer(
            target: coordinator,
            action: #selector(Coordinator.handleMagnify(_:))
        )
        magnifyGesture.delegate = coordinator
        scrollView.addGestureRecognizer(magnifyGesture)
        coordinator.magnifyGesture = magnifyGesture

        let doubleClickGesture = NSClickGestureRecognizer(
            target: coordinator,
            action: #selector(Coordinator.handleDoubleClick(_:))
        )
        doubleClickGesture.numberOfClicksRequired = 2
        scrollView.addGestureRecognizer(doubleClickGesture)
        coordinator.doubleClickGesture = doubleClickGesture
    }

    /// The image view and the three callbacks that write cursor and loupe
    /// state back up. Each hops to the main actor before touching a binding,
    /// exactly as before — the closures capture `self` the same way they did
    /// inline, since a method's `self` is the same value.
    private func makeImageView() -> TrackingImageView {
        let imageView = TrackingImageView()
        imageView.imageScaling = .scaleNone  // We'll handle sizing
        // iPhone HEIC photos carry an HDR gain map. NSImageView defaults to
        // `.high` dynamic range on macOS 14+, which elevates the window's EDR
        // headroom and makes surrounding SDR UI look washed out. Lock to
        // `.standard` so photos render as tone-mapped SDR like Preview.app's
        // default behaviour.
        imageView.preferredImageDynamicRange = .standard
        imageView.onCursorMoved = { normalizedPos in
            Task { @MainActor in
                // Only update if position is within bounds (clamp to valid range)
                // This prevents edge artifacts when cursor leaves image area
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
        return imageView
    }

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = makeScrollView()
        attachGestures(to: scrollView, coordinator: context.coordinator)

        let imageView = makeImageView()

        scrollView.documentView = imageView
        context.coordinator.scrollView = scrollView
        context.coordinator.imageView = imageView
        wirePointer(imageView: imageView, scrollView: scrollView, coordinator: context.coordinator)

        // An override image is already decoded in memory — apply it synchronously.
        // A URL is decoded OFF the main thread (#3864); the placeholder (hidden
        // scroll view) shows until the ready image arrives, fit in the same turn.
        context.coordinator.currentOverrideImage = overrideImage
        if let overrideImage {
            imageView.image = overrideImage
            imageView.frame = NSRect(origin: .zero, size: overrideImage.size)
            Self.logger.info("makeNSView: Set image size=\(overrideImage.size.width)x\(overrideImage.size.height)")
            Task { @MainActor in
                self.imageSize = overrideImage.size
            }
        } else if let url {
            loadImageAsync(url: url, into: imageView, scrollView: scrollView, coordinator: context.coordinator)
        }
        Self.logger.info(
            "makeNSView: Set documentView, bounds=\(scrollView.bounds.width)x\(scrollView.bounds.height)"
        )

        // Observe scroll/zoom changes for visible rect
        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.boundsDidChange(_:)),
            name: NSView.boundsDidChangeNotification,
            object: scrollView.contentView
        )
        // ONE hop, so the two rects reach SwiftUI in a single transaction and
        // the overlay never maps a fresh crop through a stale frame (D3).
        context.coordinator.onGeometryChanged = { measured in
            Task { @MainActor in
                if self.geometry != measured {
                    self.geometry = measured
                }
            }
        }
        // #596 (2nd attempt): fires once at gesture end with the final
        // magnification. Writes the @Binding so updateNSView's sync-check
        // matches and doesn't revert the zoom. Gate on epsilon to avoid
        // a self-triggering re-render loop on the initial fit cascade.
        context.coordinator.onScaleChanged = { newScale in
            Task { @MainActor in
                if abs(self.scale - newScale) > 0.01 {
                    self.scale = newScale
                }
            }
        }

        // Initial center will happen in updateNSView after layout
        context.coordinator.needsInitialCenter = true

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        // Entry ladder: the region rung owns the vertical swipe axis even
        // though the page around the crop could pan (2026-08-23).
        (scrollView as? SiblingSwipeScrollView)?.verticalSwipeAlwaysNavigates =
            focusRegion != nil
        let hasImage = (context.coordinator.imageView as? NSImageView)?.image != nil
        // Scale this pass applied automatically (initial fit or resize re-fit).
        // #4279: when set, the magnification↔scale sync below must NOT run — the
        // `scale` binding is still one turn behind, and writing it back would
        // undo the fit in the very same pass, leaving the image at whatever
        // stale zoom the binding happened to hold.
        // FIRST-PINCH SNAP-BACK (Daniel, 2026-08-09 '#47'): the automatic
        // fit ran BEFORE the pinch gate, and the first pinch's re-render can
        // arrive before the recognizer reports .began — any pane-size delta
        // accrued since load (a panel appearing, an inspector settling) got
        // cashed in as a refit right under the user's fingers: zoom snapped
        // to fit, THEN pinching worked. A magnify event in flight means the
        // user is zooming NOW: suppress the automatic fit for this pass and
        // hand zoom ownership over (the same #4279 semantics .began applies,
        // just before .began exists).
        let pinchInFlight = context.coordinator.isUserMagnifying
            || NSApp.currentEvent?.type == .magnify
        if pinchInFlight {
            context.coordinator.markManualZoom()
        }
        let autoAppliedScale = pinchInFlight ? nil : applyAutomaticFit(
            scrollView: scrollView,
            coordinator: context.coordinator,
            hasImage: hasImage
        )

        // #596: skip the magnification→scale sync while a pinch is active.
        // NSMagnificationGestureRecognizer mutates scrollView.magnification
        // directly; writing `scale` back on every frame would race with
        // that write and effectively pin the zoom to the pre-pinch value.
        // The binding gets its write-back at gesture `.ended` via
        // `Coordinator.onScaleChanged` instead.
        if autoAppliedScale == nil,
           !context.coordinator.isUserMagnifying,
           context.coordinator.consumePendingScaleIfMatched(scale),
           abs(scrollView.magnification - scale) > 0.01 {
            scrollView.magnification = scale
        }

        if let imageView = context.coordinator.imageView as? TrackingImageView {
            syncLoupeState(on: imageView)
            applyImageChangeIfNeeded(
                imageView: imageView,
                scrollView: scrollView,
                coordinator: context.coordinator
            )
        }

        // Keep content centered when the viewport size changes.
        updateContentInsets(scrollView: scrollView, imageView: context.coordinator.imageView!)

        // Re-measure the overlay geometry after every updateNSView pass that
        // may have moved the fit: the boundsDidChange notification does NOT
        // fire for the initial layout/auto-fit, so the overlay kept its
        // mid-layout snapshot — boxes slightly off at fit, then EXACT the
        // moment any zoom forced a re-measure (Daniel's 100%-vs-134%
        // screenshot pair, 2026-08-21). Cheap: publishes only on change.
        context.coordinator.updateVisibleRect()

        // Some first-paint paths reach here with a loaded image and real bounds
        // but without the reveal callback having fired yet. Reveal eagerly so
        // the image doesn't stay blank until the next interaction.
        if scrollView.alphaValue < 1,
           scrollView.bounds.width > 0,
           scrollView.bounds.height > 0,
           let imageView = context.coordinator.imageView as? NSImageView,
           imageView.image != nil {
            scrollView.alphaValue = 1
        }

        // Update visible rect
        context.coordinator.updateVisibleRect()
    }

    /// Clicks and drags for the region layer, normalized through the SAME
    /// `PreviewImageGeometry` the overlays draw with (2026-09-04).
    ///
    /// This used to re-derive the drawn rect from `imageView` at event time
    /// (`DrawnImageFrame.drawnRect` + a bottom-left→top-left flip). That is a
    /// SECOND, independent derivation of the one mapping the overlay uses —
    /// and in the wild the two disagreed by a constant offset while every
    /// isolated round-trip test passed (Daniel, 2026-09-04: "I clicked first
    /// line, it selected last"; the mis-landed marquees decode as line boxes
    /// + exactly (0.185, 0.488) normalized). Mapping the pointer through the
    /// coordinator's last PUBLISHED geometry makes click-vs-draw agreement
    /// hold by construction: the layer's inverse mapping lands the point at
    /// exactly `panePoint - drawnFrame.origin`, the overlay's own space.
    ///
    /// The old derivation is kept ONLY as a tripwire: on every mouse-down the
    /// two are compared, and a divergence logs the full machine state under
    /// `pointer-triage` — so if the environmental cause recurs it names
    /// itself instead of moving a band.
    private func wirePointer(
        imageView: TrackingImageView,
        scrollView: NSScrollView,
        coordinator: Coordinator
    ) {
        imageView.onPointer = { [weak imageView, weak scrollView, weak coordinator] phase, viewPoint, event in
            guard let imageView, let scrollView, let coordinator,
                  imageView.image != nil, let onPointer = self.onPointer else { return }
            // Fresh measurement first: the event may arrive before any
            // boundsDidChange (first click after mount) or after a layout
            // the notification did not cover.
            if coordinator.lastGeometry?.isMeasured != true {
                coordinator.updateVisibleRect()
            }
            guard let geometry = coordinator.lastGeometry,
                  let normalized = PreviewPointerMapping.normalized(
                      // The scroll view is flipped, so its space IS the
                      // top-left pane space `drawnFrame` is measured in.
                      panePoint: scrollView.convert(event.locationInWindow, from: nil),
                      geometry: geometry
                  ) else { return }
            if phase == .pressed {
                Self.tripwireCompare(
                    normalized: normalized, viewPoint: viewPoint,
                    imageView: imageView, scrollView: scrollView
                )
            }
            onPointer(PreviewPointerEvent(
                phase: phase, point: normalized,
                shift: event.modifierFlags.contains(.shift),
                clickCount: event.clickCount
            ))
        }
    }

    /// The retired image-view-space derivation, run on mouse-down purely to
    /// DETECT divergence: agreement is silent; disagreement logs everything a
    /// diagnosis needs. Filter Console on `pointer-triage`.
    private static func tripwireCompare(
        normalized: CGPoint, viewPoint: CGPoint,
        imageView: NSImageView, scrollView: NSScrollView
    ) {
        let drawn = DrawnImageFrame.drawnRect(in: imageView)
        guard drawn.width > 0, drawn.height > 0 else { return }
        let legacy = CGPoint(
            x: (viewPoint.x - drawn.minX) / drawn.width,
            y: 1 - (viewPoint.y - drawn.minY) / drawn.height
        )
        guard abs(legacy.x - normalized.x) > 0.005 || abs(legacy.y - normalized.y) > 0.005 else { return }
        Logger(subsystem: "app.fichero.fichero", category: "pointer-triage").fault(
            """
            pointer-triage divergence: published=(\(normalized.x, format: .fixed(precision: 4)), \
            \(normalized.y, format: .fixed(precision: 4))) legacy=(\(legacy.x, format: .fixed(precision: 4)), \
            \(legacy.y, format: .fixed(precision: 4))) viewPoint=(\(viewPoint.x, format: .fixed(precision: 1)), \
            \(viewPoint.y, format: .fixed(precision: 1))) \
            drawnDoc=\(String(describing: drawn), privacy: .public) \
            imageBounds=\(String(describing: imageView.bounds), privacy: .public) \
            imageSize=\(String(describing: imageView.image?.size), privacy: .public) \
            alignment=\(imageView.imageAlignment.rawValue) scaling=\(imageView.imageScaling.rawValue) \
            mag=\(scrollView.magnification, format: .fixed(precision: 4)) \
            clipBounds=\(String(describing: scrollView.contentView.bounds), privacy: .public) \
            flipped=(sv: \(scrollView.isFlipped), iv: \(imageView.isFlipped))
            """
        )
    }

    func makeCoordinator() -> Coordinator {
        let coord = Coordinator()
        Task { @MainActor in
            self.coordinator = coord
        }
        return coord
    }

    /// Decode `url` OFF the main thread, then apply the ready image on the main actor
    /// (#3864). Marks the URL requested immediately so re-renders during the decode
    /// don't re-kick it, and takes a token so a superseded page-flip's late decode is
    /// dropped. Fits in the same turn as the image when bounds are known; otherwise
    /// defers to `updateNSView`'s (image-gated) initial fit.
    func loadImageAsync(
        url: URL,
        into imageView: TrackingImageView,
        scrollView: NSScrollView,
        coordinator: Coordinator
    ) {
        coordinator.currentURL = url
        coordinator.currentOverrideImage = nil
        // A different item is on screen — auto-fit owns the zoom again (#4279).
        coordinator.resetZoomOwnershipForNewItem()
        let token = coordinator.beginImageLoad()
        Task { @MainActor in
            guard let cgImage = await decodeSDRCGImage(from: url),
                  coordinator.isCurrentImageLoad(token) else { return }
            let image = NSImage(cgImage: cgImage, size: CGSize(width: cgImage.width, height: cgImage.height))
            imageView.image = image
            imageView.frame = NSRect(origin: .zero, size: image.size)
            imageView.loupePosition = nil
            self.imageSize = image.size
            if let fitScale = coordinator.calculateFitScale() {
                applyZoomOutFloor(scrollView, fitScale: fitScale)
                scrollView.magnification = fitScale
                coordinator.noteAutoFitApplied()
                self.scale = fitScale
                centerImage(scrollView: scrollView, imageView: imageView)
                if let region = focusRegion {
                    // Entry ladder: open ON the band, not the whole page.
                    coordinator.zoomToNormalizedRegion(region)
                }
                if scrollView.alphaValue < 1 { scrollView.alphaValue = 1 }
            } else {
                coordinator.needsInitialCenter = true
            }
            // Re-measure the overlay geometry HERE (entry-highlight fix,
            // 2026-08-23): this completion runs after updateNSView's trailing
            // re-measure, and the fit it just applied does not reliably fire
            // boundsDidChange (the recorded 2026-08-21 gap) — so the overlay
            // kept the PREVIOUS item's frame and the entry highlight drew
            // scaled and displaced against a stale drawnFrame.
            coordinator.updateVisibleRect()
        }
    }

    /// Zoom-out floor tracks fit (#4587): the user can zoom out to the
    /// fit-to-view scale (or to 100% for an image smaller than the pane),
    /// never to a 1% speck in a grey field. Applied wherever a fresh fit is
    /// computed, so the floor follows item and pane changes; AppKit clamps
    /// any lower magnification writes against it.
    func applyZoomOutFloor(_ scrollView: NSScrollView, fitScale: CGFloat) {
        // Half of fit, not fit exactly (user, 2026-08-19: "can't zoom out
        // enough now") — room to see the whole page with margin while still
        // never a 1% speck in a grey field.
        scrollView.minMagnification = min(fitScale * 0.5, 1.0)
    }

    /// Center the image by expanding the image view frame when the scaled image
    /// is smaller than the viewport, using imageAlignment for native centering.
    private func centerImage(scrollView: NSScrollView, imageView: NSView) {
        guard let imgView = imageView as? NSImageView, let image = imgView.image else {
            Self.logger.warning("centerImage: No image or imageView")
            return
        }

        layoutImageView(imgView, image: image, in: scrollView)
    }

    /// Keep the image view frame in sync with the viewport on resize/zoom.
    private func updateContentInsets(scrollView: NSScrollView, imageView: NSView) {
        guard let imgView = imageView as? NSImageView, let image = imgView.image else { return }

        layoutImageView(imgView, image: image, in: scrollView)
    }

    /// Shared layout: when the scaled image is smaller than the viewport,
    /// expand the image view frame so AppKit's imageAlignment centers it.
    private func layoutImageView(_ imgView: NSImageView, image: NSImage, in scrollView: NSScrollView) {
        let imageSize = image.size
        // contentSize, not bounds — legacy scrollers (see the coordinator's
        // updateContentInsetsForCurrentLayout, 2026-08-31).
        let viewSize = scrollView.contentSize
        let mag = scrollView.magnification
        let scaledW = imageSize.width * mag
        let scaledH = imageSize.height * mag

        // Determine needed frame size (at least viewport/mag, at least image size)
        let frameW = max(imageSize.width, viewSize.width / mag)
        let frameH = max(imageSize.height, viewSize.height / mag)

        let needsExpand = scaledW < viewSize.width || scaledH < viewSize.height
        let targetFrame = NSRect(origin: .zero, size: CGSize(width: frameW, height: frameH))

        if imgView.frame != targetFrame {
            imgView.frame = targetFrame
        }
        imgView.imageAlignment = needsExpand ? .alignCenter : .alignTopLeft

        // Clear any stale contentInsets from previous approach
        scrollView.contentInsets = NSEdgeInsets()
    }

}

// Same-file extension: these helpers left `updateNSView` for
// function_body_length, and holding them here keeps the struct body
// under type_body_length too. Private stays file-scoped and reachable.
extension ImageWithCursorTracking {
    /// Push the current loupe bindings onto the view, and open the loupe at
    /// centre the first time it is enabled — after a short settle, because
    /// drawing it before the view has bounds puts it in the wrong place.
    private func syncLoupeState(on imageView: TrackingImageView) {
        // Update loupe enabled state
        imageView.loupeEnabled = loupeEnabled

        // Auto-show loupe at center when enabled and no position exists
        // Use slight delay to let view settle before drawing
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
    }

    /// Swap in a new page when the override image or the URL changed. An
    /// already-decoded override applies synchronously and fits in the same
    /// frame; a URL decodes off the main thread (#3864) with the previous page
    /// left on screen until the new one can swap in already fitted.
    private func applyImageChangeIfNeeded(
        imageView: TrackingImageView,
        scrollView: NSScrollView,
        coordinator: Coordinator
    ) {
        // Detect image change: either a new overrideImage or a new URL.
        let overrideChanged = overrideImage !== coordinator.currentOverrideImage
        let urlChanged = coordinator.currentURL != url
        let needsImageUpdate = overrideImage != nil ? overrideChanged : urlChanged
        guard needsImageUpdate else { return }

        if let overrideImage {
            // SAME item, higher resolution (2026-08-11): the hi-res image
            // arrives asynchronously moments after the display-size one, and
            // treating it as "a different item" re-fitted the zoom — right
            // under the user's first pinch ("it immediately snaps back to
            // zoomed out, then I can pinch and it remembers"). A swap whose
            // URL is unchanged preserves the on-screen view instead: same
            // apparent size (magnification scaled by the pixel-width ratio),
            // same scroll position, zoom ownership untouched.
            let itemChanged = itemKey != coordinator.currentItemKey
            coordinator.currentItemKey = itemKey
            if !urlChanged, !itemChanged, let old = coordinator.currentOverrideImage,
               old.size.width > 0, overrideImage.size.width > 0 {
                applySameItemPixelSwap(
                    overrideImage, replacing: old,
                    imageView: imageView, scrollView: scrollView,
                    coordinator: coordinator
                )
                return
            }
            // Already-decoded override: apply synchronously, fit in the same
            // frame so the new image never renders at the old magnification
            // for a frame (#773/#777).
            PreviewSwapAnimation.runPending(on: imageView)
            imageView.image = overrideImage
            imageView.frame = NSRect(origin: .zero, size: overrideImage.size)
            imageView.loupePosition = nil  // Reset loupe on image change
            coordinator.currentURL = url
            coordinator.currentOverrideImage = overrideImage
            // A different item is on screen — auto-fit owns the zoom
            // again until the user zooms this one manually (#4279).
            // Deliberately no `noteAutoFitApplied()` here: this branch
            // runs *after* this pass's magnification↔scale sync, so
            // leaving the recorded pane size cleared makes the next
            // pass re-assert the fit if the (one-turn-late) binding
            // write hasn't landed yet.
            coordinator.resetZoomOwnershipForNewItem()
            Task { @MainActor in
                self.imageSize = overrideImage.size
            }
            if let fitScale = coordinator.calculateFitScale() {
                applyZoomOutFloor(scrollView, fitScale: fitScale)
                scrollView.magnification = fitScale
                Task { @MainActor in
                    self.scale = fitScale
                }
            }
            centerImage(scrollView: scrollView, imageView: imageView)
            if let region = focusRegion {
                coordinator.zoomToNormalizedRegion(region)
            }
            if scrollView.alphaValue < 1 { scrollView.alphaValue = 1 }
            // Same re-measure as the async completion: the fit this branch
            // applies is exactly the auto-fit boundsDidChange misses.
            coordinator.updateVisibleRect()
        } else if let url {
            // Decode the new page OFF the main thread (#3864). The previous
            // page stays visible until the ready image swaps in fitted, in one
            // turn — no main-thread block, no wrong-magnification flash.
            loadImageAsync(url: url, into: imageView, scrollView: scrollView, coordinator: coordinator)
        }
    }

    /// SAME item, new pixels — the hi-res upgrade: preserve the on-screen
    /// view exactly (apparent size via the pixel-width ratio, scroll origin,
    /// zoom ownership untouched). Extracted from `applyImageChangeIfNeeded`
    /// for function_body_length.
    private func applySameItemPixelSwap(
        _ overrideImage: PlatformImage, replacing old: PlatformImage,
        imageView: TrackingImageView, scrollView: NSScrollView,
        coordinator: ImageWithCursorTrackingMacCoordinator
    ) {
        let ratio = old.size.width / overrideImage.size.width
        let preservedMagnification = scrollView.magnification * ratio
        let visibleOrigin = scrollView.contentView.bounds.origin
        PreviewSwapAnimation.runPending(on: imageView)
        imageView.image = overrideImage
        imageView.frame = NSRect(origin: .zero, size: overrideImage.size)
        coordinator.currentOverrideImage = overrideImage
        Task { @MainActor in
            self.imageSize = overrideImage.size
        }
        scrollView.magnification = preservedMagnification
        scrollView.contentView.scroll(
            to: NSPoint(x: visibleOrigin.x / ratio, y: visibleOrigin.y / ratio)
        )
        // The binding write lands a turn later — park the value so the
        // magnification↔scale sync doesn't snap back to the stale scale.
        coordinator.pendingProgrammaticScale = preservedMagnification
        // Third of the three image-swap endpoints — same stale-geometry class.
        coordinator.updateVisibleRect()
        Task { @MainActor in
            self.scale = preservedMagnification
        }
    }
}

// MARK: - Automatic Fit (#4279)
// In an extension so the representable's own body stays within the
// type-body-length budget.

extension ImageWithCursorTracking {
    /// Apply this pass's automatic zoom, if one is due: the first-layout fit
    /// (and reveal), or a re-fit because the pane resized while the user hadn't
    /// taken manual control (#4279). Returns the scale applied, or `nil` when
    /// the zoom was left alone.
    private func applyAutomaticFit(
        scrollView: NSScrollView,
        coordinator: Coordinator,
        hasImage: Bool
    ) -> CGFloat? {
        // Fit-to-window and center on first layout when bounds are known AND the
        // image has actually decoded (#3864 — the decode is now async, so an early
        // updateNSView can run before the image exists; don't reveal an empty frame).
        if coordinator.needsInitialCenter && hasImage
            && scrollView.bounds.width > 0 && scrollView.bounds.height > 0 {
            coordinator.needsInitialCenter = false
            // Fit to window on first layout (like Preview.app)
            var applied: CGFloat?
            if let fitScale = coordinator.calculateFitScale() {
                applyZoomOutFloor(scrollView, fitScale: fitScale)
                scrollView.magnification = fitScale
                coordinator.noteAutoFitApplied()
                applied = fitScale
                Task { @MainActor in
                    self.scale = fitScale
                }
            }
            centerImage(scrollView: scrollView, imageView: coordinator.imageView!)
            // Reveal after centering (was hidden to prevent flash)
            if scrollView.alphaValue < 1 {
                scrollView.alphaValue = 1
            }
            return applied
        }

        // Keep the fit current as the pane resizes, for as long as the user
        // hasn't zoomed manually. A manual zoom freezes the scale until a
        // different image is displayed.
        guard hasImage, let refit = coordinator.autoRefitScale() else { return nil }
        scrollView.magnification = refit
        Task { @MainActor in
            self.scale = refit
        }
        return refit
    }
}

#endif
