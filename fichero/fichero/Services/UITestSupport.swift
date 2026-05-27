import Foundation

// XCUITest support (#1230). These helpers live apart from the in-process
// `isRunningXCTests()` (in EmbeddedBackendService) because XCUITest runs the
// app as a SEPARATE process from the test runner — the XCTest runtime is NOT
// loaded here, so `isRunningXCTests()` is false. The runner signals intent via
// a launch argument and an env var instead.

/// True when the app was launched by the XCUITest harness. Used to neutralize
/// boot side effects (embedded-engine spawn, move-to-Applications prompt,
/// real-library restore) so the smoke tests launch fast against an isolated
/// library.
func isUITesting() -> Bool {
    ProcessInfo.processInfo.arguments.contains("--uitesting")
}

/// During UI testing the harness points the app at a disposable Application
/// Support directory (passed via `FICHERO_UITEST_HOME`) so the smoke tests
/// never read or write the developer's real `global.fichero`. Returns nil
/// outside UI tests or when the env var is unset.
func uiTestSupportDirectory() -> URL? {
    guard isUITesting(),
          let path = ProcessInfo.processInfo.environment["FICHERO_UITEST_HOME"],
          !path.isEmpty else { return nil }
    return URL(fileURLWithPath: path, isDirectory: true)
}
