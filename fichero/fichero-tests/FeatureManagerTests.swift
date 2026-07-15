@testable import Fichero
import XCTest

@MainActor
final class FeatureManagerTests: XCTestCase {
    private func withFeatureTier<T>(_ tier: String, body: () throws -> T) rethrows -> T {
        let key = "FICHERO_FEATURE_TIER"
        let previous = ProcessInfo.processInfo.environment[key]
        setenv(key, tier, 1)
        defer {
            if let previous {
                setenv(key, previous, 1)
            } else {
                unsetenv(key)
            }
        }
        return try body()
    }

    func testV001DefaultsDisableOffTierSurfaces() {
        let featureManager = FeatureManager.shared
        featureManager.resetToV001()

        // Enabled in v0.0.1
        XCTAssertTrue(featureManager.isLibraryEnabled)
        XCTAssertTrue(featureManager.isSearchEnabled)
        XCTAssertTrue(featureManager.isWorkflowsEnabled)
        XCTAssertTrue(featureManager.isWorkflowEditorAdvancedViewsEnabled)
        XCTAssertTrue(featureManager.isActivityEnabled)
        XCTAssertTrue(featureManager.isSettingsGeneralTabEnabled)
        // Workflow execution surfaces promoted to release defaults (#252).
        XCTAssertTrue(featureManager.isWorkflowImportExportEnabled)
        XCTAssertTrue(featureManager.isWorkflowLangGraphPreviewEnabled)
        XCTAssertTrue(featureManager.isWorkflowFilesToolbarButtonEnabled)
        XCTAssertTrue(featureManager.isWorkflowRunOnSelectionEnabled)

        // Batches promoted to v0.0.1 defaults alongside workflows.
        XCTAssertTrue(featureManager.isBatchesEnabled)

        // Disabled in v0.0.1
        XCTAssertFalse(featureManager.isChatEnabled)
        XCTAssertFalse(featureManager.isAutomationEnabled)
    }

    func testAlphaBuildDefaultsExposeInternalReviewSettingsAndIntegrationSurfaces() {
        let featureManager = FeatureManager.shared

        withFeatureTier("alpha") {
            featureManager.resetToV001()

            XCTAssertTrue(featureManager.isSettingsEngineTabEnabled)
            XCTAssertTrue(featureManager.isSettingsShareTabEnabled)
            XCTAssertTrue(featureManager.isSettingsUsersTabEnabled)
            XCTAssertTrue(featureManager.isSettingsCaptureTabEnabled)
            XCTAssertTrue(featureManager.isSettingsBackendTabEnabled)
            XCTAssertTrue(featureManager.isSettingsModelsTabEnabled)
            XCTAssertTrue(featureManager.isMCPEnabled)
            XCTAssertTrue(featureManager.isIntegrationsEnabled)
        }
    }

    func testReleaseBuildStillHidesInternalReviewSurfaces() {
        let featureManager = FeatureManager.shared

        withFeatureTier("release") {
            featureManager.resetToV001()

            XCTAssertFalse(featureManager.isSettingsEngineTabEnabled)
            XCTAssertFalse(featureManager.isSettingsShareTabEnabled)
            XCTAssertFalse(featureManager.isSettingsUsersTabEnabled)
            XCTAssertFalse(featureManager.isSettingsCaptureTabEnabled)
            XCTAssertFalse(featureManager.isSettingsBackendTabEnabled)
            XCTAssertFalse(featureManager.isSettingsModelsTabEnabled)
            XCTAssertFalse(featureManager.isMCPEnabled)
            XCTAssertFalse(featureManager.isIntegrationsEnabled)
        }
    }

    // The Library Access pane (People / Devices+QR / Capture) holds real, keepable
    // capabilities, so its EXISTENCE must not hang off the `.alpha`-tier
    // `settings_share_tab` flag — that hid the QR from beta testers ("nowhere to
    // turn on the qrcode", #3811). It is reachable in internal + tester builds and
    // still hidden in release until the fail-closed engine-refusal P0 lands (#3776).
    func testLibraryAccessSettingsReachableForTestersHiddenInRelease() {
        XCTAssertTrue(SettingsView.showsLibraryAccessSettings(tier: .dev))
        XCTAssertTrue(SettingsView.showsLibraryAccessSettings(tier: .alpha))
        // The regression case: beta testers must see the sharing/QR pane.
        XCTAssertTrue(SettingsView.showsLibraryAccessSettings(tier: .beta))
        // Release stays gated until #3776's P0 verification.
        XCTAssertFalse(SettingsView.showsLibraryAccessSettings(tier: .release))
    }
}
