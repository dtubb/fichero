import Foundation
import HTTPTypes
import OpenAPIRuntime
import PythonKit

/// An `OpenAPIRuntime.ClientTransport` that drives a Python ASGI application
/// **in-process** — no subprocess, no socket, no HTTP server. It builds an ASGI
/// `scope` from the outgoing `HTTPRequest`, runs `app(scope, receive, send)` on a
/// background Python thread, and returns the response.
///
/// The response body is a *true* incremental stream: each `http.response.body`
/// event the ASGI app emits is handed to Swift as it arrives (see `AsgiBridge`
/// and `PythonWorker`). This is what makes server-sent-events / chunked responses
/// work — unlike `httpx.ASGITransport`, which buffers the whole response.
public struct InMemoryASGIClientTransport: ClientTransport {

    /// The ASGI application object (e.g. `fichero.api.main:app`). Obtain it on the
    /// `PythonWorker` thread; it is only ever touched there afterwards.
    private let app: PythonObject

    /// - Parameter app: a Python ASGI 3.0 application callable.
    public init(app: PythonObject) {
        self.app = app
    }

    public func send(
        _ request: HTTPRequest,
        body: HTTPBody?,
        baseURL: URL,
        operationID: String
    ) async throws -> (HTTPResponse, HTTPBody?) {
        // 1. Collect the request body (unary requests only; ASGI receive() is
        //    single-shot here). Streaming *uploads* are out of scope.
        var requestBytes: [UInt8] = []
        if let body {
            for try await chunk in body { requestBytes.append(contentsOf: chunk) }
        }

        let method = request.method.rawValue
        let rawPath = request.path ?? "/"
        var headerPairs: [(String, String)] = []
        for field in request.headerFields {
            headerPairs.append((field.name.canonicalName, field.value))
        }

        let worker = PythonWorker.shared
        let app = self.app

        // 2. Build the scope and start the driver thread. Returns the event queue.
        let q: PythonObject = worker.sync {
            let bridge = worker.bridge
            let pyHeaders = PythonObject(headerPairs.map { PythonObject([PythonObject($0.0), PythonObject($0.1)]) })
            let scope = bridge.make_scope(PythonObject(method), PythonObject(rawPath), pyHeaders)
            let pyBody = Python.bytes(PythonObject(requestBytes))
            return bridge.make_driver(app, scope, pyBody)
        }

        // 3. Pull the response head (status + headers). This is the first queue item.
        let head: HeadOrError = worker.sync {
            let item = worker.bridge.q_get(q)
            let tag = String(item[0]) ?? ""
            if tag == "error" {
                return .error(String(item[1]) ?? "unknown ASGI error")
            }
            guard tag == "start", let status = Int(item[1]) else {
                return .error("expected http.response.start, got \(tag)")
            }
            var headers: [(String, String)] = []
            for pair in item[2] {
                if let k = String(pair[0]), let v = String(pair[1]) { headers.append((k, v)) }
            }
            return .head(status: status, headers: headers)
        }

        let (status, respHeaders): (Int, [(String, String)])
        switch head {
        case .error(let message):
            throw ASGITransportError.applicationError(message)
        case .head(let s, let h):
            (status, respHeaders) = (s, h)
        }

        var fields = HTTPFields()
        for (name, value) in respHeaders {
            guard let fieldName = HTTPField.Name(name) else { continue }
            fields.append(HTTPField(name: fieldName, value: value))
        }
        let response = HTTPResponse(status: .init(code: status), headerFields: fields)

        // 4. Stream the body. A dedicated thread pulls one event at a time from the
        //    Python queue (via the worker) and yields each chunk immediately.
        let (stream, continuation) = AsyncThrowingStream<ArraySlice<UInt8>, any Error>.makeStream()
        let thread = Thread {
            while true {
                let event: BodyEvent = worker.sync {
                    let item = worker.bridge.q_get(q)
                    let tag = String(item[0]) ?? ""
                    switch tag {
                    case "body":
                        let bytes = [UInt8](item[1]) ?? []
                        return .chunk(bytes, more: Bool(item[2]) ?? false)
                    case "done":
                        return .done
                    case "error":
                        return .failure(String(item[1]) ?? "unknown ASGI error")
                    default:
                        return .failure("unexpected event: \(tag)")
                    }
                }
                switch event {
                case .chunk(let bytes, let more):
                    if !bytes.isEmpty { continuation.yield(bytes[...]) }
                    // ASGI: the final body event has more_body == false.
                    if !more { continuation.finish(); return }
                case .done:
                    continuation.finish(); return
                case .failure(let message):
                    continuation.finish(throwing: ASGITransportError.applicationError(message))
                    return
                }
            }
        }
        thread.name = "InMemoryASGITransport.BodyDrain"
        thread.start()

        return (response, HTTPBody(stream, length: .unknown))
    }
}

/// Errors surfaced from the in-process ASGI application.
public enum ASGITransportError: Error, CustomStringConvertible {
    case applicationError(String)

    public var description: String {
        switch self {
        case .applicationError(let message): return "ASGI application error: \(message)"
        }
    }
}

private enum HeadOrError {
    case head(status: Int, headers: [(String, String)])
    case error(String)
}

private enum BodyEvent {
    case chunk([UInt8], more: Bool)
    case done
    case failure(String)
}
