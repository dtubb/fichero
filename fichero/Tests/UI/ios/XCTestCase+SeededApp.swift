#if os(iOS)
import XCTest

/// What the iPhone UI tests on the seeded harness engine share: the launch and the library row lookup.
extension XCTestCase {
    /// Launches the app's real root view against the engine `scripts/run_ios_ui_sim.sh` starts; it FAILS, not skips,
    /// when that engine is missing.
    func launchSeededApp() throws -> XCUIApplication {
        let env = ProcessInfo.processInfo.environment
        let socket = try XCTUnwrap(env["FICHERO_FORCE_UDS_PATH"], "run through scripts/run_ios_ui_sim.sh: no engine socket")
        let library = try XCTUnwrap(env["FICHERO_UITEST_LIBRARY"], "run through scripts/run_ios_ui_sim.sh: no seeded project")
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "-fichero.remote_access.paired_library_path", library]
        app.launchEnvironment["FICHERO_FORCE_UDS_PATH"] = socket
        app.launch()
        return app
    }

    func row(_ app: XCUIApplication, containing name: String) -> XCUIElement {
        app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'libraryRow.' AND label CONTAINS %@", name)).firstMatch
    }
}
#endif
