#if os(iOS) || os(visionOS)
import SwiftUI

/// Try again / Copy details / Open Tailscale / Open Settings under a pairing failure's sentence (`PairingFailureActions`),
/// shared by the link sheet and the Connect screen so both say and offer the same (`sharing.ios-says-which-step`).
struct PairingFailureButtons: View {
    let failure: PairingFailureError?
    let message: String
    /// Try again: the link sheet pairs again; the Connect screen opens the scanner again.
    let retry: () -> Void
    @Environment(\.openURL) private var openURL

    var body: some View {
        ForEach(PairingFailureActions.actions(for: failure?.failure, host: failure?.context.host ?? ""), id: \.self) { action in
            Button(PairingFailureActions.title(action)) { perform(action) }
                .buttonStyle(action == .tryAgain ? .borderedProminent : .bordered)
        }
    }

    private func perform(_ action: PairingFailureActions.Action) {
        switch action {
        case .tryAgain:
            retry()
        case .copyDetails:
            if let failure {
                PlatformPasteboard.writeString(PairingFailureActions.details(failure.failure, context: failure.context))
            } else {
                PlatformPasteboard.writeString(message)
            }
        case .openSettings:
            if let settings = URL(string: PairingFailureActions.settingsURL) { openURL(settings) }
        case .openTailscale:
            // The app if it is installed, else its App Store page.
            if let app = URL(string: PairingFailureActions.tailscaleURL), let store = URL(string: PairingFailureActions.tailscaleStoreURL) {
                openURL(app) { accepted in if !accepted { openURL(store) } }
            }
        }
    }
}

#Preview("Pairing failure buttons") {
    List {
        Text(PairingFailure.tailnetNameNotFound.sentence(.init(host: "studio.tail1234.ts.net")))
        PairingFailureButtons(
            failure: PairingFailureError(failure: .tailnetNameNotFound, context: .init(host: "studio.tail1234.ts.net")),
            message: "",
            retry: {}
        )
    }
}
#endif
