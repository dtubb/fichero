import AppKit
import OSLog
import Quartz
import SwiftUI

// MARK: - Smart Preview View

struct SmartPreviewView: View {
    let url: URL
    var documentId: String?

    private var isImage: Bool {
        let imageExtensions = ["jpg", "jpeg", "png", "gif", "tiff", "tif", "bmp", "heic", "webp"]
        let ext = url.pathExtension.lowercased()
        return imageExtensions.contains(ext)
    }

    var body: some View {
        if isImage {
            ZoomableImagePreview(url: url, documentId: documentId)
        } else {
            QuickLookPreviewView(url: url)
        }
    }
}

// MARK: - Quick Look Preview View (NSViewRepresentable)

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

// MARK: - Swipe-to-navigate monitor (#593)

/// Invisible background view that monitors NSEvent.swipe events
/// (two/three-finger trackpad horizontal swipes) and calls the provided
/// navigation callbacks. Lifetime is scoped to the host view via
/// onAppear/onDisappear so we don't leak the local NSEvent monitor.
///
/// NSEvent.swipe is discrete from .scrollWheel and .magnify — adding
/// it alongside pinch-to-zoom and PDF scrolling produces no event-routing
/// conflict. Swift macOS lacks NSSwipeGestureRecognizer; the
/// addLocalMonitorForEvents pattern is the supported approach (see
/// MEMORY.md `feedback_nsswipe_gesture_missing`).
struct SwipeSiblingNavigator: View {
    var onNavigatePrevious: () -> Void
    var onNavigateNext: () -> Void

    @State private var monitor: Any?

    var body: some View {
        Color.clear
            .onAppear {
                let prev = onNavigatePrevious
                let next = onNavigateNext
                monitor = NSEvent.addLocalMonitorForEvents(matching: .swipe) { event in
                    if event.deltaX > 0 {
                        prev()
                    } else if event.deltaX < 0 {
                        next()
                    }
                    return event
                }
            }
            .onDisappear {
                if let existing = monitor {
                    NSEvent.removeMonitor(existing)
                    monitor = nil
                }
            }
    }
}
