import SwiftUI

enum AdaptiveAppleShellRoute: Equatable, Sendable {
    case split
    case stack
}

extension AdaptiveAppleShellRoute {
    static func resolve(horizontalSizeClass: UserInterfaceSizeClass?) -> AdaptiveAppleShellRoute {
        ContentView.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass)
            ? .stack
            : .split
    }
}

/// Minimal Apple shell router for the iOS / iPadOS / visionOS entry path.
///
/// Compact width gets a stack so the app stays one-surface-at-a-time.
/// Regular width keeps the existing split-driven shell untouched.
struct AdaptiveAppleShellHost<Content: View>: View {
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    private let content: () -> Content

    init(@ViewBuilder content: @escaping () -> Content) {
        self.content = content
    }

    @ViewBuilder
    var body: some View {
        switch AdaptiveAppleShellRoute.resolve(horizontalSizeClass: horizontalSizeClass) {
        case .split:
            content()
        case .stack:
            NavigationStack {
                content()
            }
        }
    }
}
