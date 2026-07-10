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
}
