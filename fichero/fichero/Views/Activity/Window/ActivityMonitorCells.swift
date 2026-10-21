import SwiftUI

extension ActivityMonitorWindow {
    static func find(_ id: ActivityMonitorRow.ID, in rows: [ActivityMonitorRow]) -> ActivityMonitorRow? {
        for row in rows {
            if row.id == id { return row }
            if let found = find(id, in: row.children ?? []) { return found }
        }
        return nil
    }
}

/// The footer line under the window: a notice or a failure in words, with Dismiss when it can go.
struct ActivityFooterLine: View {
    let message: String
    let onDismiss: (() -> Void)?

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            Text(message)
                .font(.caption)
            Spacer(minLength: 8)
            if let onDismiss {
                Button("Dismiss", action: onDismiss)
                    .font(.caption)
                    .buttonStyle(.borderless)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.regularMaterial)
    }
}

#Preview("A footer notice") {
    ActivityFooterLine(message: "Could not reach the engine; showing the last list.", onDismiss: {})
}
