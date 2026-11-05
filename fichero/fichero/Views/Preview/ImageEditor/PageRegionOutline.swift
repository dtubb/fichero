import SwiftUI

/// The page's box as a dashed outline, drawn over a fitted image while no tool is chosen (`image.enhance.page-region-shown-in-the-app`,
/// #6187). Not interactive: the corner handles are the tool.
struct PageRegionOutline: View {
    let region: PageRegionSummary
    /// The image's frame within the container, in container coordinates.
    let fittedRect: CGRect

    var body: some View {
        Rectangle()
            .stroke(Color.accentColor.opacity(0.8), style: StrokeStyle(lineWidth: 1.5, dash: [6, 4]))
            .frame(width: region.box.width * fittedRect.width, height: region.box.height * fittedRect.height)
            .position(x: fittedRect.minX + (region.box.midX) * fittedRect.width,
                      y: fittedRect.minY + (region.box.midY) * fittedRect.height)
            .allowsHitTesting(false)
            .accessibilityIdentifier("pageRegionOutline")
    }
}

#Preview("Page region outline") {
    ZStack {
        Color.gray.opacity(0.2)
        if let region = PageRegionSummary(pageRegion: ["box": [0.3, 0.1, 0.6, 0.8], "method": "vision", "confidence": 0.95]) {
            PageRegionOutline(region: region, fittedRect: CGRect(x: 20, y: 20, width: 240, height: 320))
        }
    }
    .frame(width: 280, height: 360)
}
