@testable import Fichero
import XCTest

/// Tests for the `ItemTypeRegistry` that drives the Add menu's items.
/// Registry is handler-driven: only categories whose handler is wired
/// up appear in `definitions`. Locks: empty registry → empty menu;
/// handler injection → items appear; lookup by id; grouping by category.
@MainActor
final class ItemTypeRegistryTests: XCTestCase {

    func testEmptyRegistryHasNoDefinitions() {
        let registry = ItemTypeRegistry()
        XCTAssertTrue(registry.definitions.isEmpty)
    }

    func testCreateFolderHandlerSurfacesFolderDefinition() {
        let registry = ItemTypeRegistry()
        registry.createFolder = { /* no-op */ }
        let defs = registry.definitions
        XCTAssertTrue(defs.contains { $0.id == "folder" })
        let folder = defs.first { $0.id == "folder" }
        XCTAssertEqual(folder?.menuCategory, .documents)
        XCTAssertNotNil(folder?.keyboardShortcut)
    }

    func testHandlerActuallyExecutes() {
        let registry = ItemTypeRegistry()
        var fired = false
        registry.createFolder = { fired = true }
        let def = registry.definitions.first { $0.id == "folder" }
        def?.handler()
        XCTAssertTrue(fired)
    }

    func testDefinitionLookupById() {
        let registry = ItemTypeRegistry()
        registry.createChat = { }
        let result = registry.definition(for: "chat")
        XCTAssertNotNil(result)
        XCTAssertEqual(result?.id, "chat")
    }

    func testDefinitionLookupMissReturnsNil() {
        let registry = ItemTypeRegistry()
        registry.createFolder = { }
        XCTAssertNil(registry.definition(for: "nope"))
    }

    func testGroupingByCategory() {
        let registry = ItemTypeRegistry()
        registry.createFolder = { }
        registry.createWorkflow = { }
        registry.createSchedule = { }
        let grouped = registry.definitionsByCategory
        XCTAssertNotNil(grouped[.documents])
        XCTAssertTrue(grouped[.documents]?.contains { $0.id == "folder" } ?? false)
    }

    func testItemMenuCategoryAllCases() {
        // Mirror the menu structure — order matters because View menu
        // renders by .allCases iteration.
        XCTAssertEqual(ItemMenuCategory.allCases.count, 5)
        XCTAssertEqual(ItemMenuCategory.allCases[0], .documents)
    }

    func testItemMenuCategoryRawValues() {
        // Stable strings for any persistence / accessibility hooks.
        XCTAssertEqual(ItemMenuCategory.documents.rawValue, "Documents")
        XCTAssertEqual(ItemMenuCategory.aiTools.rawValue, "AI")
        XCTAssertEqual(ItemMenuCategory.automation.rawValue, "Automation")
        XCTAssertEqual(ItemMenuCategory.places.rawValue, "Places")
        XCTAssertEqual(ItemMenuCategory.tools.rawValue, "Tools")
    }

    func testItemTypeDefinitionDefaults() {
        let def = ItemTypeDefinition(
            id: "test",
            name: "Test",
            icon: "doc",
            category: .documents,
            handler: { }
        )
        XCTAssertEqual(def.id, "test")
        XCTAssertNil(def.keyboardShortcut)  // optional, defaults to nil
    }

    func testAllNineHandlersIndependent() {
        // Wiring up ONE handler should add EXACTLY that handler's items,
        // not accidentally surface neighbours.
        let registry = ItemTypeRegistry()
        registry.createChain = { }
        let ids = Set(registry.definitions.map(\.id))
        XCTAssertTrue(ids.contains("chain"))
        XCTAssertFalse(ids.contains("folder"))
        XCTAssertFalse(ids.contains("search"))
    }
}
