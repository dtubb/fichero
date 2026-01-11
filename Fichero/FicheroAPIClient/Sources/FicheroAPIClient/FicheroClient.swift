import Foundation
import OpenAPIRuntime
import OpenAPIURLSession

/// Convenience wrapper for the generated Fichero API client.
///
/// Usage:
/// ```swift
/// let fichero = FicheroClient(baseURL: URL(string: "http://localhost:8765")!)
///
/// // List workflows
/// let response = try await fichero.api.listWorkflows()
/// let workflows = try response.ok.body.json
///
/// // Create a workflow
/// let createResponse = try await fichero.api.createWorkflow(
///     body: .json(.init(name: "My Workflow"))
/// )
/// ```
public struct FicheroClient {
    /// The generated API client
    public let api: Client

    /// The base URL of the API server
    public let baseURL: URL

    /// Creates a new Fichero API client.
    /// - Parameters:
    ///   - baseURL: The base URL of the Fichero backend (e.g., http://localhost:8765)
    ///   - libraryPath: Optional library path header value
    public init(baseURL: URL, libraryPath: String? = nil) {
        self.baseURL = baseURL

        // The API paths in OpenAPI include /api prefix
        let serverURL = baseURL.appendingPathComponent("api")

        self.api = Client(
            serverURL: serverURL,
            transport: URLSessionTransport()
        )
    }

    /// Default client pointing to localhost:8765
    public static var localhost: FicheroClient {
        FicheroClient(baseURL: URL(string: "http://localhost:8765")!)
    }
}

// MARK: - Re-export types for convenience

// These will be available once the generator runs
// public typealias Workflow = Components.Schemas.Workflow
// public typealias Document = Components.Schemas.Document
