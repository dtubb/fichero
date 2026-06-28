@testable import Fichero
import Foundation
import XCTest

/// Tests for IntegrationsServiceTypes — the integration DTOs (#1991 Services
/// coverage). Locks snake_case decoding, the Identifiable id fallbacks, the
/// name-only identity of AppIntegration, and the localized error strings.
final class IntegrationsServiceTypesTests: XCTestCase {

    // MARK: - AppIntegration

    func testAppIntegrationDecodesSnakeCaseAndComputed() throws {
        let json = Data("""
        {
            "name": "DEVONthink",
            "bundle_id": "com.devon-technologies.think3",
            "status": "available",
            "version": "3.9",
            "path": "/Applications/DEVONthink 3.app",
            "error": null
        }
        """.utf8)
        let integration = try JSONDecoder().decode(AppIntegration.self, from: json)
        XCTAssertEqual(integration.bundleId, "com.devon-technologies.think3")
        XCTAssertEqual(integration.id, "DEVONthink")
        XCTAssertTrue(integration.isAvailable)
    }

    func testAppIntegrationIsAvailableFalseWhenNotAvailable() throws {
        let json = Data("""
        {"name": "X", "bundle_id": "b", "status": "not_installed"}
        """.utf8)
        let integration = try JSONDecoder().decode(AppIntegration.self, from: json)
        XCTAssertFalse(integration.isAvailable)
        XCTAssertNil(integration.version)
    }

    func testAppIntegrationIdentityIsNameOnly() {
        // Equality/hash deliberately key on `name` only — same name, different
        // status, collapses to one element.
        let available = AppIntegration(
            name: "App", bundleId: "b", status: "available",
            version: nil, path: nil, error: nil
        )
        let unavailable = AppIntegration(
            name: "App", bundleId: "other", status: "not_installed",
            version: "9", path: "/x", error: "boom"
        )
        XCTAssertEqual(available, unavailable)
        XCTAssertEqual(Set([available, unavailable]).count, 1)
    }

    // MARK: - IntegrationItem / results

    func testIntegrationItemDecodesSnakeCaseAndId() throws {
        let json = Data("""
        {
            "external_id": "ext-1",
            "name": "Note",
            "source_app": "Bookends",
            "item_type": "reference",
            "file_path": null,
            "url": "x-bookends://ext-1",
            "content": "body",
            "metadata": {"k": "v"},
            "created_at": "2026-06-28",
            "modified_at": null
        }
        """.utf8)
        let item = try JSONDecoder().decode(IntegrationItem.self, from: json)
        XCTAssertEqual(item.id, "ext-1")
        XCTAssertEqual(item.sourceApp, "Bookends")
        XCTAssertEqual(item.itemType, "reference")
        XCTAssertEqual(item.metadata["k"], "v")
        XCTAssertNil(item.modifiedAt)
    }

    func testImportAndExportResultDecode() throws {
        let importResult = try JSONDecoder().decode(
            ImportResult.self,
            from: Data(#"{"success": true, "file_path": "/p", "error": null}"#.utf8)
        )
        XCTAssertTrue(importResult.success)
        XCTAssertEqual(importResult.filePath, "/p")

        let exportResult = try JSONDecoder().decode(
            ExportResult.self,
            from: Data(#"{"success": false, "external_id": null, "error": "nope"}"#.utf8)
        )
        XCTAssertFalse(exportResult.success)
        XCTAssertEqual(exportResult.error, "nope")
    }

    // MARK: - Identifiable id fallbacks

    func testLibraryTypeIdFallbacks() {
        XCTAssertEqual(DEVONthinkDatabase(name: "n", uuid: "u", path: nil).id, "u")
        XCTAssertEqual(DEVONthinkDatabase(name: "n", uuid: nil, path: "/p").id, "n")
        XCTAssertEqual(BookendsLibrary(name: "n", path: "/p").id, "/p")
        XCTAssertEqual(BookendsLibrary(name: "n", path: nil).id, "n")
        XCTAssertEqual(TinderboxDocument(name: "n", path: "/p").id, "/p")
        XCTAssertEqual(TinderboxDocument(name: "n", path: nil).id, "n")
    }

    // MARK: - IntegrationsError

    func testIntegrationsErrorDescriptions() {
        XCTAssertEqual(IntegrationsError.invalidURL.errorDescription, "Invalid URL")
        XCTAssertEqual(IntegrationsError.serverError.errorDescription, "Server error")
        XCTAssertEqual(IntegrationsError.createFailed.errorDescription, "Failed to create item")
        XCTAssertEqual(
            IntegrationsError.appNotAvailable("Bookends").errorDescription,
            "Bookends is not available"
        )
    }
}
