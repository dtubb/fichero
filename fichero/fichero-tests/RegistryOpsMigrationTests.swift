//
//  RegistryOpsMigrationTests.swift
//  FicheroTests
//
//  #3030 — the global-registry add/remove calls (FileMenuCommands,
//  LibraryManager+Operations) migrated off the hand-rolled APIClient
//  post/delete onto the generated `add_known_library` / `remove_known_library`
//  operations. These lock the request contract the callers now depend on:
//  add carries path+name as query params, and remove percent-encodes the
//  filesystem path into a SINGLE URL segment (so the `{library_path}` route
//  matches and the backend decodes it back to the raw path). The single-segment
//  encoding is what the old client did by hand — regressing it 404s the delete.
//  Reuses `MockURLProtocol` from StorageServiceGeneratedTests (same target).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct RegistryOpsMigrationTests {

    private func makeClient(
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> FicheroClient {
        MockURLProtocol.requestHandler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        return FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: nil,
            session: session
        )
    }

    @Test("add_known_library POSTs to /api/registry/add with path + name query params")
    func addCarriesQueryParams() async throws {
        let client = makeClient { request in
            #expect(request.httpMethod == "POST")
            #expect(request.url?.path == "/api/registry/add")
            let query = request.url?.query ?? ""
            #expect(query.contains("path="))
            #expect(query.contains("name="))
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data("{\"path\":\"/tmp/lib.fichero\"}".utf8))
        }

        let response = try await client.api.addKnownLibraryApiRegistryAddPost(
            query: .init(path: "/tmp/lib.fichero", name: "Lib")
        )
        if case .ok = response {} else {
            Issue.record("expected .ok")
        }
    }

    @Test("remove_known_library encodes the filesystem path into one URL segment")
    func removeEncodesPathAsSingleSegment() async throws {
        let client = makeClient { request in
            #expect(request.httpMethod == "DELETE")
            // The library path's slashes MUST be percent-encoded (%2F) so the
            // whole path is a single `{library_path}` segment. If they leaked
            // through as literal '/', the route would not match server-side.
            let absolute = request.url?.absoluteString ?? ""
            #expect(absolute.contains("/api/registry/"))
            #expect(absolute.contains("%2FUsers%2F"))
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data("{}".utf8))
        }

        let response = try await client.api.removeKnownLibraryApiRegistryLibraryPathDelete(
            path: .init(libraryPath: "/Users/x/lib.fichero")
        )
        if case .ok = response {} else {
            Issue.record("expected .ok")
        }
    }
}
