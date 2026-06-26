import SwiftUI

// MARK: - Source-page thumbnail for an image/PDF node (#1744)

/// Renders the actual page thumbnail for a source-backed node, loaded through
/// the storage service (so it works against a remote engine and respects auth —
/// never a local file path). Falls back to the kind icon while loading or if no
/// thumbnail is available. Mirrors the 3D scene's texture path
/// (`storageService.thumbnailData(for:)`).
struct SpatialNodeThumbnail: View {
    let sourceId: String
    let fallbackIcon: String
    let tint: Color
    let side: CGFloat
    /// LOD gate (#2298): when false (canvas zoomed out) the page thumbnail is
    /// not fetched — the cheap kind glyph is shown instead, so a zoomed-out
    /// overview of thousands of nodes issues zero thumbnail requests. An
    /// already-loaded thumbnail is kept (no flicker) until the view is recycled.
    var enabled: Bool = true

    @State private var thumbnail: Image?

    var body: some View {
        Group {
            if let thumbnail {
                thumbnail
                    .resizable()
                    .aspectRatio(contentMode: .fill)
            } else {
                Image(systemName: fallbackIcon)
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: side, height: side)
                    .background(tint, in: RoundedRectangle(cornerRadius: 3))
            }
        }
        .frame(width: side, height: side)
        .clipShape(RoundedRectangle(cornerRadius: 3))
        // Re-run when zoom crosses the LOD threshold (`enabled` flips), so
        // thumbnails load on zoom-in without a separate refresh path.
        .task(id: "\(sourceId)|\(enabled)") {
            guard enabled, thumbnail == nil else { return }
            thumbnail = (try? await LibraryManager.shared.globalLibrary?
                .storageService.getThumbnail(sourceId)) ?? nil
        }
    }
}
