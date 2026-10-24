import Foundation

/// Applies the LAST of a burst of window-width readings once the width has been still for `delay` (#6009). Dragging the
/// Inspector's edge changes the measured width every frame; writing layout state on each reading made the app hang in a
/// feedback loop ("onChange action tried to update multiple times per frame"), so a drag now costs one write at its end.
@MainActor
final class WindowWidthSettle {
    private var task: Task<Void, Never>?

    func schedule(after delay: Duration = .milliseconds(150), _ apply: @escaping @MainActor () -> Void) {
        task?.cancel()
        task = Task {
            try? await Task.sleep(for: delay)
            guard !Task.isCancelled else { return }
            apply()
        }
    }

    /// A reading is worth acting on when it is a real width that moved by at least half a point.
    nonisolated static func isNewWidth(_ new: Double, since measured: Double) -> Bool {
        new > 0 && abs(measured - new) >= 0.5
    }
}
