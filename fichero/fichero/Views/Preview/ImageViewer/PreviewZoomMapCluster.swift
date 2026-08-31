#if os(macOS)
import SwiftUI

// MARK: - The magnification family cluster (Daniel, 2026-08-29)
//
// "Where am I and how close am I are one concern." One floating cluster,
// TOP-RIGHT of the canvas, stacked (Daniel, 2026-08-31 — the pill moved
// ABOVE the map):
//   • the zoom pill on top (− % + · fit · 1:1 · loupe · bar · map toggle),
//   • the mini-map under it, in a glass lozenge, when shown.
// The pill's chevron hides the map and collapses the cluster to the pill.
// The whole cluster answers `imagePreview.zoomControlsVisible`, which a
// pane-header button owns; this view only READS it.

struct PreviewZoomMapCluster<Map: View>: View {
    @AppStorage("imagePreview.zoomControlsVisible") private var controlsVisible = true
    @AppStorage("imagePreview.miniMapVisible") private var miniMapVisible = true

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
        if controlsVisible {
            VStack(alignment: .trailing, spacing: 8) {
                zoomPill
                // The map hangs UNDER the pill in its own glass lozenge — the
                // Tahoe/Golden-Gate idiom (Daniel, 2026-08-30: "golden gate and
                // tahoe style"), never a bare rectangle. The map paints its own
                // `.ultraThinMaterial`, so the page reads through the letterbox.
                if miniMapVisible {
                    map()
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 10))
                }
            }
            .padding(8)
        }
    }

    /// ONE line (Daniel, 2026-08-30: "zoom, and all that on one line, not
    /// two"): − % + · fit · 1:1 · loupe · magnifier bar · map chevron, one capsule.
    private var zoomPill: some View {
        HStack(spacing: 6) {
            pillButton("minus.magnifyingglass", help: "Zoom Out (⌘− or −)", action: zoomOut)
            Text("\(scalePercent)%")
                .font(.caption)
                .monospacedDigit()
                .foregroundStyle(.secondary)
                .frame(minWidth: 40)
            pillButton("plus.magnifyingglass", help: "Zoom In (⌘+ or +)", action: zoomIn)
            Divider().frame(height: 14)
            pillButton(
                "arrow.up.left.and.arrow.down.right",
                help: "Zoom to Fit (⌘9 or 9)",
                action: fitToWindow
            )
            pillButton("1.square", help: "Actual Size — 100% (⌘0 or 0)", action: actualSize)
            if loupeEnabled != nil || magnifierEnabled != nil {
                Divider().frame(height: 14)
            }
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
            Divider().frame(height: 14)
            // The disclosure (Daniel, 2026-08-31): hides the map and leaves
            // the pill alone on the canvas. Persisted, no shortcut of its own.
            pillButton(
                miniMapVisible ? "chevron.up" : "chevron.down",
                help: miniMapVisible ? "Hide Navigator Map" : "Show Navigator Map",
                action: { miniMapVisible.toggle() }
            )
            .accessibilityIdentifier("previewMiniMapToggle")
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .glassEffect(.regular, in: Capsule())
        .accessibilityIdentifier("previewZoomPill")
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
