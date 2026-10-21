import SwiftUI

extension DocumentInspectorInfoTab {
    /// The page's read is not trusted: says so and why, in the flagged style (orange triangle), and nothing when it is.
    @ViewBuilder
    var readFlagSection: some View {
        if let flag = document.readFlag {
            Label(flag.note, systemImage: "exclamationmark.triangle")
                .font(.callout)
                .foregroundStyle(.orange)
                .textSelection(.enabled)
                .padding(.horizontal, 12)
                .accessibilityIdentifier("inspector.info.readFlag")
        }
    }
}
