import FicheroAPIClient
import SwiftUI

#if canImport(UIKit)

/// True full-screen image/page presentation for iPhone (#2607).
///
/// The inline `ZoomableImagePreview` lives inside a `NavigationStack` detail
/// on iPhone, so it carries a title bar, back button, and the mini-toolbar —
/// which waste most of a small screen when you just want to read the source.
/// This cover fills the entire screen edge-to-edge on a black background with
/// no chrome, reusing `ImageWithCursorTracking` so pinch-zoom/pan come for
/// free (no parallel image stack). A close button always dismisses; a
/// downward swipe does too when the image isn't being panned.
struct FullScreenImagePreview: View {
    let url: URL?
    let renderedImage: PlatformImage?

    @Environment(\.dismiss) var dismiss

    @State var scale: CGFloat = 1.0
    @State var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)
    @State var imageSize: CGSize = .zero
    @State var visibleRect: CGRect = .zero
    @State var loupeMagnification: CGFloat = 3.0
    @State var loupeSize: CGFloat = 150.0
    @State var imageCoordinator: ImageWithCursorTracking.Coordinator?
    @State var dragOffset: CGFloat = 0

    let minScale: CGFloat = 0.01
    let maxScale: CGFloat = 10.0

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Color.black.ignoresSafeArea()

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
                    loupeEnabled: false,
                    loupeLocked: false,
                    loupeMagnification: $loupeMagnification,
                    loupeSize: $loupeSize,
                    coordinator: $imageCoordinator
                )
                .ignoresSafeArea()
            } else {
                ContentUnavailableView(
                    "Image Preview",
                    systemImage: "photo",
                    description: Text("The image could not be loaded.")
                )
                .foregroundStyle(.white)
            }

            // Close affordance — respects the safe area so it stays tappable
            // under the notch / Dynamic Island.
            Button {
                dismiss()
            } label: {
                Image(systemName: "xmark")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(12)
                    .background(.ultraThinMaterial, in: Circle())
            }
            .padding(.top, 8)
            .padding(.trailing, 16)
            .help("Close full-screen image")
            .accessibilityIdentifier("fullScreenImageClose")
            .accessibilityLabel("Close Full Screen")
        }
        .offset(y: dragOffset)
        .gesture(
            DragGesture(minimumDistance: 20)
                .onChanged { value in
                    if value.translation.height > 0 {
                        dragOffset = value.translation.height
                    }
                }
                .onEnded { value in
                    if value.translation.height > 120 {
                        dismiss()
                    } else {
                        withAnimation(.spring(response: 0.3)) { dragOffset = 0 }
                    }
                }
        )
        #if os(iOS)
        .statusBarHidden(true)
        #endif
    }
}

#Preview("Compact Zoomable Image Preview") {
    ZoomableImagePreview(renderedImage: UIImage(systemName: "photo"))
        .environment(StorageService(ficheroClient: FicheroClient(libraryPath: nil)))
        .frame(width: 280, height: 360)
}

#endif
