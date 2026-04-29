import SwiftUI

/// View shown when backend is not running
struct BackendConnectionView: View {
    @ObservedObject var appState: AppState
    @EnvironmentObject var backendService: EmbeddedBackendService

    var body: some View {
        VStack(spacing: 24) {
            // Icon
            Image(systemName: "server.rack")
                .font(.system(size: 72))
                .foregroundColor(.secondary)

            // Title
            Text("Connecting to Backend")
                .font(.title)
                .fontWeight(.semibold)

            // Status message
            if backendService.status == .starting {
                // Backend is starting - show progress
                VStack(spacing: 16) {
                    ProgressView()
                        .scaleEffect(1.2)

                    Text("Starting backend server...")
                        .font(.headline)
                        .foregroundColor(.primary)

                    Text("This may take 30-40 seconds on first launch")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            } else if appState.isCheckingBackend {
                ProgressView()
                    .scaleEffect(0.8)
                Text("Checking backend connection...")
                    .foregroundColor(.secondary)
            } else {
                // Error state
                VStack(spacing: 12) {
                    Text("Backend Not Running")
                        .font(.headline)
                        .foregroundColor(.red)

                    if let error = appState.backendError {
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                    }
                }
            }

            // Retry button
            Button {
                Task {
                    await appState.checkBackendHealth()
                }
            } label: {
                Label("Retry Connection", systemImage: "arrow.clockwise")
            }
            .buttonStyle(.borderedProminent)
            .disabled(appState.isCheckingBackend)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(nsColor: .windowBackgroundColor))
        .task {
            // Auto-retry every 5 seconds
            while !appState.isBackendRunning {
                try? await Task.sleep(for: .seconds(5))
                if !Task.isCancelled {
                    await appState.checkBackendHealth()
                }
            }
        }
    }
}

#Preview {
    BackendConnectionView(appState: AppState())
        .frame(width: 600, height: 400)
}
