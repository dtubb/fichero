//
//  ActivityMockTransport.swift
//  FicheroTests
//
//  The stubbed transport the Activity store tests share (copied before from ActivityTableTests' pattern; shared by
//  ActivityDetailsTests and ActivityQueuedItemsTests since #6101, which split the first by its length limit).
//

import Foundation

struct ActivityStubbedResponse {
    let pathSuffix: String
    let method: String
    let status: Int
    let body: Data
}

final class ActivityMockTransport: URLProtocol {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var stubs: [ActivityStubbedResponse] = []
    nonisolated(unsafe) private static var requests: [URLRequest] = []

    static func reset(_ stubs: [ActivityStubbedResponse]) {
        lock.lock()
        self.stubs = stubs
        requests = []
        lock.unlock()
    }

    static func recorded() -> [URLRequest] {
        lock.lock()
        defer { lock.unlock() }
        return requests
    }

    // swiftlint:disable:next static_over_final_class
    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.host == "127.0.0.1" && request.url?.path.hasPrefix("/api/") == true
    }

    // swiftlint:disable:next static_over_final_class
    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        let path = request.url?.path ?? ""
        let method = request.httpMethod ?? ""
        Self.lock.lock()
        Self.requests.append(request)
        let stub = Self.stubs.first { path.hasSuffix($0.pathSuffix) && $0.method == method }
        Self.lock.unlock()

        let resolved = stub ?? ActivityStubbedResponse(pathSuffix: "", method: "", status: 404, body: Data(#"{"detail":"no stub"}"#.utf8))
        guard let url = request.url,
              let response = HTTPURLResponse(
                  url: url, statusCode: resolved.status, httpVersion: "HTTP/1.1",
                  headerFields: ["Content-Type": "application/json"]
              ) else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: resolved.body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
