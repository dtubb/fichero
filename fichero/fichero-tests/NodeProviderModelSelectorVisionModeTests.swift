@testable import Fichero
import Foundation
import XCTest

final class NodeProviderModelSelectorVisionModeTests: XCTestCase {

    func testAllRuntimeModelAliasesAreRecognized() {
        for providerId in ["$small", "$large", "$vision_small", "$vision_medium", "$vision_large"] {
            XCTAssertTrue(isModelAliasProviderId(providerId), providerId)
        }
        XCTAssertFalse(isModelAliasProviderId("openai"))
    }

    private static func source() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent("Views/Workflow/Nodes/NodeProviderModelSelector.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testLeavingAppleVisionClearsVisionModeForDefaultAndAliases() throws {
        let source = try Self.source()
        let clear = "node.config?.removeValue(forKey: \"vision_mode\")"
        let defaultRange = try XCTUnwrap(source.range(of: "if newValue.isEmpty"))
        let defaultExit = try XCTUnwrap(source.range(of: "return", range: defaultRange.lowerBound..<source.endIndex))
        let aliasRange = try XCTUnwrap(source.range(of: "isModelAliasProviderId(newValue)"))
        let llmRange = try XCTUnwrap(source.range(of: "// LLM provider selected"))

        XCTAssertNotNil(source.range(of: clear, range: defaultRange.lowerBound..<defaultExit.upperBound))
        XCTAssertNotNil(source.range(of: clear, range: aliasRange.lowerBound..<llmRange.lowerBound))
    }
}
