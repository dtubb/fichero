@testable import Fichero
import Foundation

/// Clears the throwaway preference suite tests read and write (#4221).
///
/// Tests used `UserDefaults.standard`, which in a test host IS
/// `app.fichero.fichero` — the domain the running app reads. A green test run
/// therefore repointed the user's live app at `https://second.tailnet.example`,
/// a reserved name that can never resolve, and he saw "Couldn't Load Documents"
/// and reasonably blamed the engine. It happened twice in one day.
///
/// **This type does NOT provide the isolation.** `EngineConfig.defaults` is a
/// computed property returning a throwaway suite whenever the process is a test
/// host, so the real domain is unreachable from a test with or without this
/// helper. That matters: the previous fix was snapshot-and-restore in
/// `tearDown`, which protects only runs that finish — and four of six runs on
/// the day this was found died by kill. Isolation that depends on orderly
/// shutdown is not isolation.
///
/// What this DOES is empty the suite between tests, so state from an earlier
/// test — or from a run that was killed before its teardown — cannot leak into
/// the next one. That is the same failure mode as the real domain, one level
/// down, and it is worth preventing even though it harms only the suite.
enum TestDefaults {
    /// Empty the test suite. Call from `setUp`.
    ///
    /// `removePersistentDomain`, NOT a `dictionaryRepresentation()` loop: the
    /// dictionary MERGES NSGlobalDomain (~91 keys on a fresh suite), and
    /// `removeObject` posts `didChangeNotification` even for keys that are
    /// absent (#4104) — so the loop fired ~91 notifications per setUp at the
    /// hosted app's AttributeGraph. Removing the persistent domain touches
    /// only suite-owned keys and posts once.
    static func reset() {
        EngineConfig.defaults.removePersistentDomain(forName: EngineConfig.testSuiteName)
    }

    /// Kept for symmetry at call sites that clear on the way out as well as in.
    /// Best-effort by nature — a killed process runs neither — which is
    /// acceptable ONLY because nothing here protects the real domain.
    static func uninstall() {
        reset()
    }
}
