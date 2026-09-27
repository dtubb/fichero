import SwiftUI

//  Extracted for file_length (#5113) with that issue's checklist: path asserted free, cut
//  above the declaration's attributes and doc comment, no file-scope conditional-compilation
//  blocks and no file-scope `private` declarations to strand, imports copied verbatim.

/// ONE lozenge for every part of the sentence (Daniel, 2026-09-01: "render
/// each part — selection, model, step — as a lozenge with the same text
/// style"). The three tokens used to carry three different paddings, two
/// fonts and an inconsistent border; only the TINT is meant to differ, since
/// the tint is what carries a step's outcome.
struct ChainTokenLozenge: ViewModifier {
    let tint: Color

    func body(content: Content) -> some View {
        content
            .font(WorkflowBar.chainTokenFont)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(tint, in: Capsule())
            .overlay(Capsule().strokeBorder(.quaternary, lineWidth: 1))
    }
}

extension View {
    func chainTokenLozenge(tint: Color) -> some View {
        modifier(ChainTokenLozenge(tint: tint))
    }
}

/// Icon-then-text on one baseline, tight enough for a 10pt lozenge —
/// `.titleAndIcon` leaves a gap sized for body text, which pushed the
/// sentence's tokens apart.
struct ChainTokenLabelStyle: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 3) {
            configuration.icon
            configuration.title
        }
    }
}

extension WorkflowBar {
    /// The sentence's one type style, worn by every token.
    static let chainTokenFont = Font.system(size: 10, weight: .medium)
    /// The plain words between tokens — same size, unemphasised, so the
    /// lozenges are what the eye lands on.
    static let chainConnectiveFont = Font.system(size: 10)
}

/// A minimal flow layout: rows wrap, the container grows (Daniel,
/// 2026-08-29: "if it's multiple rows, make the rows expand so we can
/// see"). Just enough Layout for the sentence — leading-aligned, fixed
/// spacing, no fancy distribution.
struct ChainFlowLayout: Layout {
    var spacing: CGFloat = 5
    var rowSpacing: CGFloat = 6

    func sizeThatFits(
        proposal: ProposedViewSize, subviews: Subviews, cache: inout ()
    ) -> CGSize {
        let width = proposal.width ?? .infinity
        var cursorX: CGFloat = 0, cursorY: CGFloat = 0, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if cursorX > 0, cursorX + size.width > width {
                cursorX = 0
                cursorY += rowHeight + rowSpacing
                rowHeight = 0
            }
            cursorX += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: proposal.width ?? cursorX, height: cursorY + rowHeight)
    }

    func placeSubviews(
        in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews,
        cache: inout ()
    ) {
        var cursorX = bounds.minX, cursorY = bounds.minY, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if cursorX > bounds.minX, cursorX + size.width > bounds.maxX {
                cursorX = bounds.minX
                cursorY += rowHeight + rowSpacing
                rowHeight = 0
            }
            subview.place(
                at: CGPoint(x: cursorX, y: cursorY),
                anchor: .topLeading,
                proposal: .unspecified
            )
            cursorX += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
