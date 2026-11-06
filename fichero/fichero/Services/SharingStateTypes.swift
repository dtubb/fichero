import Foundation

/// One connected client surface, as the Sharing pane shows it (2026-08-27).
struct ConnectedClientRecord: Identifiable, Equatable {
    var id: String { client }
    let client: String
    let lastSeen: String
    let requests: Int
    let transport: String
}

struct SharingStateRecord: Equatable {
    let tailnetURL: String?
    let tailnetServeCommand: String?
    let auditId: String?
    /// The host's addresses in one place (`sharing.state-names-every-address`): the sharing address the engine was started
    /// with, its LAN IP, and who holds the tailnet forward ("ours" | "foreign" | "none"); nil from an engine before the field.
    var publicBaseURL: String?
    var lanIP: String?
    var tailnetForward: String?
    /// Why Multi-user cannot be turned on yet (`multiuser_blocker`), nil when nothing blocks it.
    var multiuserBlocker: String?
    /// A tailnet forward Fichero did not make, with the command that frees it (`tailnet_serve_conflict`).
    var tailnetServeConflict: TailnetServeConflict?
    /// How many projects someone can open (`shared_library_count`, #6366); 0 asks which to share; nil from an older engine.
    var sharedLibraryCount: Int?
}
