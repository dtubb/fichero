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

/// Opt-in UI-test mode that exercises the real embedded macOS engine. Normal
/// UI smoke tests remain inert so they can run without a Briefcase bundle.
func isEmbeddedEngineUITesting() -> Bool {
    isUITesting() && ProcessInfo.processInfo.arguments.contains("--uitesting-embedded")
}

/// A disposable restored-library fixture for the embedded-engine launch smoke.
/// It lives under the app's existing UI-test support directory, never in the
/// developer's defaults or library tree.
func uiTestRestoredLibraryURL() -> URL? {
    guard isEmbeddedEngineUITesting(),
          ProcessInfo.processInfo.environment["FICHERO_UITEST_RESTORE_LIBRARY"] == "1",
          let root = uiTestSupportDirectory() else {
        return nil
    }
    let library = root.appendingPathComponent("Restored.fichero", isDirectory: true)
    try? FileManager.default.createDirectory(at: library, withIntermediateDirectories: true)
    return library
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

/// Optional seeded library path for XCUITest reading-surface flows (#1242).
/// Preferred launch form: `--fichero-library /tmp/Seed.fichero`; env fallback
/// keeps shell-based smoke launches simple.
func uiTestLibraryOverrideURL(
    arguments: [String] = ProcessInfo.processInfo.arguments,
    environment: [String: String] = ProcessInfo.processInfo.environment
) -> URL? {
    guard arguments.contains("--uitesting") else { return nil }
    if let index = arguments.firstIndex(of: "--fichero-library"),
       arguments.indices.contains(index + 1) {
        let path = arguments[index + 1]
        if !path.isEmpty {
            return URL(fileURLWithPath: path)
        }
    }
    guard let path = environment["FICHERO_UITEST_LIBRARY"],
          !path.isEmpty else { return nil }
    return URL(fileURLWithPath: path)
}

@MainActor
func openUITestLibraryOverrideIfNeeded() {
    guard let libraryURL = uiTestLibraryOverrideURL() else { return }
    // Discard the returned LibraryReference: this UI-test hook only needs the
    // side effect (open the library and make it current); the caller reads the
    // active library through LibraryManager, not this return value (#3978).
    _ = LibraryManager.shared.openLibrary(at: libraryURL)
    // Test hook (InspectorFlowsUITests): deterministically open a seeded
    // document into the detail/inspector so the entities-load + KG-pane flows
    // don't depend on fragile double-click-through-folders navigation. The id
    // is honoured by `LibraryView.consumePendingOpen()`, which fetches it by id
    // (even when it's nested under a collection and not in the root listing).
    if let openId = uiTestOpenDocumentId() {
        LibraryManager.shared.pendingOpenDocumentId = openId
    }
}

/// Optional seeded-document id an XCUITest wants opened straight into the
/// detail/inspector at launch (`FICHERO_UITEST_OPEN_DOCUMENT`). Test hook only —
/// gated by `--uitesting` and nil otherwise. Consumed by
/// `LibraryView.consumePendingOpen()`.
func uiTestOpenDocumentId(
    arguments: [String] = ProcessInfo.processInfo.arguments,
    environment: [String: String] = ProcessInfo.processInfo.environment
) -> String? {
    guard arguments.contains("--uitesting"),
          let id = environment["FICHERO_UITEST_OPEN_DOCUMENT"],
          !id.isEmpty else { return nil }
    return id
}
