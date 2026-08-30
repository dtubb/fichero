#if os(macOS)
import SwiftUI

// MARK: - The magnification family cluster (Daniel, 2026-08-29)
//
// "Where am I and how close am I are one concern." One floating cluster,
// BOTTOM-RIGHT of the canvas, stacked:
//   • mini-map on top (when the map has something to say),
//   • the zoom pill under it (− % + · fit · 1:1),
//   • a small third row with the LOUPE and magnifier-bar toggles.
// When the map is hidden the cluster collapses to the zoom pill (plus the
// toggles row where the host supports them). Nothing of this family remains
// in the bottom bar.

struct PreviewZoomMapCluster<Map: View>: View {
    var scalePercent: Int
    var zoomIn: () -> Void
    var zoomOut: () -> Void
    var fitToWindow: () -> Void
    var actualSize: () -> Void
    /// nil hides the loupe toggle (host without a loupe).
    var loupeEnabled: Binding<Bool>?
    /// nil hides the magnifier-bar toggle (e.g. the PDF page).
    var magnifierEnabled: Binding<Bool>?
    /// The mini-map, or EmptyView to collapse the cluster to the pill.
    @ViewBuilder var map: () -> Map

    var body: some View {
        VStack(alignment: .trailing, spacing: 8) {
            map()
            zoomPill
            togglesRow
        }
        .padding(8)
    }

    private var zoomPill: some View {
        HStack(spacing: 6) {
            pillButton("minus.magnifyingglass", help: "Zoom Out", action: zoomOut)
            Text("\(scalePercent)%")
                .font(.caption)
                .monospacedDigit()
                .foregroundStyle(.secondary)
                .frame(minWidth: 40)
            pillButton("plus.magnifyingglass", help: "Zoom In", action: zoomIn)
            Divider().frame(height: 14)
            pillButton("arrow.up.left.and.arrow.down.right", help: "Fit to Window", action: fitToWindow)
            pillButton("1.square", help: "Actual Size (100%)", action: actualSize)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .glassEffect(.regular, in: Capsule())
        .accessibilityIdentifier("previewZoomPill")
    }

    @ViewBuilder
    private var togglesRow: some View {
        if loupeEnabled != nil || magnifierEnabled != nil {
            HStack(spacing: 6) {
                if let loupeEnabled {
                    pillToggle(
                        loupeEnabled,
                        icon: "magnifyingglass.circle",
                        activeIcon: "magnifyingglass.circle.fill",
                        help: "Loupe — follows the cursor; scroll adjusts magnification, "
                            + "⌥ summons it, Esc dismisses",
                        identifier: "previewLoupeToggle"
                    )
                }
                if let magnifierEnabled {
                    pillToggle(
                        magnifierEnabled,
                        icon: "rectangle.bottomhalf.inset.filled",
                        activeIcon: "rectangle.bottomhalf.inset.filled",
                        help: "Magnifier bar — a magnified strip along the bottom edge",
                        identifier: "previewMagnifierToggle"
                    )
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .glassEffect(.regular, in: Capsule())
        }
    }

    private func pillButton(
        _ icon: String, help: String, action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .help(help)
        .accessibilityLabel(help)
    }

    private func pillToggle(
        _ binding: Binding<Bool>,
        icon: String, activeIcon: String, help: String, identifier: String
    ) -> some View {
        Button {
            binding.wrappedValue.toggle()
        } label: {
            Image(systemName: binding.wrappedValue ? activeIcon : icon)
                .foregroundStyle(binding.wrappedValue ? Color.accentColor : Color.secondary)
        }
        .buttonStyle(.plain)
        .help(help)
        .accessibilityLabel(help)
        .accessibilityIdentifier(identifier)
    }
}
#endif
