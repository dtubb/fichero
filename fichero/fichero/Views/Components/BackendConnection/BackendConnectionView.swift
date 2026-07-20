#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import FicheroAPIClient
import SwiftUI

/// View shown while the embedded engine is booting (or when it failed to start).
///
/// The engine takes ~25-40s to boot on first launch (heavy ML imports — see
/// engine#743 for the lazy-import refactor that will fix this). To make that
/// wait feel less dead, we cycle through a few honest messages that match
/// what the engine is actually doing, and use the app icon instead of a
/// generic SF symbol.
struct BackendConnectionView: View {
    @Bindable var appState: AppState
    /// The single retry entry point (#3108), supplied by the root gate. The
    /// button just calls this; the view never probes health, writes backend
    /// status, or re-implements `start()` — it is render-only.
    var onRetry: (@MainActor () async -> Void)?
    @Environment(EmbeddedBackendService.self) var backendService

    /// Index into `Self.startupMessages`, advanced by a timer while `.starting`.
    @State var messageIndex: Int = 0

    /// Animation phase for the connecting-dots between app + engine icons.
    @State private var dotPhase: Int = 0

    var usesExternalBackendConnection: Bool {
        #if os(iOS) || os(visionOS)
        true
        #else
        EngineConfig.requiresExternalBackendConnection
        #endif
    }

    /// Messages cycled while the session is `.starting` (`engine.isChecking`).
    ///
    /// Honest phrasing only: the engine doesn't load models, prepare the
    /// graph, or index the library at startup — it imports Python libraries
    /// and initializes its database. Aspirational copy ("loading language
    /// models", "indexing your library") is a lie; users notice. Each line
    /// describes what the engine is *actually* doing in that window.
    private static let startupMessages: [String] = [
        "Connecting to the engine…",
        "Loading runtime libraries…",
        "Opening the database…",
        "Almost ready…"
    ]

    var body: some View {
        VStack(spacing: 24) {
            // Two icons side-by-side — Fichero (app) on the left, Engine
            // (Python helper) on the right — with three dots animating
            // between them to visualize "the app is talking to the engine".
            // The dots cycle through three phases on a 0.4s timer; the
            // single "active" dot lights up while the others dim.
            HStack(spacing: 16) {
                Image(platformImage: ficheroIconImage)
                    .resizable()
                    .interpolation(.high)
                    .frame(width: 72, height: 72)

                HStack(spacing: 6) {
                    ForEach(0..<3, id: \.self) { dotIndex in
                        Circle()
                            .fill(dotPhase == dotIndex ? Color.accentColor : Color.secondary.opacity(0.3))
                            .frame(width: 8, height: 8)
                    }
                }
                .frame(width: 50)

                Image(platformImage: engineIconImage)
                    .resizable()
                    .interpolation(.high)
                    .frame(width: 72, height: 72)
            }

            Text(titleText)
                .font(.title)
                .fontWeight(.semibold)

            // Decide which state to show. `.stopped` is a transient state
            // at app-launch (we haven't called `start()` yet) — UI-wise it
            // belongs with `.starting`, not in the red-error branch. Only
            // `.failed` triggers the red error text and the Retry button.
            // This prevents the "engine not running" flash that happens in
            // the ~100ms gap between view-mount and `start()` being called.
            let isFailed = showsFailureState
            let isBootingOrChecking = !isFailed

            if isBootingOrChecking {
                VStack(spacing: 16) {
                    ProgressView()
                        .scaleEffect(1.2)

                    // Cycling status. The transition gives a soft fade so
                    // the message change isn't a jarring text-swap.
                    Text(Self.startupMessages[messageIndex])
                        .font(.headline)
                        .foregroundColor(.primary)
                        .id(messageIndex) // force re-render for transition
                        .transition(.opacity)

                    Text(secondaryStatusText)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            } else {
                VStack(spacing: 12) {
                    Text(failureTitle)
                        .font(.headline)
                        .foregroundColor(.red)
                        .accessibilityIdentifier("backend.connection.title")

                    if let error = failureDetail {
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                    }
                }
            }

            // Shown only after a failure phase — not during normal booting where
            // the user hasn't done anything wrong. Tapping it runs the single
            // retry entry point (#3108): macOS respawns the stuck engine, iOS
            // re-adopts its paired host. The button is absent while `.starting`,
            // so a retry can never SIGTERM a healthy cold-starting engine.
            if isFailed {
                HStack(spacing: 12) {
                    // A foreign holder of :8765 gets the in-window decision
                    // (#3111) — three-way when we know the PID, two-way under the
                    // App Sandbox where we cannot (#3749); every other failure
                    // gets the single retry entry point (#3108). Keyed on the
                    // PHASE, not the PID: a nil PID is still a real conflict, and
                    // testing the PID here would render an empty box.
                    if isPortConflict {
                        portConflictActions
                    } else {
                        if failureAccessError?.recovery == .resetPin {
                            resetCertificateButton
                        } else {
                            retryButton
                        }
                        if failureAccessError?.recovery == .signIn {
                            resetSignInButton
                        }
                        if showsForgetPairingButton {
                            forgetPairingButton
                        }
                    }
                    showLogButton
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(platformColor: .windowBackgroundColor))
        .task(id: appState.engine.isChecking) {
            // Cycle the honest status copy while the session is `.starting`
            // (#3108). Render-only: readiness is owned by the session's single
            // poller (fast poll while starting, heartbeat while ready) — this
            // loop only advances the message index, it never probes or writes
            // backend state.
            guard appState.engine.isChecking else { return }
            while !Task.isCancelled, appState.engine.isChecking {
                try? await Task.sleep(for: .seconds(5))
                if Task.isCancelled { return }
                withAnimation(.easeInOut(duration: 0.4)) {
                    messageIndex = min(messageIndex + 1, Self.startupMessages.count - 1)
                }
            }
        }
        .task(id: appState.engine.isChecking) {
            // Dot animation — faster cadence so the splash stays alive between
            // message changes. Also purely visual; stops as soon as the session
            // leaves `.starting`.
            guard appState.engine.isChecking else { return }
            while !Task.isCancelled, appState.engine.isChecking {
                try? await Task.sleep(for: .milliseconds(450))
                if Task.isCancelled { return }
                withAnimation(.easeInOut(duration: 0.25)) {
                    dotPhase = (dotPhase + 1) % 3
                }
            }
        }
        .onChange(of: appState.isBackendRunning) { _, running in
            // The background heartbeat re-probes even while we're parked on a
            // startup failure (#3162). The moment it recovers readiness, clear
            // the failed status so the workspace shows instead of a stale
            // "Not Running" screen on a healthy engine.
            if running, backendService.status == .failed {
                backendService.status = .running
                backendService.errorMessage = nil
            }
        }
    }
}

#Preview {
    BackendConnectionView(appState: AppState())
        .frame(width: 600, height: 400)
}
