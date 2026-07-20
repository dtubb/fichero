import SwiftUI

/// Edge being actively dragged from a port
struct DraggingWorkflowEdgeView: View {
    let startPoint: CGPoint
    let currentPoint: CGPoint

    var body: some View {
        Path { path in
            let controlDistance = abs(currentPoint.x - startPoint.x) * 0.5
            let control1 = CGPoint(x: startPoint.x + controlDistance, y: startPoint.y)
            let control2 = CGPoint(x: currentPoint.x - controlDistance, y: currentPoint.y)

            path.move(to: startPoint)
            path.addCurve(to: currentPoint, control1: control1, control2: control2)
        }
        .stroke(
            Color.accentColor,
            style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [5, 3])
        )
    }
}
