import SwiftUI

/// The chain ROW — the frame the sentence lives in, and the run controls
/// pinned beside it.
///
/// Split out of `WorkflowBar` (2026-08-31) when the row learned to wrap: the
/// height measurement, the row cap and the controls cluster together outgrew
/// what the main type could carry under SwiftLint's file-length rule. The cut
/// is the one the UI makes anyway — `WorkflowBar+ChainRail` draws the
/// sentence, this file decides how much room it gets.
extension WorkflowBar {

    /// One row of the wrapped sentence — the tallest token in it (a capsule
    /// chip) plus breathing room.
    static let chainRailRowHeight: CGFloat = 22
    /// How tall the sentence may grow before it starts scrolling instead
    /// (Daniel, 2026-08-31: "taking multiple lines if it needs to, or
    /// scrolling"). Three rows is the point past which the bar would be
    /// eating the content it acts on.
    static let chainRailMaxRows: Int = 3
    static let chainRailRowSpacing: CGFloat = 6
    private static var chainRailMaxHeight: CGFloat {
        CGFloat(chainRailMaxRows) * chainRailRowHeight
            + CGFloat(chainRailMaxRows - 1) * chainRailRowSpacing
    }

    /// The chain: the sentence WRAPS across as many rows as it needs, up to
    /// three, and scrolls vertically past that (Daniel, 2026-08-31).
    ///
    /// The old shape could not wrap however wide `ChainFlowLayout` was willing
    /// to be: a horizontal `ScrollView` with `.fixedSize(horizontal: true)`
    /// proposes UNBOUNDED width, so the flow layout always fitted everything on
    /// one row and the row's fixed 34pt frame then clipped it. Now the rail is
    /// proposed the real available width, measures the height it wants, and the
    /// row takes that height — capped.
    var chainRow: some View {
        HStack(alignment: .top, spacing: 8) {
            ScrollView(.vertical) {
                chainRail
                    .padding(.horizontal, 10)
                    .background {
                        // Measured rather than guessed: the number of rows
                        // depends on chip labels, the window width and whether
                        // the context token is present.
                        Color.clear.onGeometryChange(for: CGFloat.self) {
                            $0.size.height
                        } action: { chainRailHeight = $0 }
                    }
            }
            .frame(
                height: min(
                    max(chainRailHeight, Self.chainRailRowHeight),
                    Self.chainRailMaxHeight
                )
            )
            .frame(maxWidth: .infinity, alignment: .leading)
            chainControls
        }
        .padding(.vertical, 6)
    }

    /// Run, clear, compare, cost and the step count — everything that must stay
    /// put no matter how many rows the sentence grows to.
    private var chainControls: some View {
        HStack(spacing: 6) {
            // Run and Clear live HERE, outside the scrolling rail (review
            // fix, 2026-08-29): inside it, an eight-step chain pushed the
            // play button off-screen — the one control that must never
            // scroll away is the one that starts the run.
            if isRunning {
                ProgressView()
                    .controlSize(.small)
                    .help("Chain is running")
                    .accessibilityLabel("Chain is running")
            } else {
                Button(action: onRunChain) {
                    Image(systemName: "play.circle.fill")
                        .font(.title3)
                        .foregroundStyle(target == .nothing
                                         ? Color.secondary : Color.accentColor)
                }
                .buttonStyle(.plain)
                // Pressing play with nothing selected used to silently do
                // nothing — the guard in runStagedChain returned without a
                // word (review, 2026-08-29). Disabled WITH the reason on
                // hover is the honest version.
                .disabled(target == .nothing)
                .help(target == .nothing
                      ? "Select a document or folder to run this chain on"
                      : "Run \(staged.count) step(s) in order on the selection")
                .accessibilityLabel("Run the chain")

                Button { staged.removeAll() } label: {
                    Image(systemName: "trash")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .help("Clear the chain")
                .accessibilityLabel("Clear the chain")

                // "Compare models…" — the same sentence, once per model
                // (Daniel, 2026-08-30). Sits beside ▶ because it IS a
                // run control, just one that fans out.
                compareItem
            }
            if let costCeiling {
                // A CEILING, said as one: "≤" is the difference between a
                // promise that can be kept and a guess.
                Text("est. ≤ \(costCeiling, format: .currency(code: "USD"))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
                    .help(
                        "Estimated upper bound for this chain over "
                        + "\(staged.count) step(s), priced from the live "
                        + "model registry. Steps whose model cannot be "
                        + "priced are not counted."
                    )
            }
            Text(staged.count == 1 ? "1 step" : "\(staged.count) steps")
                .font(.caption2)
                .foregroundStyle(.secondary)
            chainOptionsMenu
        }
        .fixedSize()
    }
}
