import CoreGraphics

/// The page's IMAGE as a layer that can be switched off (ruled 2026-09-27, the wireframes' Q2:
/// display switches are LAYERS -- the image on or off, the overlays on or off -- and overlays
/// without the image is a view the maintainer wants).
///
/// Off means the pixels are not DRAWN, not that the image view goes away: its frame, zoom and
/// scroll position are what every overlay is laid out against, so hiding the view would move or
/// drop every box. Alpha, not `isHidden`: a hidden AppKit view stops receiving the clicks and
/// drags the region layer is fed from, and an alpha-0 one does not.
enum ImageLayer {
    /// Shared by every image canvas; the What-to-show menu's "Show Image" writes it.
    static let defaultsKey = "imagePreview.imageVisible"

    static func alpha(visible: Bool) -> CGFloat { visible ? 1 : 0 }
}
