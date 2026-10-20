#if canImport(AppKit)
import SwiftUI

extension ShareSettingsView {
    /// The engine's real multi-user state — the single source of truth (#3331),
    /// shared with the Accounts pane so both agree. Reads
    /// `GET /api/auth/identity` via IdentityStore, never the local desired flag.
    var backendMultiuser: Bool { appState.identityStore.multiuserEnabled }
}
#endif
