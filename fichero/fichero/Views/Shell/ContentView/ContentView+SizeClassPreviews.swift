import SwiftUI

// Size-class variants for the adaptive shell (#3019). The horizontalSizeClass
// environment override is what the routing policies read
// (shouldUseCompactNavigationFlow / CompactShellPolicy / shouldUseSplittablePane
// / InspectorPlacement.adaptiveDefault), so these render the two shells the
// ShellRoutingMatrixTests assert: regular = split + docked inspector, compact =
// stack navigation + sheet inspector.

#Preview("Shell — Regular (Mac/iPad)") {
    ContentView()
        .environment(ViewSettings())
        .environment(AppState())
        .environment(ErrorService.shared)
        .environment(FeatureManager.shared)
        .environment(\.horizontalSizeClass, .regular)
        .frame(width: 1200, height: 700)
}

#Preview("Shell — Compact (iPhone)") {
    ContentView()
        .environment(ViewSettings())
        .environment(AppState())
        .environment(ErrorService.shared)
        .environment(FeatureManager.shared)
        .environment(\.horizontalSizeClass, .compact)
        .frame(width: 390, height: 780)
}
