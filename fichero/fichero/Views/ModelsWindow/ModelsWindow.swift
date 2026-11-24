import SwiftUI

/// The Models and Cluster window (`models.window.is-activitys-shape`, #6588): one `Window` scene, opened from the Window menu.
struct ModelsWindow: View {
    var body: some View {
        ModelsPaneView()
            .navigationTitle(ModelsWindowModel.windowTitle)
            .frame(minWidth: 900, minHeight: 480)
            .accessibilityIdentifier("models.window")
    }
}

#Preview("The Models and Cluster window") {
    ModelsWindow()
        .environment(LibraryManager.shared)
        .frame(width: 1100, height: 600)
}
