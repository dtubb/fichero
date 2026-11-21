import SwiftUI

/// The thin line with a circle at its left end that a drop between rows of the segment list shows, as in the Finder's and
/// Mail's sidebars (`segment-editor.list-drag-reorder`).
struct OrderInsertionLine: View {
    var body: some View {
        HStack(spacing: 0) {
            Circle().stroke(Color.accentColor, lineWidth: 2).frame(width: 8, height: 8)
            Rectangle().fill(Color.accentColor).frame(height: 2)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

#if DEBUG
#Preview("Between two rows") {
    VStack(alignment: .leading, spacing: 4) {
        Text("line 1")
        Text("line 2").overlay(alignment: .top) { OrderInsertionLine().offset(y: -3) }
    }
    .padding()
    .frame(width: 240)
}
#endif
