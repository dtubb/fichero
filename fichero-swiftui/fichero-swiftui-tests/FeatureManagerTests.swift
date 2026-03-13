import XCTest
@testable import Fichero

@MainActor
final class FeatureManagerTests: XCTestCase {
    func testV001DefaultsDisableOffTierSurfaces() {
        let featureManager = FeatureManager.shared
        featureManager.resetToV001()

        XCTAssertTrue(featureManager.isLibraryEnabled)
        XCTAssertTrue(featureManager.isSearchEnabled)

        XCTAssertFalse(featureManager.isChatEnabled)
        XCTAssertFalse(featureManager.isWorkflowsEnabled)
        XCTAssertFalse(featureManager.isBatchesEnabled)
        XCTAssertFalse(featureManager.isAutomationEnabled)
        XCTAssertFalse(featureManager.isActivityEnabled)
    }
}
