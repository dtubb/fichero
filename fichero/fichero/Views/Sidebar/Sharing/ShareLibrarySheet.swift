import FicheroAPIClient
import SwiftUI

/// "Share this library…" surface (#3149, plan §5 F1).
///
/// Pick an existing account — or create a new person inline — assign a role,
/// and share: the engine grants the per-library role through the audited
/// `acl.set` action and returns a `share_url`, shown here to copy / send. The
/// members list manages current roles (change / revoke) via the *same* audited
/// ACL methods the sidebar `LibrarySharingBadge` uses (`setLibraryRole` /
/// `revokeLibraryRole`) — this iterates on that #2869 surface, it does not
/// replace it.
///
/// Presented from the badge popover, so it only appears when multi-user mode is
/// on for this library.
struct ShareLibrarySheet: View {
    let library: LibraryManager.LibraryReference
    let usersStore: UsersStore

    @Environment(\.dismiss) private var dismiss

    // The reachable-host + pin state that turns a role grant into a link someone
    // can actually open. Same @AppStorage keys the one pairing surface owns
    // (ShareSettingsView), so this reflects whether sharing is on and where.
    @AppStorage(RemoteAccessConfig.publicBaseURLKey) var publicBaseURL = ""
    @AppStorage(RemoteAccessConfig.hostingEnabledKey) var hostingEnabled = false
    @AppStorage(RemoteAccessConfig.bonjourEnabledKey) var bonjourEnabled = false

    // Optional so this cross-platform sheet never traps if presented outside the
    // main window's environment (e.g. iOS). When present (the macOS sidebar case),
    // "Share" can do its OWN host/cert setup instead of sending the user to Settings
    // — you share a thing by sharing it, not by first enabling a subsystem (#3776).
    @Environment(EmbeddedBackendService.self) var backendService: EmbeddedBackendService?
    @Environment(AppState.self) var appState: AppState?
    @Environment(LibraryManager.self) var libraryManager: LibraryManager?

    // Share form
    @State var personChoice: String = ""
    @State var role = "viewer"
    @State var isSharing = false
    // Set once the role grant succeeds — the "Share Link" section appears then.
    @State var didShare = false
    // The short-lived, single-use pair code minted for the link — SAME code
    // semantics as the QR. nil until minted; the link cannot exist without it.
    @State var pairingCode: PairingCodeRecord?
    @State var spkiPin = ""
    @State var shareError: String?
    @State var copied = false

    // Inline "New person…" create
    @State var newDisplayName = ""
    @State var newUsername = ""
    @State var newPassword = ""
    @State var isCreating = false
    @State var createError: String?

    // Members
    @State var members: [Components.Schemas.LibraryMember] = []
    @State var isLoadingMembers = false
    @State var membersError: String?
    @State var isApplying = false
    @State var manageError: String?

    /// The share sheet grants Viewer/Editor only — Owner is deliberately NOT here
    /// (#3787). Owner is a whole-library administrator, granted on purpose in
    /// Settings → People, not handed out casually while sharing with someone. The
    /// engine still enforces >=1 owner, so downgrading the last owner from here is
    /// refused with an honest error, never silently.
    static let shareRoles = ["editor", "viewer"]
    static let newPersonTag = "__new_person__"

    var body: some View {
        NavigationStack {
            Form {
                shareSection
                if didShare {
                    shareLinkSection
                }
                membersSection
            }
            .formStyle(.grouped)
            .navigationTitle("Share Library")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .frame(minWidth: 420, minHeight: 480)
        .task { await loadEverything() }
    }
}
