import SwiftUI

/// Xcode-style consent prompt for an agent/MCP client connecting (#1847).
///
/// Mirrors the macOS "“X” wants to access…" alert: an icon, a bold headline
/// naming the client, a one-line explanation, a "Don't ask again this session"
/// checkbox, and a Deny / Approve pair (Approve is the default action). UI only
/// — it reports the decision through `onDecision`; provisioning happens in the
/// engine layer that will call `AgentConsentStore.requestConsent` later.
struct AgentConsentSheet: View {
    let request: AgentConsentRequest
    let onDecision: (_ approved: Bool, _ remember: Bool) -> Void

    @State private var remember = false

    private var explanation: String {
        request.purpose
            ?? "It will connect to this library through Fichero and act as a user with the "
                + "permissions you grant. You can revoke it any time in Settings."
    }

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "person.badge.key.fill")
                .font(.largeTitle)
                .imageScale(.large)
                .symbolRenderingMode(.hierarchical)
                .foregroundStyle(Color.accentColor)
                .accessibilityHidden(true)

            VStack(spacing: 8) {
                Text("\(request.clientName) wants to connect")
                    .font(.title3)
                    .fontWeight(.semibold)
                    .multilineTextAlignment(.center)
                Text(explanation)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Toggle("Don't ask again this session", isOn: $remember)
                .font(.callout)
                #if os(macOS)
                .toggleStyle(.checkbox)
                #endif

            HStack(spacing: 12) {
                Button("Deny", role: .cancel) {
                    onDecision(false, remember)
                }
                .keyboardShortcut(.cancelAction)

                Button("Approve") {
                    onDecision(true, remember)
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
            }
            .accessibilityElement(children: .contain)
        }
        .padding(28)
        .frame(maxWidth: 380)
    }
}

extension View {
    /// Presents `AgentConsentSheet` whenever `store` has a pending request, and
    /// feeds the decision back through `store.resolve`. Attach once high in the
    /// app's view tree; the engine layer raises requests via
    /// `store.requestConsent`. The sheet cannot be dismissed without a decision —
    /// silently walking away is not one of the two answers.
    func agentConsentPrompt(_ store: AgentConsentStore) -> some View {
        sheet(
            isPresented: Binding(
                get: { store.pending != nil },
                set: { presented in
                    // The sheet is dismissed only by resolving; treat an external
                    // close (should not happen with dismissal disabled) as a deny
                    // so a connection is never left hanging on a silent dismissal.
                    if !presented, store.pending != nil {
                        store.resolve(approved: false, remember: false)
                    }
                }
            )
        ) {
            if let request = store.pending {
                AgentConsentSheet(request: request) { approved, remember in
                    store.resolve(approved: approved, remember: remember)
                }
                .interactiveDismissDisabled()
            }
        }
    }
}

#if DEBUG
/// Drives the store so the preview exercises the real connect → prompt → decide
/// path, not just a static sheet.
private struct AgentConsentPreviewHarness: View {
    @State private var store = AgentConsentStore()
    @State private var lastResult: String = "—"

    var body: some View {
        VStack(spacing: 16) {
            Text("Last decision: \(lastResult)")
                .font(.headline)
            Button("Simulate agent connect") {
                Task {
                    let approved = await store.requestConsent(
                        AgentConsentRequest(clientName: "Claude Desktop")
                    )
                    lastResult = approved ? "Approved" : "Denied"
                }
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(40)
        .frame(width: 420, height: 220)
        .agentConsentPrompt(store)
    }
}

#Preview("Agent consent — live") {
    AgentConsentPreviewHarness()
}

#Preview("Agent consent — sheet") {
    AgentConsentSheet(
        request: AgentConsentRequest(
            clientName: "MCP · research-tools",
            purpose: "It wants to read documents and run workflows in this library."
        ),
        onDecision: { _, _ in }
    )
}
#endif
