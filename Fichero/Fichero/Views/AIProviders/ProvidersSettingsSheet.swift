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
        .frame(width: 700, height: 500)
    }
}
