#if os(macOS)
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import Testing

@testable import Fichero

/// Tests for the AppleScript bridge helpers and async execution wrapper.
@Suite("AppleScript bridge")
struct AppleScriptBridgeTests {

    @Test("runAsyncWithoutBlocking returns an async value on the main thread")
    @MainActor
    func runAsyncWithoutBlockingReturnsValue() throws {
        let result = try runAsyncWithoutBlocking {
            await "hello"
        }
        #expect(result == "hello")
    }

    @Test("AppleScript inputs round-trip through OpenAPI object container")
    func inputsContainerRoundTrip() throws {
        let inputs: [String: any Sendable] = [
            "query": "find pdf",
            "limit": 5,
            "enabled": true
        ]
        let container = try OpenAPIObjectContainer(
            unvalidatedValue: inputs.mapValues { $0 as (any Sendable)? }
        )
        #expect(container.value["query"] as? String == "find pdf")
        #expect(container.value["limit"] as? Int == 5)
        #expect(container.value["enabled"] as? Bool == true)
    }
}
#endif
