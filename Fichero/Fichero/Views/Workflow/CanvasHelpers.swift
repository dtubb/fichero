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

        var x: CGFloat = 0
        while x < rect.width {
            path.move(to: CGPoint(x: x, y: 0))
            path.addLine(to: CGPoint(x: x, y: rect.height))
            x += spacing
        }

        var y: CGFloat = 0
        while y < rect.height {
            path.move(to: CGPoint(x: 0, y: y))
            path.addLine(to: CGPoint(x: rect.width, y: y))
            y += spacing
        }

        return path
    }
}

// MARK: - Preference Keys

/// Preference key for tracking the canvas frame in global coordinates
struct CanvasFramePreferenceKey: PreferenceKey {
    static var defaultValue: CGRect = .zero

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
