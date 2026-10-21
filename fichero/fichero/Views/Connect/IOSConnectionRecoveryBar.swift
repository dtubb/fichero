#if os(iOS) || os(visionOS)
import SwiftUI

/// One plain line and two buttons at the top of whatever column is showing, while the connection is not working
/// (`m2p.ios.connect-failure-offers-recovery`): Reconnect (the one retry entry point) and Change Server… (the Connect to a Mac
/// sheet, which pairs with another Mac and reconnects). The only other place was a toolbar item of the content column.
struct IOSConnectionRecoveryBar: View {
    @Environment(AppState.self) private var appState
    let onRetry: @MainActor () async -> Void

    @State private var choosingServer = false
    @State private var reconnecting = false

    private var title: String {
        ConnectionPresentation.status(
            phase: appState.engine.phase,
            ownership: ConnectionPresentation.EngineOwnership.current(),
            accessError: appState.backendAccessError,
            authBroken: appState.authBroken,
            conflict: appState.engine.conflict
        ).title
    }

    var body: some View {
        VStack(spacing: 8) {
            Text(title)
                .font(.subheadline)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity)
            HStack(spacing: 12) {
                Button {
                    reconnecting = true
                    Task {
                        await onRetry()
                        reconnecting = false
                    }
                } label: {
                    Label("Reconnect", systemImage: "arrow.clockwise")
                }
                .disabled(reconnecting)
                .accessibilityIdentifier("connection.recovery.reconnect")
                Button {
                    choosingServer = true
                } label: {
                    Label("Change Server…", systemImage: "server.rack")
                }
                .accessibilityIdentifier("connection.recovery.change-server")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 16)
        .frame(maxWidth: .infinity)
        .background(.bar)
        .sheet(isPresented: $choosingServer) {
            NavigationStack {
                RemoteConnectionSetupView {
                    choosingServer = false
                    await onRetry()
                }
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Cancel") { choosingServer = false }
                    }
                }
            }
        }
    }
}

#Preview {
    IOSConnectionRecoveryBar(onRetry: {})
        .environment(AppState())
        .padding()
}
#endif
