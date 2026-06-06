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
            "folder",
            "aggregate",
            "transcribe",
            "extract_all",
            "kg_writer",
            "catalogue",
            "citations_extract",
            "extract_entities",
            "key_people",
            "timeline",
            "keywords",
            "summarize_file",
            "people_folder_cleanup",
            "places_folder_cleanup",
            "organizations_folder_cleanup",
            "dates_folder_cleanup",
            "events_folder_cleanup",
            "keywords_folder_cleanup"
        ]

        let enabled = featureManager.workflowEnabledTools
        let missing = required.subtracting(enabled)
        XCTAssertTrue(
            missing.isEmpty,
            "Catalogue workflow requires these tools enabled in v0.0.1 allowlist: \(missing.sorted())"
        )
    }
}
