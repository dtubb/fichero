import SwiftUI

// Zoom chrome for the reading pane's mini-toolbar: an expanded button cluster
// and a compact menu fallback (chosen via ViewThatFits). Split out of
// ReadingPaneView to keep the type body under the SwiftLint threshold.
extension ReadingPaneView {
    @ViewBuilder
    var zoomControls: some View {
        Button { webZoom = max(0.5, webZoom - 0.1) } label: {
            Image(systemName: "minus.magnifyingglass")
                .readerIconTarget()
        }
        .buttonStyle(.plain)
        .help("Zoom Out")
        .accessibilityLabel("Zoom out")
        .accessibilityValue("\(Int(webZoom * 100)) percent")

        Text("\(Int(webZoom * 100))%")
            .font(.caption)
            .monospacedDigit()
            .frame(width: 44)
            // Spoken as the zoom buttons' accessibilityValue; as its own element it
            // would just be a bare number with no context.
            .accessibilityHidden(true)

        Button { webZoom = min(3.0, webZoom + 0.1) } label: {
            Image(systemName: "plus.magnifyingglass")
                .readerIconTarget()
        }
        .buttonStyle(.plain)
        .help("Zoom In")
        .accessibilityLabel("Zoom in")
        .accessibilityValue("\(Int(webZoom * 100)) percent")

        Button { webZoom = 1.0 } label: {
            Image(systemName: "1.square")
                .readerIconTarget()
        }
        .buttonStyle(.plain)
        .help("Reset Zoom")
        .accessibilityLabel("Reset zoom to 100 percent")
    }

    @ViewBuilder
    var zoomMenu: some View {
        Menu {
            Button("Zoom Out") {
                webZoom = max(0.5, webZoom - 0.1)
            }
            Button("Zoom In") {
                webZoom = min(3.0, webZoom + 0.1)
            }
            Button("Reset Zoom") {
                webZoom = 1.0
            }
        } label: {
            Label("Zoom", systemImage: "magnifyingglass")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
    }
}
