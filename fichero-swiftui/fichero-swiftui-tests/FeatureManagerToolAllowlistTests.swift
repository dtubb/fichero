@testable import Fichero
import XCTest

/// Guards the tools allowlist for v0.0.1 release profile — must include
/// the full set required for the Catalogue workflow to run. A missing
/// entry here means users can't actually build the demo pipeline.
@MainActor
final class FeatureManagerToolAllowlistTests: XCTestCase {

    func testAllowlistIncludesCatalogueWorkflowTools() {
        let featureManager = FeatureManager.shared
        featureManager.resetToV001()

        let required: Set<String> = [
            "files",
            "collection",
            "transcribe",
            "catalogue",
            "extract_entities",
            "key_people",
            "timeline",
            "keywords",
            "summarize_file"
        ]

        let enabled = featureManager.workflowEnabledTools
        let missing = required.subtracting(enabled)
        XCTAssertTrue(
            missing.isEmpty,
            "Catalogue workflow requires these tools enabled in v0.0.1 allowlist: \(missing.sorted())"
        )
    }
}
