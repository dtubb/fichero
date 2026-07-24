#if os(macOS)
import XCTest
import OpenAPIRuntime
import OpenAPIAsyncHTTPClient
@testable import FicheroAPIClient

/// Transport-routing coverage for the KG web pane (#4066).
///
/// `EngineWebViewSchemeHandler` funnels every `fichero-engine://` navigation +
/// relative subresource through `FicheroClient.requestData(...)` — the SAME
/// transport-agnostic fetch path the generated `Client` uses. Because
/// `requestData` dials the client's `ClientTransport`, the pane works over
/// `.uds` (AF_UNIX socket, NO HTTP listener) and `.inMemory` (in-process ASGI
/// via PythonKit, NO socket at all) — the two transports where a raw
/// `URLSession` to `https://127.0.0.1:8765` used to fail `-1004` and leave the
/// pane blank (#4066).
///
/// These tests exercise the handler's EXACT fetch path (`requestData`) over
/// each non-HTTP transport, so a regression that reverts the pane to a raw
/// engine URL fails here. The in-process round-trip boots the real Fichero
/// engine via PythonKit (the "python-kit option" Daniel asked about) and
/// skips when the toolchain isn't discoverable, mirroring
/// `InMemoryTransportSmokeTests`.
///
/// NOTE: constructing ANY `.inMemory` client boots CPython once per process
/// (a fatal `try!` in PythonKit, not a catchable throw), so the `.inMemory`
/// tests MUST call `configureInProcessEngineEnvOrSkip()` before building the
/// client — otherwise a box with a broken native `pydantic_core` extension
/// would crash the whole test process. The UDS tests never touch PythonKit.
@MainActor
final class EngineWebViewRoutingTests: XCTestCase {

    // MARK: - UDS (AF_UNIX socket, no HTTP listener)

    /// The KG handler rides `FicheroClient.requestData`. A client provisioned
    /// for `.uds` MUST dial an `AsyncHTTPClientTransport` pointed at an
    /// `http+unix://` server URL (the AF_UNIX socket) — NOT a URLSession that
    /// would hit `https://127.0.0.1:8765` (the HTTP listener that doesn't exist
    /// over UDS). This is the "no HTTP listener" half of #4066 for UDS. No
    /// CPython boot, no network — pure transport-selection assertions.
    func testKGHandlerClientDialsUnixSocketNotHTTPListener() {
        let socket = "/tmp/fichero-kg-pane-routing-test.sock"
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            transportMode: .uds(path: socket)
        )

        XCTAssertEqual(client.transportMode, .uds(path: socket))
        XCTAssertTrue(
            client.transport is AsyncHTTPClientTransport,
            "The KG pane's UDS client must dial AsyncHTTPClient (the AF_UNIX socket), "
                + "not URLSession — a URLSession would try the absent HTTP listener"
        )

