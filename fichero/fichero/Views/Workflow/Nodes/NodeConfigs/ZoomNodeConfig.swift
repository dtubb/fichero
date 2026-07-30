import SwiftUI

// MARK: - Tile-grid math (pure, mirrors the server's zoom tool)

/// Client-side mirror of the `zoom` tool's tiling math
/// (fichero-server `workflows/tools/zoom.py`): horizontal strips with a
/// configurable overlap, each upscaled by `scale`. Pure so the preview and
/// its tests share the exact geometry the server will cut (#4323).
/// Geometry-aligned tiling (tiles following detected text lines) is the
/// #4309/#4340 follow-up; this is the blind-grid preview.
enum ZoomTileGrid {
    struct Tile: Equatable {
        /// Vertical extent as fractions of the page height (0...1).
        let top: Double
        let bottom: Double
    }

    /// Server default: rows=0 means "choose from image height" —
    /// one ~400px strip per row.
    static func effectiveRows(imageHeight: Int, rows: Int) -> Int {
        if rows > 0 { return rows }
        return max(1, Int((Double(imageHeight) / 400.0).rounded(.up)))
    }

    /// Fractional strip extents for a page of `imageHeight` pixels.
    /// Mirrors zoom.py: stripHeight = ceil(h/rows),
    /// overlapPixels = round(stripHeight · overlap), clamped to the page.
    static func tiles(imageHeight: Int, rows: Int, overlap: Double) -> [Tile] {
        guard imageHeight > 0 else { return [] }
        let clampedOverlap = min(0.3, max(0.0, overlap))
        let rowCount = effectiveRows(imageHeight: imageHeight, rows: rows)
        let stripHeight = Int((Double(imageHeight) / Double(rowCount)).rounded(.up))
        let overlapPixels = Int((Double(stripHeight) * clampedOverlap).rounded())
        let height = Double(imageHeight)

        return (0..<rowCount).map { index in
            let top = max(0, index * stripHeight - overlapPixels)
            let bottom = min(imageHeight, (index + 1) * stripHeight + overlapPixels)
            return Tile(top: Double(top) / height, bottom: Double(bottom) / height)
        }
    }
}

// MARK: - Preview view

/// Live tile-grid preview for the Zoom node: a stylized sample page with the
/// configured strips overlaid, updating as rows/overlap/scale change (#4323).
struct ZoomTileGridPreview: View {
    let node: WorkflowNode

    /// Representative manuscript page height in pixels, used for the
    /// rows=0 ("Auto") derivation. Matches a typical ~200dpi scan.
    static let samplePageHeight = 1600
    private static let sampleTextLineCount = 14

    private var rows: Int {
        node.config?["rows"]?.intValue ?? 0
    }

    private var overlap: Double {
        node.config?["overlap"]?.doubleValue ?? 0.15
    }

    private var scale: Double {
        node.config?["scale"]?.doubleValue ?? 2.0
    }

    private var mode: String {
        node.config?["mode"]?.stringValue ?? "tile"
    }

    private var tiles: [ZoomTileGrid.Tile] {
        ZoomTileGrid.tiles(imageHeight: Self.samplePageHeight, rows: rows, overlap: overlap)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Tiling Preview")
                .font(.caption)
                .foregroundStyle(.secondary)

            if mode == "region" {
                Text("Region mode crops one fixed rectangle — set x, y, width, and height below.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            } else {
                samplePage
                    .frame(height: 180)
                summaryLine
            }
        }
    }

    private var samplePage: some View {
        GeometryReader { proxy in
            let size = proxy.size
            ZStack(alignment: .topLeading) {
                // Stylized sample page with fake text lines.
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color(.textBackgroundColor))
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.secondary.opacity(0.4), lineWidth: 1)
                    )
                ForEach(0..<Self.sampleTextLineCount, id: \.self) { line in
                    let lineY = size.height * (0.06 + 0.9 * Double(line) / Double(Self.sampleTextLineCount))
                    RoundedRectangle(cornerRadius: 1)
                        .fill(Color.secondary.opacity(0.35))
                        .frame(width: size.width * (line % 4 == 3 ? 0.55 : 0.8), height: 2)
                        .offset(x: size.width * 0.08, y: lineY)
                }

                // The configured strips, alternating tints so overlaps read.
                ForEach(Array(tiles.enumerated()), id: \.offset) { index, tile in
                    let top = size.height * tile.top
                    let height = size.height * (tile.bottom - tile.top)
                    Rectangle()
                        .fill((index.isMultiple(of: 2) ? Color.pink : Color.blue).opacity(0.14))
                        .overlay(alignment: .top) {
                            Rectangle()
                                .fill(Color.pink.opacity(0.5))
                                .frame(height: 1)
                        }
                        .overlay(alignment: .bottom) {
                            Rectangle()
                                .fill(Color.pink.opacity(0.5))
                                .frame(height: 1)
                        }
                        .frame(width: size.width, height: height)
                        .offset(y: top)
                }
            }
        }
        .accessibilityLabel("Tile grid preview: \(tiles.count) strips")
    }

    private var summaryLine: some View {
        let rowLabel = rows > 0 ? "\(tiles.count) rows" : "Auto (\(tiles.count) rows)"
        return Text("\(rowLabel) · \(Int((min(0.3, max(0, overlap)) * 100).rounded()))% overlap · each strip enlarged ×\(scale, specifier: "%.1f")")
            .font(.caption2)
            .foregroundStyle(.secondary)
            .monospacedDigit()
    }
}
