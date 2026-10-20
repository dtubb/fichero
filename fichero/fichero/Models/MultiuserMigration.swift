import Foundation

/// One-time launch migration for #5914 (## 609). Until then the app switched Multi-user by handing its engine
/// `FICHERO_MULTIUSER`, so the engine never persisted the choice; the app no longer passes it, so an install whose app
/// preference says ON and whose engine says OFF is turned on ONCE through the engine's route, else the update would switch
/// Multi-user off silently and lock out the people invited. If the route refuses (no owner password chosen yet) the person is
/// told once and it is not tried again: it never loops. After it the app's local copy follows the engine, never the reverse.
@MainActor
enum MultiuserMigration {
    static let triedKey = "fichero.multiuser.migration5914.tried"
    static let noteKey = "fichero.multiuser.migration5914.note"

    static func shouldPush(localOn: Bool, engineOn: Bool, alreadyTried: Bool, engineIsLocal: Bool) -> Bool {
        localOn && !engineOn && !alreadyTried && engineIsLocal
    }

    static func note(for reason: String) -> String {
        // Dev Local pins the variable: its refusal names the environment, which the person cannot act on.
        if reason.contains("FICHERO_MULTIUSER") {
            return "Multi-user was on before this update, but this engine was started with it fixed by its launcher, so it was not carried over."
        }
        return "Multi-user was on before this update and could not be carried over: \(reason)"
    }

    /// Only an answer from the engine (success or a refusal) spends the one try; a transport error is tried again next launch,
    /// and so is a 401: the engine did not hear the owner (its credential was not accepted), it did not say no.
    static func engineAnswered(_ error: Error) -> Bool {
        guard let api = error as? APIError else { return false }
        switch api {
        case .invalidResponse, .connectionFailed: return false
        case .httpError(let code, _): return code != 401
        case .badRequest, .notFound, .serverError: return true
        }
    }

    /// True when it asked the engine to turn Multi-user on (so the caller reads the engine's state again).
    @discardableResult
    static func run(
        engineOn: Bool, engineIsLocal: Bool, defaults: UserDefaults, turnOn: () async throws -> Void
    ) async -> Bool {
        let local = defaults.object(forKey: EngineConfig.multiuserEnabledKey) != nil
            && defaults.bool(forKey: EngineConfig.multiuserEnabledKey)
        guard shouldPush(
            localOn: local, engineOn: engineOn, alreadyTried: defaults.bool(forKey: triedKey), engineIsLocal: engineIsLocal
        ) else { return false }
        do {
            try await turnOn()
            defaults.set(true, forKey: triedKey)
            defaults.removeObject(forKey: noteKey)
        } catch {
            guard engineAnswered(error) else { return false }  // nothing answered: not spent, tried again next launch
            defaults.set(true, forKey: triedKey)  // the engine said no: once, never a loop
            defaults.set(note(for: error.localizedDescription), forKey: noteKey)
        }
        return true
    }

    /// The app's local copy of the switch follows the engine (the sidebar and inspector read it).
    static func follow(engineOn: Bool, defaults: UserDefaults) {
        defaults.set(engineOn, forKey: EngineConfig.multiuserEnabledKey)
    }

    /// The migration's refusal, once, for the Sharing pane to show.
    static func takeNote(defaults: UserDefaults) -> String? {
        guard let text = defaults.string(forKey: noteKey) else { return nil }
        defaults.removeObject(forKey: noteKey)
        return text
    }
}
