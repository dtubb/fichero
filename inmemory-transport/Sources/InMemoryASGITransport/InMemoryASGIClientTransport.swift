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
/// event the ASGI app emits is handed to Swift as it arrives (see `AsgiBridge`).
/// Unlike `httpx.ASGITransport`, nothing is buffered.
///
/// Concurrency: request set-up and the response head are done on the shared
/// `PythonWorker`, but the body is drained on a **dedicated thread** that manages
/// the GIL itself (`PyGIL.ensure`/`release` per event). While that thread is
/// parked in the blocking `queue.Queue.get()` the GIL is free, so the worker can
/// service other requests concurrently — a slow SSE stream does not stall unary
/// calls.
public struct InMemoryASGIClientTransport: ClientTransport {

    private let appHandle: ASGIApp
    /// Test-only hook fired when a body-drain thread exits (any reason). Lets
    /// tests observe cancellation without exposing internals publicly.
    private let onDrainEnd: (() -> Void)?

    /// - Parameter app: an ASGI application handle from `ASGIAppLoader`.
    public init(app: ASGIApp) {
        self.appHandle = app
        self.onDrainEnd = nil
    }

    /// Internal initializer with a drain-exit observer, for tests.
    init(app: ASGIApp, onDrainEnd: (() -> Void)?) {
        self.appHandle = app
        self.onDrainEnd = onDrainEnd
    }

    public func send(
        _ request: HTTPRequest,
        body: HTTPBody?,
        baseURL: URL,
        operationID: String
    ) async throws -> (HTTPResponse, HTTPBody?) {
        // 1. Collect the request body (unary requests only). No Python here.
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
        let appHandle = self.appHandle  // ARC copy of a class ref — no Python touch.

        // 2. Build the scope and start the driver thread on the worker (GIL held
        //    by the worker's per-job ensure). Return a GIL-safe handle to the
        //    event queue.
        let queueRef: PyRef = worker.sync {
            let bridge = worker.bridge
            let app = appHandle.ref.value  // dereferenced under the GIL
            let pyHeaders = PythonObject(
                headerPairs.map { PythonObject([PythonObject($0.0), PythonObject($0.1)]) }
            )
            let scope = bridge.make_scope(PythonObject(method), PythonObject(rawPath), pyHeaders)
            let pyBody = Python.bytes(PythonObject(requestBytes))
            return PyRef(bridge.make_driver(app, scope, pyBody))
        }

        // 3. Pull the response head (first queue item) on the worker.
        let head: HeadOrError = worker.sync {
            let item = worker.bridge.q_get(queueRef.value)
            let tag = String(item[0]) ?? ""
            if tag == "error" { return .error(String(item[1]) ?? "unknown ASGI error") }
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
        case .error(let message): throw ASGITransportError.applicationError(message)
        case .head(let s, let h): (status, respHeaders) = (s, h)
        }

        var fields = HTTPFields()
        for (name, value) in respHeaders {
            guard let fieldName = HTTPField.Name(name) else { continue }
            fields.append(HTTPField(name: fieldName, value: value))
        }
        let response = HTTPResponse(status: .init(code: status), headerFields: fields)

        // 4. Drain the body on a dedicated thread that owns its own GIL cycles,
        //    decoupled from the shared worker so it never serializes other work.
        let (stream, continuation) = AsyncThrowingStream<ArraySlice<UInt8>, any Error>.makeStream()
        let control = DrainControl(queueRef: queueRef)

        // WARN-3: if the consumer drops the stream (e.g. cancels an SSE), stop the
        // drain thread promptly instead of leaking it for the life of the stream.
        continuation.onTermination = { _ in control.cancel() }

        let onDrainEnd = self.onDrainEnd
        let drain = Thread {
            defer { onDrainEnd?() }
            while true {
                if control.isCancelled { continuation.finish(); return }

                let event: BodyEvent = {
                    let gil = PyGIL.ensure()
                    defer { PyGIL.release(gil) }
                    // Blocking get(); releases the GIL while it waits, so the
                    // producer (and any concurrent worker request) can run.
                    let item = control.queueRef.value.get()
                    let tag = String(item[0]) ?? ""
                    switch tag {
                    case "body":
                        let bytes = [UInt8](item[1]) ?? []
                        return .chunk(bytes, more: Bool(item[2]) ?? false)
                    case "done": return .done
                    case "error": return .failure(String(item[1]) ?? "unknown ASGI error")
                    case "__cancel__": return .cancelled
                    default: return .failure("unexpected event: \(tag)")
                    }
                }()

                if control.isCancelled { continuation.finish(); return }
                switch event {
                case .chunk(let bytes, let more):
                    if !bytes.isEmpty { continuation.yield(bytes[...]) }
                    if !more { continuation.finish(); return }
                case .done:
                    continuation.finish(); return
                case .cancelled:
                    continuation.finish(); return
                case .failure(let message):
                    continuation.finish(throwing: ASGITransportError.applicationError(message))
                    return
                }
            }
        }
        drain.name = "InMemoryASGITransport.BodyDrain"
        control.thread = drain
        drain.start()

        return (response, HTTPBody(stream, length: .unknown))
    }
}

/// Coordinates cancellation of a body-drain thread. Holds the queue handle so it
/// outlives the drain, and can wake a blocked `get()` by pushing a sentinel.
private final class DrainControl {
    let queueRef: PyRef
    private let lock = NSLock()
    private var cancelled = false
    var thread: Thread?

    init(queueRef: PyRef) { self.queueRef = queueRef }

    var isCancelled: Bool {
        lock.lock(); defer { lock.unlock() }
        return cancelled
    }

    /// Mark cancelled and unblock a drain thread parked in `get()` by pushing a
    /// sentinel onto the Python queue (done under the GIL).
    func cancel() {
        lock.lock()
        let already = cancelled
        cancelled = true
        lock.unlock()
        guard !already else { return }

        let gil = PyGIL.ensure()
        queueRef.value.put(PythonObject("__cancel__"))
        PyGIL.release(gil)
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
    case cancelled
    case failure(String)
}
