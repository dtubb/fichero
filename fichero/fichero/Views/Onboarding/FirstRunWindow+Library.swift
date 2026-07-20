import SwiftUI

struct LibrarySetupActionsRow: View {
    let primaryTitle: String
    let primaryIcon: String
    let primaryAction: () -> Void
    let selectedLabel: String?

    var body: some View {
        HStack(spacing: 10) {
            Button(action: primaryAction) {
                Label(primaryTitle, systemImage: primaryIcon)
            }

            if let selectedLabel {
                Label(selectedLabel, systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                    .lineLimit(1)
            }
        }
    }
}
