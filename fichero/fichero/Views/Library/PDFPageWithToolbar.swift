import SwiftUI

// MARK: - PDFPageWithToolbar

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

    // Loupe settings — same AppStorage keys as PDFPageView.Coordinator reads,
    // so both stay in sync automatically via shared UserDefaults storage.
    @AppStorage("pdfPreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("pdfPreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("pdfPreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("pdfPreview.loupeLocked") private var loupeLocked = false

    @State private var loupePosition: CGPoint = .init(x: 0.5, y: 0.5)
    @State private var loupeLockedPosition: CGPoint = .init(x: 0.5, y: 0.5)

    private var scaleBinding: Binding<CGFloat> {
        Binding(
            get: { zoom.scale },
            set: { zoom.scale = $0 }
        )
    }

    private var effectiveLoupePosition: CGPoint {
        loupeLocked ? loupeLockedPosition : loupePosition
    }

    var body: some View {
        VStack(spacing: 0) {
            // Toolbar: zoom controls + loupe toggle. Uses MiniToolbar so the
            // PDF preview header is the same 44pt height as the list mode rail,
            // image preview, knowledge surface, and inspector tab strip (#1228).
            MiniToolbar {
                Button {
                    zoom.zoomOut()
                } label: {
                    Image(systemName: "minus.magnifyingglass")
                }
                .buttonStyle(.plain)
                .help("Zoom Out")

                Text("\(Int(zoom.scale * 100))%")
                    .font(.caption)
                    .monospacedDigit()
                    .frame(width: 50)

                Button {
                    zoom.zoomIn()
                } label: {
                    Image(systemName: "plus.magnifyingglass")
                }
                .buttonStyle(.plain)
                .help("Zoom In")

                Divider().frame(height: 16)

                Button {
                    zoom.fitToWindow()
                } label: {
                    Image(systemName: "arrow.up.left.and.arrow.down.right")
                }
                .buttonStyle(.plain)
                .help("Fit to Window")

                Button {
                    zoom.actualSize()
                } label: {
                    Image(systemName: "1.square")
                }
                .buttonStyle(.plain)
                .help("Actual Size (100%)")

                Divider().frame(height: 16)

                // Loupe controls
                HStack(spacing: 4) {
                    Button {
                        loupeEnabled.toggle()
                    } label: {
                        Image(systemName: loupeEnabled
                                ? "magnifyingglass.circle.fill"
                                : "magnifyingglass.circle")
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(loupeEnabled ? .accentColor : .primary)
                    .help("Toggle loupe")

                    if loupeEnabled {
                        Button {
                            if !loupeLocked { loupeLockedPosition = loupePosition }
                            loupeLocked.toggle()
                        } label: {
                            Image(systemName: loupeLocked ? "lock.fill" : "lock.open")
                        }
                        .buttonStyle(.plain)
                        .foregroundColor(loupeLocked ? .accentColor : .secondary)
                        .help(loupeLocked ? "Unlock loupe" : "Lock loupe")

                        Text(String(format: "%.1fx", loupeMagnification))
                            .font(.caption2)
                            .monospacedDigit()
                            .foregroundColor(.secondary)
                            .frame(width: 32)

                        Slider(value: $loupeMagnification, in: 1...8, step: 0.5)
                            .frame(width: 80)
                    }
                }

                Spacer()
            }

            Divider()

            ZStack {
                PDFPageView(
                    path: path,
                    pageIndex: pageIndex,
                    onPageIndexChange: onPageIndexChange,
                    zoomController: zoom,
                    onCursorMoved: { pos in loupePosition = pos }
                )

                if loupeEnabled {
                    PDFLoupeOverlay(
                        pdfPath: path,
                        pageIndex: pageIndex,
                        cursorPosition: effectiveLoupePosition,
                        magnification: loupeMagnification,
                        loupeSize: loupeSize
                    )
                    .allowsHitTesting(false)
                }
            }
        }
    }
}
