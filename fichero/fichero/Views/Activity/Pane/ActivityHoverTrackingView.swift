import SwiftUI

/// Holds one row's hover in its own state, so the pointer entering or leaving a row redraws that cell and not the table
/// (`activity.pane.row-controls`, #6588). The content is given whether the pointer is over it.
struct ActivityHoverTrackingView<Content: View>: View {
    @State private var isHovered = false
    @ViewBuilder let content: (Bool) -> Content

    var body: some View {
        content(isHovered).onHover { isHovered = $0 }
    }
}

#Preview("Hover shows the controls") {
    ActivityHoverTrackingView { hovered in
        HStack {
            Text("Reading pages")
            Spacer()
            if hovered { Image(systemName: "pause.fill") }
        }
        .padding()
        .frame(width: 280)
    }
}
