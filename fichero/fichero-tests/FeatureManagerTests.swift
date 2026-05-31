@testable import Fichero
import XCTest

@MainActor
final class FeatureManagerTests: XCTestCase {
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
        // Mind Palace ships ON during dev (Daniel-facing); revisit before release.
        XCTAssertTrue(featureManager.isMindPalaceEnabled)
        // Workflow execution surfaces promoted to release defaults (#252).
        XCTAssertTrue(featureManager.isWorkflowImportExportEnabled)
        XCTAssertTrue(featureManager.isWorkflowLangGraphPreviewEnabled)
        XCTAssertTrue(featureManager.isWorkflowFilesToolbarButtonEnabled)
        XCTAssertTrue(featureManager.isWorkflowRunOnSelectionEnabled)

        // Disabled in v0.0.1
        XCTAssertFalse(featureManager.isChatEnabled)
        XCTAssertFalse(featureManager.isBatchesEnabled)
        XCTAssertFalse(featureManager.isAutomationEnabled)
    }
}
