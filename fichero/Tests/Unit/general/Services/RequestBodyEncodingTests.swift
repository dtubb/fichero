@testable import Fichero
import XCTest

/// Tests for MCP + Provider request bodies — snake_case encode + optional
/// omission for partial updates. Pure encode logic, no live engine.
final class RequestBodyEncodingTests: XCTestCase {

    private func encodeToDict<T: Encodable>(_ value: T) throws -> [String: Any] {
        let data = try JSONEncoder().encode(value)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    // MARK: - CreateMCPServerRequest

    func testCreateMCPServerEncodesToolNamePrefixSnakeCase() throws {
        let req = CreateMCPServerRequest(name: "srv", transport: "stdio",
                                         toolNamePrefix: true, enabled: false)
        let obj = try encodeToDict(req)
        XCTAssertEqual(obj["name"] as? String, "srv")
        XCTAssertEqual(obj["transport"] as? String, "stdio")
        XCTAssertEqual(obj["tool_name_prefix"] as? Bool, true)  // ← snake_case
        XCTAssertEqual(obj["enabled"] as? Bool, false)
        XCTAssertNil(obj["toolNamePrefix"])  // camelCase never leaks
    }

    // MARK: - UpdateMCPServerRequest (partial update omits nil)

    func testUpdateMCPServerOmitsNilFields() throws {
        let req = UpdateMCPServerRequest(enabled: true)  // only enabled set
        let obj = try encodeToDict(req)
        XCTAssertEqual(obj["enabled"] as? Bool, true)
        XCTAssertNil(obj["name"])
        XCTAssertNil(obj["transport"])
        XCTAssertNil(obj["tool_name_prefix"])
    }

    func testUpdateMCPServerEncodesToolNamePrefixWhenSet() throws {
        let req = UpdateMCPServerRequest(toolNamePrefix: false)
        let obj = try encodeToDict(req)
        XCTAssertEqual(obj["tool_name_prefix"] as? Bool, false)  // ← snake_case
        XCTAssertNil(obj["enabled"])
    }

    // MARK: - UpdateProviderRequest

    func testUpdateProviderEncodesSnakeCaseAndOmitsNil() throws {
        let req = UpdateProviderRequest(name: nil, apiBase: "https://api.test",
                                        enabled: true, apiKey: nil)
        let obj = try encodeToDict(req)
        XCTAssertEqual(obj["api_base"] as? String, "https://api.test")  // ← api_base
        XCTAssertEqual(obj["enabled"] as? Bool, true)
        XCTAssertNil(obj["name"])      // nil omitted
        XCTAssertNil(obj["api_key"])   // nil omitted
        XCTAssertNil(obj["apiBase"])   // camelCase never leaks
    }

    func testUpdateProviderEncodesApiKeySnakeCase() throws {
        let req = UpdateProviderRequest(name: "p", apiBase: nil, enabled: nil, apiKey: "sk-1")
        let obj = try encodeToDict(req)
        XCTAssertEqual(obj["api_key"] as? String, "sk-1")  // ← api_key
        XCTAssertEqual(obj["name"] as? String, "p")
        XCTAssertNil(obj["enabled"])
    }

    // MARK: - SetAPIKeyRequest

    func testSetAPIKeyEncodesApiKeySnakeCase() throws {
        let obj = try encodeToDict(SetAPIKeyRequest(apiKey: "sk-9"))
        XCTAssertEqual(obj["api_key"] as? String, "sk-9")
        XCTAssertNil(obj["apiKey"])
        XCTAssertEqual(obj.keys.count, 1)
    }
}