        // The server URL the handler's `requestData` appends `/api/...` onto is
        // `http+unix://<socket>`, never `https://127.0.0.1:8765`. There is no HTTP
        // listener for a raw URLSession to reach — the pane MUST go through this.
        let serverURL = FicheroClient.makeServerURL(
            baseURL: client.baseURL,
            transportMode: client.transportMode
        )
        XCTAssertEqual(serverURL.scheme, "http+unix")
        XCTAssertFalse(
            serverURL.absoluteString.contains("127.0.0.1"),
            "UDS server URL must not reference the 127.0.0.1 HTTP listener"
        )
    }

    // MARK: - In-memory (python-kit option: in-process ASGI, no socket)
    //
    // Grouped last because constructing a `.inMemory` client boots CPython once
    // per process (fatal on failure). `configureInProcessEngineEnvOrSkip()`
    // runs BEFORE the client is built so a missing toolchain skips cleanly.

    /// End-to-end over the in-memory load: drive the handler's EXACT fetch path
    /// — `client.requestData(path:)` — through a `.inMemory` `FicheroClient` and
    /// assert the engine answers 200. This is the round-trip Daniel asked about
    /// ("has it tested with the in-memory load as well e.g. via the python-kit
    /// option"). `requestData` is the same method `EngineWebViewSchemeHandler`
    /// calls for every `fichero-engine://` navigation + subresource, so a 200
    /// here proves the KG pane reaches the engine over the in-memory transport
    /// with no socket and no HTTP listener. Also pins the transport TYPE so a
    /// regression that swaps `.inMemory` back to URLSession fails loudly.
    /// Skips when the Python toolchain / engine checkout can't be located
    /// (same rule as `InMemoryTransportSmokeTests`).
    func testKGHandlerFetchPathRoundTripsOverInMemoryTransport() async throws {
        try Self.configureInProcessEngineEnvOrSkip()

        let client = FicheroClient(transportMode: .inMemory)
        XCTAssertEqual(client.transportMode, .inMemory)
        XCTAssertTrue(
            client.transport is InMemoryASGIClientTransport,
            "The KG pane's in-memory client must dial InMemoryASGIClientTransport "
                + "(the python-kit / in-process load), not URLSession"
        )

        // The exact call the scheme handler makes for a KG page load. `/api/health`
        // is the lightest read the engine serves; it needs no library scoping, so
        // a 200 isolates "the transport round-trips" from library/auth concerns.
        let (status, data) = try await client.requestData(path: "/api/health")

        XCTAssertEqual(status, 200, "in-memory requestData must reach the engine")
        let body = String(decoding: data, as: UTF8.self)
        XCTAssertTrue(
            body.contains("\"status\":\"healthy\""),
            "in-memory /api/health via requestData should report healthy; got: \(body)"
        )
    }

    // MARK: - In-process engine environment discovery
    //
    // Mirrors `InMemoryTransportSmokeTests` so the python-kit round-trip skips
    // cleanly on a box without the toolchain instead of crashing. CPython boots
    // once per process; keep this test grouped with the smoke suite at run time.

    private static func configureInProcessEngineEnvOrSkip() throws {
        guard let repo = repoRoot() else {
            throw XCTSkip("No Fichero checkout with .venv + fichero-engine found; "
                + "in-process engine unavailable.")
        }
        let fm = FileManager.default

        let engineSrc = repo.appendingPathComponent("fichero-engine/src")
        guard fm.fileExists(atPath: engineSrc.appendingPathComponent("fichero/api/main.py").path) else {
            throw XCTSkip("Engine source not found at \(engineSrc.path); cannot import fichero.api.main.")
        }
        setenvIfUnset("FICHERO_ENGINE_SRC", engineSrc.path)

        guard let sitePackages = discoverSitePackages(venvRoot: repo.appendingPathComponent(".venv")) else {
            throw XCTSkip("No .venv site-packages under \(repo.path)/.venv; engine deps unavailable.")
        }
        setenvIfUnset("FICHERO_VENV_SITE_PACKAGES", sitePackages)

        guard let libpython = discoverLibpython(venvRoot: repo.appendingPathComponent(".venv")) else {
            throw XCTSkip("Could not resolve libpython from the venv; PythonKit cannot boot CPython.")
        }
        setenvIfUnset("PYTHON_LIBRARY", libpython)
    }

    private static func setenvIfUnset(_ key: String, _ value: String) {
        if let existing = ProcessInfo.processInfo.environment[key], !existing.isEmpty { return }
        setenv(key, value, 0)
    }

    private static func discoverSitePackages(venvRoot: URL) -> String? {
        let libDir = venvRoot.appendingPathComponent("lib")
        guard let entries = try? FileManager.default.contentsOfDirectory(atPath: libDir.path) else { return nil }
        for name in entries.sorted() where name.hasPrefix("python3") {
            let candidate = libDir.appendingPathComponent(name).appendingPathComponent("site-packages")
            if FileManager.default.fileExists(atPath: candidate.path) { return candidate.path }
        }
        return nil
    }

    private static func discoverLibpython(venvRoot: URL) -> String? {
        let python = venvRoot.appendingPathComponent("bin/python")
        guard FileManager.default.fileExists(atPath: python.path) else { return nil }
        let process = Process()
        process.executableURL = python
        process.arguments = ["-c",
            "import sysconfig,os;"
            + "p=sysconfig.get_config_var('PYTHONFRAMEWORKPREFIX');"
            + "fw=sysconfig.get_config_var('PYTHONFRAMEWORK');"
            + "v=sysconfig.get_config_var('py_version_short');"
            + "print(os.path.join(p, fw+'.framework','Versions',v,fw) if p and fw else '')"
        ]
        let out = Pipe()
        process.standardOutput = out
        process.standardError = Pipe()
        guard (try? process.run()) != nil else { return nil }
        process.waitUntilExit()
        let data = out.fileHandleForReading.readDataToEndOfFile()
        let path = String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
        return (!path.isEmpty && FileManager.default.fileExists(atPath: path)) ? path : nil
    }

    private static func repoRoot() -> URL? {
        let fm = FileManager.default
        func looksLikeRepo(_ url: URL) -> Bool {
            fm.fileExists(atPath: url.appendingPathComponent(".venv/bin/python").path)
                && fm.fileExists(atPath: url.appendingPathComponent("fichero-engine/src").path)
        }
        if let env = ProcessInfo.processInfo.environment["FICHERO_REPO_ROOT"], !env.isEmpty {
            let url = URL(fileURLWithPath: env)
            if looksLikeRepo(url) { return url }
        }
        var dir = URL(fileURLWithPath: #filePath)
        for _ in 0..<12 {
            if looksLikeRepo(dir) { return dir }
            dir = dir.deletingLastPathComponent()
        }
        let fallback = fm.homeDirectoryForCurrentUser.appendingPathComponent("code/fichero")
        return looksLikeRepo(fallback) ? fallback : nil
    }
}
#endif