@testable import Fichero
import Foundation
import XCTest

/// Tests for SidebarSearchTypes — SavedSearch, SearchFilters, DateRange,
/// WorkflowSidebarItem. Locks snake_case keys (load-bearing for the
/// search-persistence + workflow-list backend round-trips) and the
/// init defaults relied on by "+ New" sidebar actions.
final class SidebarSearchTypesTests: XCTestCase {

    // MARK: - SavedSearch

    func testSavedSearchInitDefaults() {
        let search = SavedSearch(name: "Recent")
        XCTAssertFalse(search.id.isEmpty)  // UUID default
        XCTAssertEqual(search.query, "")
        XCTAssertEqual(search.searchType, "hybrid")
        XCTAssertEqual(search.sortBy, "relevance")
        XCTAssertEqual(search.sortDirection, "desc")
        XCTAssertEqual(search.icon, "magnifyingglass")
        XCTAssertFalse(search.isSmartSearch)
        XCTAssertEqual(search.folderPath, "/")
        XCTAssertEqual(search.sortOrder, 0)
    }

    func testSavedSearchSnakeCaseEncode() throws {
        let search = SavedSearch(
            id: "s-1", name: "Gold",
            query: "gold mining",
            filters: SearchFilters(),
            searchType: "semantic",
            sortBy: "name",
            sortDirection: "asc",
            icon: "star",
            isSmartSearch: true,
            folderPath: "/Pinned",
            sortOrder: 3,
            createdAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let data = try JSONEncoder().encode(search)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["id"] as? String, "s-1")
        XCTAssertEqual(json?["search_type"] as? String, "semantic")
        XCTAssertEqual(json?["sort_by"] as? String, "name")
        XCTAssertEqual(json?["sort_direction"] as? String, "asc")
        XCTAssertEqual(json?["is_smart_search"] as? Bool, true)
        XCTAssertEqual(json?["folder_path"] as? String, "/Pinned")
        XCTAssertEqual(json?["sort_order"] as? Int, 3)
        XCTAssertNotNil(json?["created_at"])
    }

    func testSavedSearchRoundTrip() throws {
        // Use the matching strategy on both sides so Date round-trips.
        let original = SavedSearch(
            id: "s-1", name: "Test", query: "x",
            searchType: "semantic", sortBy: "date", sortDirection: "asc",
            isSmartSearch: true, folderPath: "/a", sortOrder: 2,
            createdAt: Date(timeIntervalSince1970: 0)
        )
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let data = try encoder.encode(original)
        let decoded = try decoder.decode(SavedSearch.self, from: data)
        XCTAssertEqual(decoded.id, original.id)
        XCTAssertEqual(decoded.query, "x")
        XCTAssertEqual(decoded.searchType, "semantic")
        XCTAssertEqual(decoded.sortBy, "date")
        XCTAssertEqual(decoded.sortDirection, "asc")
        XCTAssertTrue(decoded.isSmartSearch)
        XCTAssertEqual(decoded.folderPath, "/a")
        XCTAssertEqual(decoded.sortOrder, 2)
    }

    // MARK: - SearchFilters

    func testSearchFiltersInitNilDefaults() {
        let filters = SearchFilters()
        XCTAssertNil(filters.docTypes)
        XCTAssertNil(filters.fileTypes)
        XCTAssertNil(filters.statuses)
        XCTAssertNil(filters.dateRange)
        XCTAssertNil(filters.hasContent)
    }

    func testSearchFiltersRoundTrip() throws {
        let filters = SearchFilters(
            docTypes: [.file], fileTypes: [.pdf],
            statuses: [.completed],
            dateRange: DateRange(start: nil, end: nil),
            hasContent: true
        )
        let data = try JSONEncoder().encode(filters)
        let decoded = try JSONDecoder().decode(SearchFilters.self, from: data)
        XCTAssertEqual(decoded.docTypes, [.file])
        XCTAssertEqual(decoded.fileTypes, [.pdf])
        XCTAssertEqual(decoded.statuses, [.completed])
        XCTAssertEqual(decoded.hasContent, true)
    }

