import CoreGraphics
import SwiftUI

/// The page's IMAGE as a layer that can be switched off (ruled 2026-09-27, the wireframes' Q2:
/// display switches are LAYERS -- the image on or off, the overlays on or off -- and overlays
/// without the image is a view the maintainer wants).
///
/// Off means the pixels are not DRAWN (`TrackingImageView.drawsImagePixels`), not that the image
/// view goes away or fades: its frame, zoom and scroll are what the boxes are drawn in, and the
/// document overlay lives INSIDE it (#5020, #5142), so hiding or fading the view would take the
/// boxes with it. It keeps receiving clicks as before.
enum ImageLayer {
    /// Shared by every image canvas; the What-to-show menu's "Show Image" writes it.
    static let defaultsKey = "imagePreview.imageVisible"
}

/// What a WORKSPACE says a preview pane's layers start as (ruled 2026-09-27, Q2: each layer has good
/// defaults tied to the workspace). Read from the pane's `PaneConfig` and published to its canvas;
/// nil fields follow the remembered default, as an unconfigured pane always has.
struct PreviewLayerDefaults: Equatable {
    var image: Bool?
    var wordBoxes: Bool?

    /// The value a layer starts at: the workspace's when it states one, else the one remembered.
    static func start(workspace: Bool?, remembered: Bool) -> Bool { workspace ?? remembered }

    /// Whether a change to a layer is remembered as the default for the next pane. A pane that
    /// opened at its WORKSPACE's value did not choose it, so writing it back would let opening
    /// one workspace change what every other pane opens with. A person moving the switch away
    /// from the workspace's value is remembered, as it always was.
    static func shouldRemember(_ value: Bool, workspace: Bool?) -> Bool { value != workspace }
}

private struct PanePreviewLayersKey: EnvironmentKey {
    static let defaultValue: PreviewLayerDefaults? = nil
}

extension EnvironmentValues {
    /// The layer defaults of THIS preview pane's workspace, published by `ContentView.paneNodeView`
    /// -- the same seam as `\.paneLibraryLayout`. nil outside a configured preview leaf.
    var panePreviewLayers: PreviewLayerDefaults? {
        get { self[PanePreviewLayersKey.self] }
        set { self[PanePreviewLayersKey.self] = newValue }
    }
}
