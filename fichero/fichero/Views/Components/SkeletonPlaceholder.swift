import SwiftUI

/// ★ EVERY FRAME PERFECT (#3616): a stable, correctly-sized placeholder shown
/// while content loads, instead of a bare spinner or a blank frame. It fills the
/// space the real content will occupy (the caller reserves the size), so the
/// image/thumbnail cross-fades in with no relayout or popping.
///
/// A subtle surface-color rectangle with a gentle breathing highlight — enough
/// to read as "loading" without a spinner. Respects Reduce Motion (static fill).
/// Cross-platform via the shared `platformColor` shim.
struct SkeletonPlaceholder: View {
    /// Matches the corner radius of the container it fills (e.g. a thumbnail tile).
    var cornerRadius: CGFloat = 0

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulse = false

    var body: some View {
        RoundedRectangle(cornerRadius: cornerRadius)
            .fill(Color(platformColor: .windowBackgroundColor))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .fill(Color.primary.opacity(pulse ? 0.08 : 0.03))
            )
            .onAppear {
                guard !reduceMotion else { return }
                withAnimation(.easeInOut(duration: 1.0).repeatForever(autoreverses: true)) {
                    pulse = true
                }
            }
            // Decorative — the surrounding surface already conveys "loading" to
            // assistive tech via its own state; a shimmer rect adds no meaning.
            .accessibilityHidden(true)
    }
}

#Preview("Skeleton — tile") {
    SkeletonPlaceholder(cornerRadius: 6)
        .frame(width: 100, height: 133)
        .padding()
}
