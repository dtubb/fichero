import SwiftUI

/// Sheet wrapper for Providers management (opened from menu)
struct ProvidersSettingsSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var appState: AppState

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Providers")
                    .font(.headline)
                Spacer()
                Button("Done") { dismiss() }
                    .keyboardShortcut(.defaultAction)
            }
            .padding()

            Divider()

            ProvidersView()
                .environmentObject(appState)
                .environmentObject(appState.providerService)
                .environmentObject(appState.modelService)
        }
        // Mac-only fixed size; iPhone/iPad sheets size to the screen (#2802).
        #if os(macOS)
        .frame(width: 700, height: 500)
        #endif
    }
}

// MARK: - Preview

#Preview {
    let appState = AppState()

    ProvidersSettingsSheet()
        .environmentObject(appState)
}
