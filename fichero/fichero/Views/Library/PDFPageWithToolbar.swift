import SwiftUI

// MARK: - PDFPageWithToolbar

/// PDF zoom toolbar mirroring the image viewer's ImageZoomToolbar.
/// Provides dedicated zoom controls for PDF documents.
struct PDFZoomToolbar: View {
    @Binding var scale: CGFloat

    let zoomIn: () -> Void
    let zoomOut: () -> Void
    let fitToWindow: () -> Void
    let actualSize: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button(action: zoomOut) {
                Image(systemName: "minus.magnifyingglass")
            }
            .buttonStyle(.plain)
            .help("Zoom Out")

            Text("\(Int(scale * 100))%")
                .font(.caption)
                .monospacedDigit()
                .frame(width: 50)

            Button(action: zoomIn) {
                Image(systemName: "plus.magnifyingglass")
            }
            .buttonStyle(.plain)
            .help("Zoom In")

            Divider()
                .frame(height: 16)

            Button(action: fitToWindow) {
                Image(systemName: "arrow.up.left.and.arrow.down.right")
            }
            .buttonStyle(.plain)
            .help("Fit to Window")

            Button(action: actualSize) {
                Image(systemName: "1.square")
            }
            .buttonStyle(.plain)
            .help("Actual Size (100%)")

            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Color(.windowBackgroundColor))
    }
}

/// PDFPageView previously bundled its own zoom toolbar (#656). The
/// embedded toolbar duplicated the document inspector's zoom controls
/// + the LibraryView icon-zoom strip, producing two stacked sets of
/// magnifier pills (#1010). The toolbar is now removed; PDFKit's
/// native ⌘+ / ⌘- still work, and the inspector toolbar remains the
/// canonical zoom surface.
struct PDFPageWithToolbar: View {
    let path: String
    let pageIndex: Int
    var onPageIndexChange: ((Int) -> Void)?

    @StateObject private var zoom = PDFZoomController()

    private var scaleBinding: Binding<CGFloat> {
        Binding(
            get: { zoom.scale },
            set: { zoom.scale = $0 }
        )
    }

    var body: some View {
        VStack(spacing: 0) {
            PDFZoomToolbar(
                scale: scaleBinding,
                zoomIn: { zoom.zoomIn() },
                zoomOut: { zoom.zoomOut() },
                fitToWindow: { zoom.fitToWindow() },
                actualSize: { zoom.actualSize() }
            )

            PDFPageView(
                path: path,
                pageIndex: pageIndex,
                onPageIndexChange: onPageIndexChange,
                zoomController: zoom
            )
        }
    }
}
