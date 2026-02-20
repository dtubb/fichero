import SwiftUI

/// Grid background for chat map view
struct ChatMapGrid: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let spacing: CGFloat = 40
        
        var xPos = spacing
        while xPos < rect.width {
            path.move(to: CGPoint(x: xPos, y: 0))
            path.addLine(to: CGPoint(x: xPos, y: rect.height))
            xPos += spacing
        }
        
        var yPos = spacing
        while yPos < rect.height {
            path.move(to: CGPoint(x: 0, y: yPos))
            path.addLine(to: CGPoint(x: rect.width, y: yPos))
            yPos += spacing
        }
        
        return path
    }
}
