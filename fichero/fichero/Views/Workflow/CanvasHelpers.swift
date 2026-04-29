import SwiftUI

// MARK: - Grid Pattern

/// Background grid pattern for the workflow canvas
struct GridPattern: Shape {
    let spacing: CGFloat

    init(spacing: CGFloat = 20) {
        self.spacing = spacing
    }

    func path(in rect: CGRect) -> Path {
        var path = Path()

        var gridX: CGFloat = 0
        while gridX < rect.width {
            path.move(to: CGPoint(x: gridX, y: 0))
            path.addLine(to: CGPoint(x: gridX, y: rect.height))
            gridX += spacing
        }

        var gridY: CGFloat = 0
        while gridY < rect.height {
            path.move(to: CGPoint(x: 0, y: gridY))
            path.addLine(to: CGPoint(x: rect.width, y: gridY))
            gridY += spacing
        }

        return path
    }
}

// MARK: - Preference Keys

/// Preference key for tracking the canvas frame in global coordinates
struct CanvasFramePreferenceKey: PreferenceKey {
    static let defaultValue: CGRect = .zero

    static func reduce(value: inout CGRect, nextValue: () -> CGRect) {
        value = nextValue()
    }
}

// MARK: - Preview

#Preview("Grid Pattern") {
    GridPattern()
        .stroke(Color.gray.opacity(0.3), lineWidth: 0.5)
        .frame(width: 400, height: 300)
        .background(Color(.textBackgroundColor))
}
