import Foundation

/// What Settings › Server shows and does (`sharing.settings.three-panes`, `sharing.settings.server-url-one-writer`, #5928):
/// the words and the rules, apart from the view, so they are tested without a window.
enum ServerSettingsText {
    static func status(running: Bool) -> String { running ? "Running" : "Stopped" }

    /// "app · fichero CLI · MCP": who has talked to the engine this session, once each; nothing to say when nobody has.
    static func clientsLine(_ names: [String]) -> String? {
        var seen = Set<String>()
        let unique = names.filter { seen.insert($0).inserted }
        return unique.isEmpty ? nil : unique.joined(separator: " · ")
    }

    static func canRestart(isRestarting: Bool, engineIsLocal: Bool) -> Bool { !isRestarting && engineIsLocal }

    /// The one red line under the Server URL field when it cannot be used; nothing when it can (blank means built-in).
    static func addressProblem(_ draft: String) -> String? {
        if case .invalid = EngineConfig.hostConfiguration(from: draft) { return "Address must start with https://" }
        return nil
    }
}

/// The Server URL field in Advanced. It edits a draft and commits through the ONE writer of the stored engine host
/// (`EngineHostSwitch`, #5916): this type never writes the host itself.
@MainActor
@Observable
final class ServerAdvancedModel {
    var draft = ""
    private(set) var error: String?
    private(set) var isApplying = false

    var problem: String? { ServerSettingsText.addressProblem(draft) }

    func sync(stored: String) { draft = stored }

    /// `switchHost(from, to, notResponding)` is `EngineHostSwitch.run`; an unchanged address is repointed and read again.
    func commit(stored: String, switchHost: (_ from: String, _ to: String, _ notResponding: String) async throws -> Void) async {
        guard problem == nil, !isApplying else { return }
        isApplying = true
        error = nil
        defer { isApplying = false }
        do {
            try await switchHost(
                stored, draft,
                draft == stored ? "The engine did not answer." : "That address did not answer, so the previous one is back.")
        } catch {
            self.error = error.localizedDescription
        }
    }
}
