import SwiftUI

/// The rubber band, drawn as Finder draws it (#4601, `library.selection.one-rubber-band`): a neutral translucent grey
/// fill with a thin light border, never the accent (an owner's accent may be yellow, and a band is not a selection
/// yet). ONE look for every band: the 2D and 3D boards, the icon grid, the Preview's region band and the image
/// editor. Semantic colours only, so it follows Dark Mode and Increase Contrast.
struct RubberBand: View {
    nonisolated static let fill: Color = .secondary.opacity(0.12)
    nonisolated static let border: Color = .secondary.opacity(0.5)
    nonisolated static let lineWidth: CGFloat = 1

    var body: some View {
        Rectangle()
            .fill(Self.fill)
            .overlay(Rectangle().strokeBorder(Self.border, lineWidth: Self.lineWidth))
            .allowsHitTesting(false)
    }
}

#Preview("Rubber band over cards") {
    ZStack(alignment: .topLeading) {
        HStack(spacing: 12) {
            ForEach(0..<3, id: \.self) { _ in
                RoundedRectangle(cornerRadius: 6).fill(.background).shadow(radius: 1).frame(width: 70, height: 90)
            }
        }
        .padding(20)
        RubberBand().frame(width: 150, height: 80).offset(x: 40, y: 40)
    }
    .frame(width: 320, height: 160)
    .background(.windowBackground)
}
