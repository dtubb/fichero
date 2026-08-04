import Foundation
import HTTPTypes
import OpenAPIRuntime

// MARK: - The test-host dial chokepoint (#4511)

/// Why this file exists.
///
/// No Swift unit test executed in this repo for weeks. `build-for-testing`
/// compiled, printed `TEST BUILD SUCCEEDED`, and the run phase never produced a
/// result — every "Swift tests green" meant *compiles*. The cause was not one
/// call: touching `LibraryManager.shared` runs its singleton `init()`, which
/// loads the global library, which dials `GET /api/documents/roots`; and the
/// same first touch fans out to `/api/registry`, `/api/search/saved`,
/// `/api/chains` and `/api/workflows/tools`. With no engine listening, each of
/// those sits on its transport deadline, and the host wedges before the first
/// assertion runs.
///
/// A per-call guard was tried and was not enough — there were five call sites,
/// and the sixth one added later would reintroduce the hang. All five (and any
/// future dial) pass through exactly ONE place: `FicheroClient.makeTransport`.
/// That is the chokepoint, so the guard lives there and nowhere else.
///
/// The rule is deliberately narrow:
///
/// * Under a test host (`XCTestConfigurationFilePath` / `XCTestBundlePath`),
///   a transport that would reach a REAL engine — the default URLSession, an
///   AF_UNIX socket, in-process CPython — is replaced by ``FailFastTransport``.
/// * An **explicitly injected** `URLSession` is honoured unchanged. That
///   session is the test's own stub (a `URLProtocol` mock, a pinning probe); it
///   never reaches an engine, and swapping it out would silently defeat the
///   test that installed it.
/// * `FicheroClient.liveTransport` still builds the real thing, so the
///   transport-selection tests can keep asserting which concrete transport a
///   mode chooses.
enum TestHostTransportGuard {
    /// True inside an XCTest / Swift Testing **host** process.
    ///
    /// Cached: the answer cannot change mid-process, and this sits on the
    /// launch path.
    ///
    /// Deliberately NOT keyed on `XCTestSessionIdentifier`. XCUITest injects
    /// that into the APP UNDER TEST, so keying on it would gut the transport of
    /// the very app a UI test is driving — the UI suite would then exercise a
    /// fail-fast stub instead of the product. The two markers below are set
    /// only for the process that hosts the tests themselves. This mirrors the
    /// same reasoning in `EngineConfig.isRunningUnderTests`; the two live in
    /// different modules (app vs. API-client package), so neither can import
    /// the other's copy.
    static let isTestHost: Bool = {
        let environment = ProcessInfo.processInfo.environment
        return environment["XCTestConfigurationFilePath"] != nil
            || environment["XCTestBundlePath"] != nil
    }()
}

/// The typed failure a test-host engine dial produces (#4511).
///
/// It is an error, not a canned empty 200: a silent success would make every
/// store under test read as "the engine answered with nothing", which is the
/// silent-fallback failure mode this project bans. A test that genuinely needs
/// engine data must inject its own session or stub the service — and this error
/// says so in as many words, because the alternative is a developer staring at
/// a decode failure.
public struct EngineDialRefusedUnderTest: Error, LocalizedError, Equatable {
    /// The generated operation that tried to dial (e.g.
    /// `listDocumentRootsApiDocumentsRootsGet`). Named so the log points at the
    /// call site rather than at this file.
    public let operationID: String

    public init(operationID: String) {
        self.operationID = operationID
    }

    public var errorDescription: String? {
        """
        Engine dial refused under the test host (#4511): '\(operationID)'.
        The test process must not reach a live engine — inject a URLSession \
        stub or exercise the service seam directly.
        """
    }
}

/// A `ClientTransport` that never opens a connection: it throws
/// ``EngineDialRefusedUnderTest`` immediately.
///
/// "Immediately" is the whole point. The bug was not that tests talked to an
/// engine; it was that they *waited* for one that would never answer, for the
/// length of the transport deadline, at launch, before any test ran.
struct FailFastTransport: ClientTransport {
    func send(
        _ request: HTTPRequest,
        body: HTTPBody?,
        baseURL: URL,
        operationID: String
    ) async throws -> (HTTPResponse, HTTPBody?) {
        throw EngineDialRefusedUnderTest(operationID: operationID)
    }
}
