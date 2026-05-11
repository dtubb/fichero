@testable import Fichero
import SwiftUI
import XCTest

/// Tests for the LLM provider/model DTOs. Locks the snake_case decode
/// from the backend's catalogue endpoint, formatter outputs that the
/// model picker shows users (cost / context window), and the
/// capability-badge fan-out that drives the model row UI.
final class ProviderServiceTypesTests: XCTestCase {

    // MARK: - CreateProviderRequest

    func testCreateProviderRequestSnakeCase() throws {
        let req = CreateProviderRequest(
            providerType: "openai", name: "My OpenAI",
            apiBase: nil, apiKey: "sk-xxx"
        )
        let data = try JSONEncoder().encode(req)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["provider_type"] as? String, "openai")
        XCTAssertEqual(json?["api_key"] as? String, "sk-xxx")
        XCTAssertEqual(json?["name"] as? String, "My OpenAI")
    }

    func testAddModelRequestSnakeCase() throws {
        let req = AddModelRequest(
            providerId: "p-1", modelId: "gpt-4o", name: nil, isDefault: true
        )
        let data = try JSONEncoder().encode(req)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["provider_id"] as? String, "p-1")
        XCTAssertEqual(json?["model_id"] as? String, "gpt-4o")
        XCTAssertEqual(json?["is_default"] as? Bool, true)
    }

    func testSetAPIKeyRequestSnakeCase() throws {
        let data = try JSONEncoder().encode(SetAPIKeyRequest(apiKey: "k"))
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertEqual(json?["api_key"] as? String, "k")
    }

    // MARK: - ProviderCatalogEntry

    func testProviderCatalogEntryDecodesSnakeCase() throws {
        let json = """
        {
            "type": "openai", "name": "OpenAI",
            "description": "GPT models",
            "api_key_env": "OPENAI_API_KEY",
            "api_key_url": "https://platform.openai.com/api-keys",
            "is_local": false, "is_builtin": false,
            "supports_vision": true, "supports_embeddings": true,
            "supports_streaming": true,
            "default_model": "gpt-4o",
            "has_api_key": true,
            "icon": "brain", "logo_asset": "Providers/OpenAI",
            "color": "green", "sort_order": 10
        }
        """.data(using: .utf8)!
        let entry = try JSONDecoder().decode(ProviderCatalogEntry.self, from: json)
        XCTAssertEqual(entry.id, "openai")  // id is type
        XCTAssertEqual(entry.apiKeyEnv, "OPENAI_API_KEY")
        XCTAssertEqual(entry.defaultModel, "gpt-4o")
        XCTAssertTrue(entry.hasApiKey)
        XCTAssertEqual(entry.logoAsset, "Providers/OpenAI")
        XCTAssertEqual(entry.sortOrder, 10)
    }

    func testProviderCatalogEntryColorMap() {
        // Backend ships a color name string; the frontend maps it to a
        // SwiftUI Color. Unknown colors fall back to accentColor so the
        // UI never breaks on a new server-side color name.
        let pairs: [(String, Color)] = [
            ("gray", .gray), ("blue", .blue), ("purple", .purple),
            ("indigo", .indigo), ("yellow", .yellow), ("green", .green),
            ("orange", .orange), ("teal", .teal), ("cyan", .cyan),
            ("pink", .pink)
        ]
        for (name, expected) in pairs {
            let entry = makeCatalogEntry(color: name)
            XCTAssertEqual(entry.swiftUIColor, expected, "color=\(name)")
        }
        // Unknown name → accentColor fallback.
        XCTAssertEqual(makeCatalogEntry(color: "fuchsia").swiftUIColor, .accentColor)
    }

    // MARK: - ProviderResponse

    func testProviderResponseDecodesSnakeCase() throws {
        let json = """
        {
            "id": "p-1", "name": "My OpenAI", "provider_type": "openai",
            "api_base": "https://api.openai.com/v1",
            "enabled": true, "sort_order": 5, "has_api_key": true,
            "created_at": "2026-05-10T10:00:00Z"
        }
        """.data(using: .utf8)!
        let resp = try JSONDecoder().decode(ProviderResponse.self, from: json)
        XCTAssertEqual(resp.providerType, "openai")
        XCTAssertEqual(resp.apiBase, "https://api.openai.com/v1")
        XCTAssertTrue(resp.hasApiKey)
        XCTAssertEqual(resp.sortOrder, 5)
    }

    // MARK: - APIKeyStatus

    func testAPIKeyStatusDecodes() throws {
        let json = """
        {
            "provider_type": "ollama",
            "has_api_key": false,
            "is_local": true,
            "keychain_available": true
        }
        """.data(using: .utf8)!
        let status = try JSONDecoder().decode(APIKeyStatus.self, from: json)
        XCTAssertEqual(status.providerType, "ollama")
        XCTAssertTrue(status.isLocal)
        XCTAssertTrue(status.keychainAvailable)
    }

    // MARK: - ModelInfo formatters

    func testFormattedInputCostFree() {
        let model = makeModel(isLocal: false, inputCost: 0)
        XCTAssertEqual(model.formattedInputCost, "Free")
    }

    func testFormattedInputCostLocalIsFree() {
        let model = makeModel(isLocal: true, inputCost: 100)
        XCTAssertEqual(model.formattedInputCost, "Free")
    }

    func testFormattedInputCostBelowOneCent() {
        let model = makeModel(isLocal: false, inputCost: 0.005)
        XCTAssertEqual(model.formattedInputCost, "<$0.01")
    }

    func testFormattedInputCostNormal() {
        let model = makeModel(isLocal: false, inputCost: 2.5)
        XCTAssertEqual(model.formattedInputCost, "$2.50")
    }

    func testFormattedOutputCostMirrors() {
        let model = makeModel(isLocal: false, outputCost: 10)
        XCTAssertEqual(model.formattedOutputCost, "$10.00")
    }

    func testFormattedContextWindow() {
        XCTAssertEqual(makeModel(maxIn: 128_000).formattedContextWindow, "128K")
        XCTAssertEqual(makeModel(maxIn: 1_000_000).formattedContextWindow, "1M")
        XCTAssertEqual(makeModel(maxIn: 500).formattedContextWindow, "500")
        XCTAssertNil(makeModel(maxIn: nil).formattedContextWindow)
        XCTAssertNil(makeModel(maxIn: 0).formattedContextWindow)  // zero guarded
    }

    // MARK: - Capability badges

    func testCapabilityBadgesEmpty() {
        let model = makeModel()  // all caps off
        XCTAssertTrue(model.capabilityBadges.isEmpty)
    }

    func testCapabilityBadgesOrderAndContents() {
        // Order is intentional — visual hierarchy in the model row.
        let model = makeModel(
            vision: true, reasoning: true, functions: true,
            audioIn: true, audioOut: true, pdf: true,
            caching: true, web: true, batch: true
        )
        let labels = model.capabilityBadges.map(\.label)
        XCTAssertEqual(
            labels,
            ["Vision", "Reasoning", "Tools", "Audio In", "Audio Out",
             "PDF", "Caching", "Web", "Batch"]
        )
    }

    func testCapabilityBadgesIcons() {
        let model = makeModel(vision: true, pdf: true)
        let badges = model.capabilityBadges
        XCTAssertEqual(badges.count, 2)
        XCTAssertEqual(badges[0].icon, "eye")
        XCTAssertEqual(badges[1].icon, "doc.text")
    }

    // MARK: - UserModelResponse

    func testUserModelResponseDecodesSnakeCase() throws {
        let json = """
        {
            "id": "um-1", "provider_id": "p-1", "name": "GPT-4o",
            "model_id": "gpt-4o", "capabilities": ["vision", "tools"],
            "is_default": true, "enabled": true,
            "input_cost": 2.5, "output_cost": 10.0
        }
        """.data(using: .utf8)!
        let m = try JSONDecoder().decode(UserModelResponse.self, from: json)
        XCTAssertEqual(m.providerId, "p-1")
        XCTAssertEqual(m.modelId, "gpt-4o")
        XCTAssertTrue(m.isDefault)
        XCTAssertEqual(m.capabilities, ["vision", "tools"])
    }

    // MARK: - ConnectionTestResponse

    func testConnectionTestResponseDecodesSnakeCase() throws {
        let json = """
        {
            "success": true,
            "provider_type": "openai",
            "message": "OK",
            "latency_ms": 245.0,
            "model_tested": "gpt-4o"
        }
        """.data(using: .utf8)!
        let resp = try JSONDecoder().decode(ConnectionTestResponse.self, from: json)
        XCTAssertTrue(resp.success)
        XCTAssertEqual(resp.providerType, "openai")
        XCTAssertEqual(resp.latencyMs, 245.0)
        XCTAssertEqual(resp.modelTested, "gpt-4o")
    }

    // MARK: - ProviderServiceError

    func testProviderServiceErrorDescription() {
        XCTAssertEqual(
            ProviderServiceError.invalidInput("bad").errorDescription,
            "Invalid input: bad"
        )
    }

    // MARK: - Helpers

    private func makeCatalogEntry(color: String) -> ProviderCatalogEntry {
        ProviderCatalogEntry(
            type: "x", name: "X", description: "",
            apiKeyEnv: nil, apiKeyUrl: nil,
            isLocal: false, isBuiltin: false,
            supportsVision: false, supportsEmbeddings: false,
            supportsStreaming: false,
            defaultModel: nil, hasApiKey: false,
            icon: "", logoAsset: nil, color: color, sortOrder: 0
        )
    }

    private func makeModel(
        isLocal: Bool = false,
        inputCost: Double = 0,
        outputCost: Double = 0,
        maxIn: Int? = nil,
        vision: Bool = false,
        reasoning: Bool = false,
        functions: Bool = false,
        audioIn: Bool = false,
        audioOut: Bool = false,
        pdf: Bool = false,
        caching: Bool = false,
        web: Bool = false,
        batch: Bool = false
    ) -> ModelInfo {
        ModelInfo(
            modelId: "m", fullName: "M", description: nil,
            isRecommended: false, isLocal: isLocal,
            inputCostPerMillion: inputCost,
            outputCostPerMillion: outputCost,
            batchInputCostPerMillion: nil,
            batchOutputCostPerMillion: nil,
            cacheReadCostPerMillion: nil,
            maxInputTokens: maxIn, maxOutputTokens: nil,
            mode: nil,
            supportsVision: vision,
            supportsFunctionCalling: functions,
            supportsAudioInput: audioIn,
            supportsAudioOutput: audioOut,
            supportsPdfInput: pdf,
            supportsPromptCaching: caching,
            supportsReasoning: reasoning,
            supportsWebSearch: web,
            supportsStreaming: false,
            supportsBatchApi: batch,
            provider: nil
        )
    }
}
