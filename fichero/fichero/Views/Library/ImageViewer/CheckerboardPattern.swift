import SwiftUI

struct CheckerboardPattern: View {
    var body: some View {
        GeometryReader { geometry in
            let size: CGFloat = 10
            let rows = Int(geometry.size.height / size) + 1
            let cols = Int(geometry.size.width / size) + 1

            Canvas { context, _ in
                for row in 0..<rows {
                    for col in 0..<cols where (row + col) % 2 == 0 {
                        let rect = CGRect(
                            x: CGFloat(col) * size,
                            y: CGFloat(row) * size,
                            width: size,
                            height: size
                        )
                        context.fill(Path(rect), with: .color(.gray.opacity(0.3)))
                    }
                }
            }
        }
    }
}
