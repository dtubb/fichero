import SwiftUI

/// Both texts of a refused note save, side by side, with the same two choices as the dialog (#5348).
struct NoteStaleCompareView: View {
    let comparison: NoteStaleComparison
    let onChoose: (_ keepMine: Bool) -> Void

    var body: some View {
        VStack(spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                column("Mine", comparison.mine)
                column("Theirs", comparison.theirs)
            }
            HStack {
                Spacer()
                Button("Take theirs") { onChoose(false) }
                Button("Keep mine") { onChoose(true) }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding()
        .frame(minWidth: 480, minHeight: 280)
    }

    private func column(_ title: String, _ text: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.headline)
            ScrollView {
                Text(text)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
        }
        .frame(maxWidth: .infinity)
    }
}

#Preview {
    NoteStaleCompareView(
        comparison: NoteStaleComparison(mine: "Letter to Ann, draft two.", theirs: "Letter to Ann, sent Tuesday."),
        onChoose: { _ in }
    )
}
