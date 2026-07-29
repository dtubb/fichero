@testable import Fichero
import XCTest

/// The enabled-gate for workflow completion notifications (#1869).
///
/// The single on/off preference must default ON — an unset key reads as enabled —
/// and honour an explicit off. This is the non-UI logic worth pinning: the
/// notifier posts nothing (and never prompts for authorization) when it is off,
/// so a wrong default here would either spam or silence every run.
final class WorkflowCompletionNotifierTests: XCTestCase {

    private let key = WorkflowCompletionNotifier.enabledDefaultsKey

    /// Save + restore the real defaults value so the test never leaks state.
    private func withCleanDefault(_ body: () -> Void) {
        let defaults = EngineConfig.defaults
        let saved = defaults.object(forKey: key)
        defer {
            if let saved { defaults.set(saved, forKey: key) } else { defaults.removeObject(forKey: key) }
        }
        defaults.removeObject(forKey: key)
        body()
    }

    func testDefaultsToEnabledWhenUnset() {
        withCleanDefault {
            XCTAssertTrue(
                WorkflowCompletionNotifier.isEnabled,
                "an unset preference must default ON, not off"
            )
        }
    }

    func testDisabledWhenExplicitlyOff() {
        withCleanDefault {
            EngineConfig.defaults.set(false, forKey: key)
            XCTAssertFalse(WorkflowCompletionNotifier.isEnabled)
        }
    }

    func testEnabledWhenExplicitlyOn() {
        withCleanDefault {
            EngineConfig.defaults.set(true, forKey: key)
            XCTAssertTrue(WorkflowCompletionNotifier.isEnabled)
        }
    }
}
