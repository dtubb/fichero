import SwiftUI

// Prepare Images' four operations, each with its own picture (`wide.picture.one-per-operation`, #5668): split, straighten, crop,
// clarity. Each draws one frame from `progress`, 0 to 1, like the stage pictures; the stage's own picture plays the four in turn.

/// What one operation's picture has done at a progress: pure, so a frame at 0, 0.5 and 1 is tested without a view.
struct OperationFrame: Equatable {
    /// Split: the gap between the halves, as a share of the page's width.
    var gutterGap = 0.0
    /// Straighten: the page's tilt in degrees; its lines settle with it.
    var tilt = 0.0
    /// Crop: how much of the dashed box is drawn (0 to 1) and how far the table falls away.
    var boxDrawn = 0.0
    var tableFaded = 0.0
    /// Clarity: how dark the ink has become and how far the light sweep has gone.
    var ink = 0.0
    var sweep = 0.0

    static let operations = ["split", "straighten", "crop", "clarity"]

    static func at(_ progress: Double, operation: String) -> OperationFrame {
        var frame = OperationFrame()
        switch operation {
        case "split": frame.gutterGap = 0.08 * StageShowcasePlayback.phase(progress, from: 0.1, to: 0.8)
        case "straighten": frame.tilt = -7 * (1 - StageShowcasePlayback.phase(progress, from: 0, to: 0.7))
        case "crop":
            frame.boxDrawn = StageShowcasePlayback.phase(progress, from: 0, to: 0.6)
            frame.tableFaded = StageShowcasePlayback.phase(progress, from: 0.5, to: 1)
        default:
            frame.sweep = StageShowcasePlayback.phase(progress, from: 0, to: 1)
            frame.ink = StageShowcasePlayback.phase(progress, from: 0.2, to: 0.9)
        }
        return frame
    }

    /// What each picture shows, for VoiceOver.
    static let descriptions = [
        "split": "A page with two pages on it parts at the gutter into two pages.",
        "straighten": "A tilted page turns upright and its lines settle.",
        "crop": "A dashed box draws around the paper and the table falls away.",
        "clarity": "The page brightens and its ink darkens under a sweep of light."
    ]

    /// The stage's own picture plays the four in turn: which operation, and its own 0 to 1, at a stage progress.
    static func turn(at progress: Double) -> (operation: String, progress: Double) {
        let count = Double(operations.count)
        let index = min(operations.count - 1, Int(max(0, progress) * count))
        return (operations[index], min(1, max(0, progress * count - Double(index))))
    }
}

/// One operation's picture over the page.
struct PrepareOperationPicture: View {
    let operation: String
    let showcase: StageShowcase
    let progress: Double

    var body: some View {
        let frame = OperationFrame.at(progress, operation: operation)
        GeometryReader { proxy in
            switch operation {
            case "split":
                HStack(spacing: proxy.size.width * frame.gutterGap) {
                    half(leading: true, in: proxy.size)
                    half(leading: false, in: proxy.size)
                }
                .frame(maxWidth: .infinity)
            case "straighten":
                StagePageLayer(showcase: showcase) { _ in EmptyView() }
                    .rotationEffect(.degrees(frame.tilt))
            case "crop":
                StagePageLayer(showcase: showcase) { _ in
                    Rectangle().trim(from: 0, to: frame.boxDrawn)
                        .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 2, dash: [6, 4]))
                        .padding(proxy.size.width * 0.12)
                    Rectangle().fill(.background).opacity(0.6 * frame.tableFaded)
                        .frame(width: proxy.size.width, height: proxy.size.height * 0.12).frame(maxHeight: .infinity, alignment: .bottom)
                }
            default:
                StagePageLayer(showcase: showcase) { _ in EmptyView() }
                    .brightness(0.12 * frame.sweep).contrast(0.8 + 0.3 * frame.ink)
                    .scanSweep(progress: frame.sweep, height: proxy.size.height)
            }
        }
        .accessibilityLabel(OperationFrame.descriptions[operation] ?? "")
    }

    /// One half of the page, the picture clipped to its left or right side.
    private func half(leading: Bool, in size: CGSize) -> some View {
        StagePageLayer(showcase: showcase) { _ in EmptyView() }
            .frame(width: size.width, height: size.height)
            .frame(width: size.width / 2, height: size.height, alignment: leading ? .leading : .trailing)
            .clipped()
    }
}

/// The stage's picture with the wide Set Up: the four operations played in turn.
struct PrepareOperationsPicture: View {
    let showcase: StageShowcase
    let progress: Double

    var body: some View {
        let turn = OperationFrame.turn(at: progress)
        PrepareOperationPicture(operation: turn.operation, showcase: showcase, progress: turn.progress)
    }
}

#Preview("Prepare Images operations") {
    if let showcase = StageShowcaseSource.showcase(for: nil) {
        PrepareOperationsPicture(showcase: showcase, progress: 0.3).frame(width: 320, height: 220).padding()
    }
}

#Preview("Split") { operationPreview("split") }
#Preview("Straighten") { operationPreview("straighten") }
#Preview("Crop") { operationPreview("crop") }
#Preview("Clarity") { operationPreview("clarity") }

/// One operation's picture mid-play, for its `#Preview`.
@MainActor @ViewBuilder
private func operationPreview(_ operation: String) -> some View {
    if let showcase = StageShowcaseSource.showcase(for: nil) {
        PrepareOperationPicture(operation: operation, showcase: showcase, progress: 0.5).frame(width: 320, height: 220).padding()
    }
}
