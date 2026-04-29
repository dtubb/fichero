import FicheroAPIClient
import SwiftUI

// MARK: - Claim Node

struct ClaimNode: View {
    let claim: Components.Schemas.KnowledgeClaim
    let isSelected: Bool
    let isFocused: Bool

    var body: some View {
        VStack(spacing: 4) {
            ZStack {
                Circle()
                    .fill(backgroundColor)
                    .frame(width: nodeSize, height: nodeSize)

                Circle()
                    .stroke(borderColor, lineWidth: isSelected ? 3 : (isFocused ? 2 : 1))
                    .frame(width: nodeSize, height: nodeSize)

                Image(systemName: iconForClaimType)
                    .font(.system(size: nodeSize * 0.4))
                    .foregroundStyle(iconColor)
            }

            Text(claim.text)
                .font(.caption2)
                .lineLimit(2)
                .frame(width: 80)
                .multilineTextAlignment(.center)
        }
    }

    private var nodeSize: CGFloat { isSelected ? 36 : 28 }

    private var backgroundColor: Color {
        if isSelected {
            return Color.accentColor.opacity(0.2)
        } else if isFocused {
            return Color.accentColor.opacity(0.1)
        }
        return Color(.controlBackgroundColor)
    }

    private var borderColor: Color {
        if isSelected {
            return .accentColor
        } else if isFocused {
            return .accentColor.opacity(0.6)
        }
        return .gray.opacity(0.4)
    }

    private var iconForClaimType: String {
        guard let type = claim.claimType else { return "text.alignleft" }
        switch type {
        case .fact: return "checkmark.circle"
        case .analysis: return "chart.bar"
        case .interpretation: return "text.quote"
        case .argument: return "text.badge.checkmark"
        case .historiography: return "clock"
        case .theory: return "lightbulb"
        }
    }

    private var iconColor: Color {
        guard let status = claim.epistemicStatus else { return .secondary }
        switch status {
        case .confirmed: return .green
        case .rejected: return .red
        case .tentative: return .orange
        }
    }
}