    func testSearchFiltersOmitsNilFields() throws {
        let filters = SearchFilters(hasContent: false)
        let data = try JSONEncoder().encode(filters)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        // Nil fields encode as absent (Optional default behaviour) —
        // backend treats absence as "no constraint".
        XCTAssertNil(json?["docTypes"])
        XCTAssertNil(json?["fileTypes"])
        XCTAssertEqual(json?["hasContent"] as? Bool, false)
    }

    func testDateRangeAllowsBothNil() throws {
        let range = DateRange(start: nil, end: nil)
        let data = try JSONEncoder().encode(range)
        let decoded = try JSONDecoder().decode(DateRange.self, from: data)
        XCTAssertNil(decoded.start)
        XCTAssertNil(decoded.end)
    }

    // MARK: - WorkflowSidebarItem

    func testWorkflowSidebarItemDefaults() {
        let item = WorkflowSidebarItem(name: "New Workflow")
        XCTAssertFalse(item.id.isEmpty)
        XCTAssertEqual(item.nodeCount, 0)
        XCTAssertEqual(item.edgeCount, 0)
        XCTAssertTrue(item.isEnabled)
        XCTAssertEqual(item.folderPath, "/")
        XCTAssertEqual(item.sortOrder, 0)
        XCTAssertFalse(item.isSystem)
    }

    func testWorkflowSidebarItemDecodesSnakeCase() throws {
        let json = Data("""
        {
            "id": "wf-1", "name": "Catalogue",
            "description": "Processes documents",
            "node_count": 5, "edge_count": 4,
            "is_enabled": true,
            "folder_path": "/AI",
            "sort_order": 2,
            "is_system": true,
            "created_at": "2026-05-11T08:00:00Z",
            "updated_at": "2026-05-11T08:30:00Z"
        }
        """.utf8)
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let item = try decoder.decode(WorkflowSidebarItem.self, from: json)
        XCTAssertEqual(item.id, "wf-1")
        XCTAssertEqual(item.nodeCount, 5)
        XCTAssertEqual(item.edgeCount, 4)
        XCTAssertTrue(item.isEnabled)
        XCTAssertEqual(item.folderPath, "/AI")
        XCTAssertEqual(item.sortOrder, 2)
        XCTAssertTrue(item.isSystem)
    }

    func testWorkflowSidebarItemSnakeCaseEncode() throws {
        let item = WorkflowSidebarItem(
            id: "wf-1", name: "Test",
            description: "x",
            nodeCount: 1, edgeCount: 0,
            isEnabled: false,
            folderPath: "/x", sortOrder: 7,
            isSystem: true
        )
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(item)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["node_count"] as? Int, 1)
        XCTAssertEqual(json?["edge_count"] as? Int, 0)
        XCTAssertEqual(json?["is_enabled"] as? Bool, false)
        XCTAssertEqual(json?["folder_path"] as? String, "/x")
        XCTAssertEqual(json?["sort_order"] as? Int, 7)
        XCTAssertEqual(json?["is_system"] as? Bool, true)
    }

    func testWorkflowSidebarItemHashable() {
        // Sidebar List(selection:) requires Hashable to dedupe selection
        // diffs. Two items with the same id + identical createdAt /
        // updatedAt must hash equal. (Default `Date()` defaults differ
        // at sub-second precision — pin them.)
        let fixed = Date(timeIntervalSince1970: 0)
        let firstItem = WorkflowSidebarItem(id: "x", name: "A", createdAt: fixed, updatedAt: fixed)
        let secondItem = WorkflowSidebarItem(id: "x", name: "A", createdAt: fixed, updatedAt: fixed)
        XCTAssertEqual(firstItem, secondItem)
        XCTAssertEqual(firstItem.hashValue, secondItem.hashValue)
    }
}
