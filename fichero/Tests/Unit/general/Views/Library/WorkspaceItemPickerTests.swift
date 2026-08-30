@testable import Fichero
import FicheroAPIClient
import OpenAPIRuntime
import XCTest

final class WorkspaceItemPickerTests: XCTestCase {

    func testWorkspaceCuratedItemMapsGeneratedPayloadContainer() throws {
        let payload = try Components.Schemas.WorkspaceItemsResponse.ItemsPayloadPayload(
            additionalProperties: OpenAPIObjectContainer(unvalidatedValue: [
                "id": "item-1",
                "target_type": "Document",
                "target_id": "doc-1",
                "role": "curated_item",
                "notes": "Read closely",
                "node_class": "claim_source",
            ])
        )

        let item = WorkspaceCuratedItem(payload: payload)

        XCTAssertEqual(item.id, "item-1")
        XCTAssertEqual(item.targetType, "Document")
        XCTAssertEqual(item.targetId, "doc-1")
        XCTAssertEqual(item.role, "curated_item")
        XCTAssertEqual(item.notes, "Read closely")
        XCTAssertEqual(item.nodeClass, "claim_source")
    }
}
