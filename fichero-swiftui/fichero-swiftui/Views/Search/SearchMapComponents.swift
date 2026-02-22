import SwiftUI

// MARK: - Search Map Grid

/// Grid background for search map view
struct SearchMapGrid: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let spacing: CGFloat = 40

        // Vertical lines
        var xPos = spacing
        while xPos < rect.width {
            path.move(to: CGPoint(x: xPos, y: 0))
            path.addLine(to: CGPoint(x: xPos, y: rect.height))
            xPos += spacing
        }

        // Horizontal lines
        var yPos = spacing
        while yPos < rect.height {
            path.move(to: CGPoint(x: 0, y: yPos))
            path.addLine(to: CGPoint(x: rect.width, y: yPos))
            yPos += spacing
        }

        return path
    }
}

// MARK: - Search Result Card (for Map View)

/// Card view for displaying search results in map mode
struct SearchResultCard: View {
    let result: SearchResult
    let isSelected: Bool

    var body: some View {
        VStack(spacing: 8) {
            // Icon
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 28))
                .foregroundColor(.accentColor)
                .frame(width: 44, height: 44)
                .background(Color.accentColor.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 8))

            // Name
            if let name = result.metadata["name"]?.value as? String {
                Text(name)
                    .font(.caption)
                    .fontWeight(.medium)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
            } else {
                Text(result.documentId.prefix(12) + "...")
                    .font(.caption)
                    .lineLimit(1)
            }

            // Score badge
            Text(String(format: "%.0f%%", result.score * 100))
                .font(.caption2)
                .foregroundColor(.white)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(scoreColor(for: result.score))
                .clipShape(Capsule())
        }
        .frame(width: 140, height: 110)
        .padding(8)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isSelected ? Color.accentColor : Color(.separatorColor), lineWidth: isSelected ? 2 : 1)
        )
        .shadow(color: .black.opacity(0.1), radius: 2, x: 0, y: 1)
    }

    private func scoreColor(for score: Double) -> Color {
        if score >= 0.8 { return .green }
        if score >= 0.5 { return .orange }
        return .gray
    }
}
