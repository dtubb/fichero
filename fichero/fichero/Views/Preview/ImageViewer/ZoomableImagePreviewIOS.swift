import FicheroAPIClient
import OSLog
import SwiftUI

#if !os(macOS)

struct ZoomableImagePreview: View {
    var url: URL?
    var documentId: String?
    var renderedImage: PlatformImage?
    /// Fired when the user steps to a sibling image in the folder image viewer.
    var onNavigateToDocument: ((String) -> Void)?
    /// API parity with the macOS variant so the shared `DocumentCanvas` call
    /// site compiles on every platform. The image editor is macOS-only, so this
    /// is unused here. (#2421)
    var isEditing: Binding<Bool>?

    init(
        url: URL? = nil,
        documentId: String? = nil,
        renderedImage: PlatformImage? = nil,
        onNavigateToDocument: ((String) -> Void)? = nil,
        isEditing: Binding<Bool>? = nil
    ) {
        self.url = url
        self.documentId = documentId
        self.renderedImage = renderedImage
        self.onNavigateToDocument = onNavigateToDocument
        self.isEditing = isEditing
    }

    @Environment(DocumentStore.self) var documentStore
    @Environment(StorageService.self) var storageService
    @Environment(\.horizontalSizeClass) var horizontalSizeClass

    @State var scale: CGFloat = 1.0
    @State var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)
    @State var imageSize: CGSize = .zero
    @State var visibleRect: CGRect = .zero
    @State var loupeMagnification: CGFloat = 3.0
    @State var loupeSize: CGFloat = 150.0
    @State var loupeEnabled: Bool = false
    @State var loupeLocked: Bool = false
    @State var imageCoordinator: ImageWithCursorTracking.Coordinator?

    /// Drives the iPhone true-full-screen presentation (#2607). Compact only.
    @State var showingFullScreen = false

    let minScale: CGFloat = 0.01
    let maxScale: CGFloat = 10.0

    var isCompact: Bool {
        horizontalSizeClass == .compact
    }

    var hasImage: Bool {
        renderedImage != nil || url != nil
    }

    /// Image/page siblings in the current folder, in display order.
    var siblingImageDocs: [Document] {
        guard documentId != nil else { return [] }
        return documentStore.currentDocuments.filter { $0.fileType == .image || $0.docType == .page }
    }

    var currentImageIndex: Int? {
        guard let documentId else { return nil }
        return siblingImageDocs.firstIndex(where: { $0.id == documentId })
    }

    var previousAction: (() -> Void)? {
        guard let onNavigateToDocument,
              let index = currentImageIndex,
              index > 0 else { return nil }
        let target = siblingImageDocs[index - 1]
        return { onNavigateToDocument(target.id) }
    }

    var nextAction: (() -> Void)? {
        guard let onNavigateToDocument,
              let index = currentImageIndex,
              index < siblingImageDocs.count - 1 else { return nil }
        let target = siblingImageDocs[index + 1]
        return { onNavigateToDocument(target.id) }
    }

    /// Document ids in the +/-`radius` window around `currentId`, excluding `currentId` itself.
    /// Static so it can be called in unit tests without a live view (#2469).
    static func preloadIds(from docs: [Document], currentId: String, radius: Int = 3) -> [String] {
        guard let index = docs.firstIndex(where: { $0.id == currentId }) else { return [] }
        let start = max(0, index - radius)
        let end = min(docs.count - 1, index + radius)
        guard start <= end else { return [] }
        return (start...end).compactMap { idx in idx == index ? nil : docs[idx].id }
    }

    var body: some View {
        VStack(spacing: 0) {
            ZStack(alignment: .bottom) {
                Group {
                    if renderedImage != nil || url != nil {
                        ImageWithCursorTracking(
                            url: url,
                            overrideImage: renderedImage,
                            scale: $scale,
                            cursorPosition: $cursorPosition,
                            imageSize: $imageSize,
                            visibleRect: $visibleRect,
                            minScale: minScale,
                            maxScale: maxScale,
                            loupeEnabled: loupeEnabled,
                            loupeLocked: loupeLocked,
                            loupeMagnification: $loupeMagnification,
                            loupeSize: $loupeSize,
                            coordinator: $imageCoordinator
                        )
                    } else {
                        ContentUnavailableView(
                            "Image Preview",
                            systemImage: "photo",
                            description: Text("The image could not be loaded.")
                        )
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color(white: 0.88, opacity: 1.0))
                // Tap the image to go true full-screen on iPhone and iPad
                // (#2607; extended to iPad regular width for #2520).
                .contentShape(Rectangle())
                .onTapGesture {
                    if hasImage {
                        showingFullScreen = true
                    }
                }

                // iOS touch prev/next overlay for folder image siblings (#2420).
                if previousAction != nil || nextAction != nil {
                    HStack(spacing: 16) {
                        Button {
                            previousAction?()
                        } label: {
                            Image(systemName: "chevron.left")
                                .font(.title3.weight(.semibold))
                                .frame(width: 40, height: 40)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(previousAction == nil)
                        .help("Show the previous image in this folder")
                        .accessibilityLabel("Previous image")
                        .accessibilityIdentifier("folderImagePrev")

                        Button {
                            nextAction?()
                        } label: {
                            Image(systemName: "chevron.right")
                                .font(.title3.weight(.semibold))
                                .frame(width: 40, height: 40)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(nextAction == nil)
                        .help("Show the next image in this folder")
                        .accessibilityLabel("Next image")
                        .accessibilityIdentifier("folderImageNext")
                    }
                    .padding(.bottom, 16)
                    .padding(.horizontal, 24)
                }
            }

            // Bottom-anchored mini-toolbar (#3060 / #2670): matches the macOS
            // ReaderToolbar and every other pane bar — content above, bar below.
            Divider()

            MiniToolbar {
                Spacer(minLength: 0)
                if isCompact {
                    Text("\(Int(scale * 100))%")
                        .font(.caption)
                        .monospacedDigit()
                        .foregroundStyle(.secondary)

                    if hasImage {
                        Button {
                            showingFullScreen = true
                        } label: {
                            Image(systemName: "arrow.up.left.and.arrow.down.right")
                        }
                        .buttonStyle(.plain)
                        .padding(.leading, 8)
                        .accessibilityIdentifier("enterFullScreenImage")
                        .accessibilityLabel("View Full Screen")
                    }
                } else {
                    Button(action: zoomOut) {
                        Image(systemName: "minus.magnifyingglass")
                    }
                    .buttonStyle(.plain)
                    .help("Zoom Out")
                    .accessibilityLabel("Zoom Out")

                    Text("\(Int(scale * 100))%")
                        .font(.caption)
                        .monospacedDigit()
                        .frame(width: 50)

                    Button(action: zoomIn) {
                        Image(systemName: "plus.magnifyingglass")
                    }
                    .buttonStyle(.plain)
                    .help("Zoom In")
                    .accessibilityLabel("Zoom In")

                    Divider()
                        .frame(height: 16)

                    Button(action: fitToWindow) {
                        Image(systemName: "arrow.up.left.and.arrow.down.right")
                    }
                    .buttonStyle(.plain)
                    .help("Fit to Window")
                    .accessibilityLabel("Fit to Window")

                    Button(action: actualSize) {
                        Image(systemName: "1.square")
                    }
                    .buttonStyle(.plain)
                    .help("Actual Size (100%)")
                    .accessibilityLabel("Actual Size (100%)")

                    // Immersive full-screen entry on iPad regular width too, not
                    // just iPhone-compact. Reuses the #2607 FullScreenImagePreview
                    // cover (black background, page-only, zoom) — no parallel
                    // viewer (#2520; #2487 is a duplicate of this).
                    if hasImage {
                        Divider()
                            .frame(height: 16)

                        Button {
                            showingFullScreen = true
                        } label: {
                            Image(systemName: "viewfinder")
                        }
                        .buttonStyle(.plain)
                        .help("View Full Screen")
                        .accessibilityIdentifier("enterFullScreenImageRegular")
                        .accessibilityLabel("View Full Screen")
                    }
                }

                Spacer()
            }
        }
        .task(id: documentId) { await preloadImages() }
        .fullScreenCover(isPresented: $showingFullScreen) {
            FullScreenImagePreview(url: url, renderedImage: renderedImage)
        }
    }

    // MARK: - Event Handlers

    private func preloadImages() async {
        guard let docId = documentId else { return }
        let neighbors = Self.preloadIds(from: siblingImageDocs, currentId: docId)
        guard !neighbors.isEmpty else { return }
        await storageService.prefetchDisplayImages(neighbors)
    }

    // MARK: - Zoom Actions

    func zoomIn() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = min(scale * 1.25, maxScale)
        }
    }

    func zoomOut() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = max(scale / 1.25, minScale)
        }
    }

    func fitToWindow() {
        if let fitScale = imageCoordinator?.calculateFitScale() {
            scale = fitScale
            DispatchQueue.main.async {
                imageCoordinator?.centerContent()
            }
        }
    }

    func actualSize() {
        scale = 1.0
        DispatchQueue.main.async {
            imageCoordinator?.centerContent()
        }
    }
}

#endif
