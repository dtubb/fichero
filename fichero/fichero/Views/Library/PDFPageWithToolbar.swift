import SwiftUI

// MARK: - PDFPageWithToolbar

/// PDFPageView previously bundled its own zoom toolbar (#656). The
/// embedded toolbar duplicated the document inspector's zoom controls
/// + the LibraryView icon-zoom strip, producing two stacked sets of
/// magnifier pills (#1010). The toolbar is now removed; PDFKit's
/// native ⌘+ / ⌘- still work, and the inspector toolbar remains the
/// canonical zoom surface.
struct PDFPageWithToolbar: View {
    let documentId: String
    let pageIndex: Int
    var onPageIndexChange: ((Int) -> Void)?
    /// Display name shown in the toolbar title slot.
    var documentTitle: String? = nil
    /// Called when the user taps the × close button. Omit to hide the button.
    var onClose: (() -> Void)? = nil

    @StateObject private var zoom = PDFZoomController()
    @StateObject private var pageNav = PDFPageController()

    // Each split-pane instance gets its own loupe state so toggling loupe
    // in one pane doesn't affect sibling panes. (@AppStorage would be shared
    // across all instances in the same window.)
    @State private var loupeEnabled = false
    @State private var loupeMagnification: Double = 3.0
    @State private var loupeSize: Double = 150.0
    @State private var loupeLocked = false

    @State private var loupePosition: CGPoint = .init(x: 0.5, y: 0.5)
    @State private var loupeLockedPosition: CGPoint = .init(x: 0.5, y: 0.5)

    @Environment(\.splitAxisActions) private var splitAxisActions
    // Secondary split panes manage their own page index so navigating in one
    // pane doesn't force all other panes to the same page.
    @Environment(\.isSecondarySplitPane) private var isSecondarySplitPane
    @State private var localPageIndex: Int = 0

    // Per-pane pin: when pinned, the pane ignores global selection changes
    // and stays on the document and page that were active at pin time.
    @State private var isPinned = false
    @State private var pinnedDocumentId: String? = nil

    /// Document ID to actually render — pinned value when locked, live prop otherwise.
    private var effectiveDocumentId: String {
        isPinned ? (pinnedDocumentId ?? documentId) : documentId
    }

    /// Which page to display: parent-driven for the primary unpinned pane,
    /// locally tracked for every secondary pane or any pinned pane.
    private var effectivePageIndex: Int {
        (isSecondarySplitPane || isPinned) ? localPageIndex : pageIndex
    }

    private var scaleBinding: Binding<CGFloat> {
        Binding(
            get: { zoom.scale },
            set: { zoom.scale = $0 }
        )
    }

    private var effectiveLoupePosition: CGPoint {
        loupeLocked ? loupeLockedPosition : loupePosition
    }

    /// X button action: collapses the active split when inside one,
    /// otherwise calls onClose to hide the whole pane.
    private func closePane() {
        if let actions = splitAxisActions {
            // H-split is more local than V-split; collapse it first so clicking X
            // on a pane in a row collapses that row, not the whole left/right split.
            if actions.hasHorizontal { actions.onToggleHorizontal(); return }
            if actions.hasVertical   { actions.onToggleVertical();   return }
        }
        onClose?()
    }

    var body: some View {
        VStack(spacing: 0) {
            // Toolbar: zoom controls + loupe toggle. Uses MiniToolbar so the
            // PDF preview header is the same 44pt height as the list mode rail,
            // image preview, knowledge surface, and inspector tab strip (#1228).
            // Layout: [× close] [title] [page nav] [spacer] [zoom] [loupe] | [split] [pin]
            MiniToolbar(content: {
                // × close — far left. Collapses active split if one is open;
                // otherwise hides the whole pane via onClose.
                let isInSplit = splitAxisActions.map { $0.hasVertical || $0.hasHorizontal } ?? false
                if onClose != nil || isInSplit {
                    Button {
                        closePane()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help(isInSplit ? "Close this split" : "Close this pane")

                    Divider().frame(height: 16)
                }

                if let title = documentTitle, !title.isEmpty {
                    Image(systemName: "doc.richtext")
                        .imageScale(.small)
                        .foregroundStyle(.secondary)
                    Text(title)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)

                    Divider().frame(height: 16)
                }

                // Page-within-document navigation (◀ N / M ▶). Document-scoped,
                // so it lives here on the canvas toolbar rather than the window
                // toolbar. Only shown for multi-page documents. (#1531)
                if pageNav.pageCount > 1 {
                    Button {
                        pageNav.goToPrevious()
                    } label: {
                        Image(systemName: "chevron.left")
                    }
                    .buttonStyle(.plain)
                    .disabled(!pageNav.canGoPrevious)
                    .help("Previous Page")
                    .accessibilityIdentifier("pdfPreviousPage")

                    Text("\(pageNav.pageIndex + 1) / \(pageNav.pageCount)")
                        .font(.caption)
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                        .frame(minWidth: 48)

                    Button {
                        pageNav.goToNext()
                    } label: {
                        Image(systemName: "chevron.right")
                    }
                    .buttonStyle(.plain)
                    .disabled(!pageNav.canGoNext)
                    .help("Next Page")
                    .accessibilityIdentifier("pdfNextPage")

                    Divider().frame(height: 16)
                }

                Spacer(minLength: 0)
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
            }, trailing: {
                // Pin — far right, after split buttons. Keeps this pane on its
                // current document + page while the global selection changes.
                Divider().frame(height: 16)

                Button {
                    if isPinned {
                        isPinned = false
                    } else {
                        pinnedDocumentId = documentId
                        localPageIndex = pageIndex
                        isPinned = true
                    }
                } label: {
                    Image(systemName: isPinned ? "pin.fill" : "pin")
                        .font(.system(size: 11))
                }
                .buttonStyle(.plain)
                .foregroundStyle(isPinned ? Color.accentColor : Color.secondary)
                .help(isPinned ? "Unpin — follow current selection" : "Pin to this document")
            })

            Divider()

            ZStack {
                PDFPageView(
                    documentId: effectiveDocumentId,
                    pageIndex: effectivePageIndex,
                    onPageIndexChange: { newIndex in
                        if isSecondarySplitPane || isPinned {
                            localPageIndex = newIndex
                        } else {
                            onPageIndexChange?(newIndex)
                        }
                    },
                    zoomController: zoom,
                    pageController: pageNav,
                    onCursorMoved: { pos in loupePosition = pos }
                )
                .onAppear { localPageIndex = pageIndex }
                .onChange(of: pageIndex) { _, newIndex in
                    // Primary unpinned pane: keep in step with parent selection.
                    // Secondary or pinned pane: ignore parent changes.
                    if !isSecondarySplitPane && !isPinned { localPageIndex = newIndex }
                }

                if loupeEnabled {
                    PDFLoupeOverlay(
                        documentId: effectiveDocumentId,
                        pageIndex: effectivePageIndex,
                        cursorPosition: effectiveLoupePosition,
                        magnification: loupeMagnification,
                        loupeSize: loupeSize
                    )
                    .allowsHitTesting(false)
                }
            }

            // Bottom annotation/editor toolbar — placeholder for tools
            // (highlight, note, drawing, etc.) that will live here.
            PaneFilterBar {
                Spacer(minLength: 0)
            }
        }
    }
}
