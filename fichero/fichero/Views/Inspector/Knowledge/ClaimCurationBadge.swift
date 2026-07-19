import FicheroAPIClient
import SwiftUI

// MARK: - ClaimCurationBadge

struct ClaimCurationBadge: View {
    let state: Components.Schemas.ClaimCurationState

    var body: some View {
        Text(label)
            .font(.caption2)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.16), in: Capsule())
            .foregroundStyle(color)
    }

    private var label: String {
        switch state {
        case .curated:
            return "Approved"
        case .rejected:
            return "Rejected"
        case .shortlisted:
            return "Shortlisted"
        case .unreviewed:
            return "Unreviewed"
        }
    }

    private var color: Color {
        switch state {
        case .curated:
            return .green
        case .rejected:
            return .red
        case .shortlisted:
            return .orange
        case .unreviewed:
            return .gray
        }
    }
}
