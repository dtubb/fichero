import SwiftUI

/// Toolbar with zoom controls and magnifier toggles for image viewer
struct ImageZoomToolbar: View {
    @Binding var scale: CGFloat
    @Binding var magnifierEnabled: Bool
    @Binding var loupeEnabled: Bool
    @Binding var loupeLocked: Bool
    @Binding var loupeMagnification: Double
    @Binding var loupeSize: Double

    let zoomIn: () -> Void
    let zoomOut: () -> Void
    let fitToWindow: () -> Void
    let actualSize: () -> Void

    var body: some View {
        // MiniToolbar keeps the image preview header at the standard 44pt so
        // it lines up with the PDF preview, list mode rail, knowledge surface,
        // and inspector tab strip. (#1228)
        MiniToolbar {
            Button(action: zoomOut) {
                Image(systemName: "minus.magnifyingglass")
            }
            .buttonStyle(.plain)
            .help("Zoom Out")

            Text("\(Int(scale * 100))%")
                .font(.caption)
                .monospacedDigit()
                .frame(width: 50)

            Button(action: zoomIn) {
                Image(systemName: "plus.magnifyingglass")
            }
            .buttonStyle(.plain)
            .help("Zoom In")

            Divider()
                .frame(height: 16)

            Button(action: fitToWindow) {
                Image(systemName: "arrow.up.left.and.arrow.down.right")
            }
            .buttonStyle(.plain)
            .help("Fit to Window")

            Button(action: actualSize) {
                Image(systemName: "1.square")
            }
            .buttonStyle(.plain)
            .help("Actual Size (100%)")

            Divider()
                .frame(height: 16)

            // Magnifier panel toggle
            Button {
                magnifierEnabled.toggle()
            } label: {
                Image(systemName: "rectangle.bottomhalf.inset.filled")
            }
            .buttonStyle(.plain)
            .foregroundColor(magnifierEnabled ? .accentColor : .primary)
            .help("Magnifier Panel")

            // Loupe toggle with zoom controls
            HStack(spacing: 4) {
                Button {
                    loupeEnabled.toggle()
                } label: {
                    Image(systemName: loupeEnabled ? "magnifyingglass.circle.fill" : "magnifyingglass.circle")
                }
                .buttonStyle(.plain)
                .foregroundColor(loupeEnabled ? .accentColor : .primary)
                .help("Loupe (crosshairs follow cursor, Option+move to reposition, lock to freeze)")

                if loupeEnabled {
                    Button {
                        loupeLocked.toggle()
                    } label: {
                        Image(systemName: loupeLocked ? "lock.fill" : "lock.open")
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(loupeLocked ? .accentColor : .secondary)
                    .help(loupeLocked ? "Unlock loupe (crosshairs follow cursor)" : "Lock loupe (freeze view)")

                    Text(String(format: "%.1fx", CGFloat(loupeMagnification)))
                        .font(.caption2)
                        .monospacedDigit()
                        .foregroundColor(.secondary)
                        .frame(width: 32)

                    Text("\(Int(loupeSize))px")
                        .font(.caption2)
                        .monospacedDigit()
                        .foregroundColor(.secondary.opacity(0.7))
                }
            }

            Spacer()
        }
    }
}
