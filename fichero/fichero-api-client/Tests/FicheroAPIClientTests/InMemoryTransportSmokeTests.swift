#if os(macOS)
import XCTest
import Foundation
import OpenAPIRuntime
import HTTPTypes
@testable import FicheroAPIClient

/// Proves the `.inMemory` transport actually round-trips: it boots the real
/// Fichero engine **in-process** via PythonKit (no subprocess, no socket, no
/// network) and issues a lightweight read (`/api/health`) through both the raw
/// `InMemoryASGIClientTransport` and the full `FicheroClient(transportMode:
/// .inMemory)` path (generated `Client` + middlewares + the `inmemory`
/// owner-auth marker).
///
/// This is the headless-test enabler for the whole service-integration mandate:
/// unlike the app's XCTest bundle (which needs `xcodebuild`), this runs under
/// plain `swift test`.
///
/// ## Environment it needs (auto-configured when discoverable, else skipped)
/// The in-process interpreter needs three things, which this test locates from
/// the repo checkout and exports (only if unset — a real export always wins):
///   - `PYTHON_LIBRARY`          → the CPython framework binary (from the venv's
///                                 own `sysconfig`, so it is machine-agnostic).
///   - `FICHERO_ENGINE_SRC`      → `<repo>/fichero-engine/src`.
///   - `FICHERO_VENV_SITE_PACKAGES` → `<repo>/.venv/lib/python3.*/site-packages`.
/// If any cannot be located (no `.venv`, no engine, CI without the Python
/// toolchain), the test `XCTSkip`s with an explanation rather than failing —
/// so a box that lacks the embedded engine stays green.
///
/// NOTE: CPython boots ONCE per process and cannot be torn down, so this whole
/// suite must run in a test process that does no *other* PythonKit work.
@MainActor
final class InMemoryTransportSmokeTests: XCTestCase {

    override func setUp() async throws {
        try Self.configureInProcessEngineEnvOrSkip()
    }

    /// Raw-transport round-trip: build the ASGI request by hand and drain the
    /// response. Proves the `AsgiBridge`/`PythonWorker`/GIL machinery end-to-end.
    func testRawTransportHealthRoundTrip() async throws {
        let transport = InMemoryASGIClientTransport(app: InMemoryEngineApp.shared())
        var request = HTTPRequest(method: .get, scheme: nil, authority: nil, path: "/api/health")
        request.headerFields[.accept] = "application/json"

        let (response, body) = try await transport.send(
            request, body: nil,
            baseURL: URL(string: "http://asgi.local")!,
            operationID: "smokeHealth"
        )

        XCTAssertEqual(response.status.code, 200, "in-process /api/health must return 200")
        var bytes: [UInt8] = []
        if let body { for try await chunk in body { bytes.append(contentsOf: chunk) } }
        let text = String(decoding: bytes, as: UTF8.self)
        XCTAssertTrue(text.contains("\"status\":\"healthy\""),
                      "health body should report healthy; got: \(text)")
    }

    /// Full-client round-trip: goes through the generated `Client`, the auth +
    /// library-path middlewares, and the `inmemory` transport marker that grants
    /// loopback-owner access — i.e. the exact path production and future service
    /// tests use.
    func testFullClientHealthRoundTrip() async throws {
        let client = FicheroClient(transportMode: .inMemory)
        let response = try await client.api.healthCheckApiHealthGet(.init())
        switch response {
        case .ok(let ok):
            let json = try ok.body.json
            XCTAssertEqual(json.status, "healthy",
                           "full-client in-process /api/health must report healthy")
        default:
            XCTFail("unexpected /api/health response over .inMemory: \(response)")
        }
    }

    // MARK: - Environment discovery

    /// Locate the repo checkout, derive the three env vars the in-process engine
    /// needs, and export any that are unset. Throws `XCTSkip` if the toolchain or
    /// engine cannot be found so the suite is a no-op on machines without them.
    private static func configureInProcessEngineEnvOrSkip() throws {
        guard let repo = repoRoot() else {
            throw XCTSkip("No Fichero checkout with .venv + fichero-engine found; "
                + "in-process engine unavailable.")
        }
        let fileManager = FileManager.default

        // FICHERO_ENGINE_SRC
        let engineSrc = repo.appendingPathComponent("fichero-engine/src")
        guard fileManager.fileExists(atPath: engineSrc.appendingPathComponent("fichero/api/main.py").path) else {
            throw XCTSkip("Engine source not found at \(engineSrc.path); cannot import fichero.api.main.")
        }
        setenvIfUnset("FICHERO_ENGINE_SRC", engineSrc.path)

        // FICHERO_VENV_SITE_PACKAGES (tolerant of the exact python3.* minor)
        guard let sitePackages = discoverSitePackages(venvRoot: repo.appendingPathComponent(".venv")) else {
            throw XCTSkip("No .venv site-packages under \(repo.path)/.venv; engine deps unavailable.")
        }
        setenvIfUnset("FICHERO_VENV_SITE_PACKAGES", sitePackages)

        // PYTHON_LIBRARY (ask the venv python for the definitive framework binary).
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

    /// Run the venv's own python to resolve the CPython framework binary path —
    /// machine-agnostic (works for any Homebrew/pyenv/framework layout).
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

    /// Walk up from this source file (always inside the repo) looking for a dir
    /// that contains both `.venv/bin/python` and `fichero-engine`. Honors
    /// `FICHERO_REPO_ROOT` when set.
    private static func repoRoot() -> URL? {
        let fileManager = FileManager.default
        func looksLikeRepo(_ url: URL) -> Bool {
            fileManager.fileExists(atPath: url.appendingPathComponent(".venv/bin/python").path)
                && fileManager.fileExists(atPath: url.appendingPathComponent("fichero-engine/src").path)
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
        // Last resort: the conventional local checkout.
        let fallback = fileManager.homeDirectoryForCurrentUser.appendingPathComponent("code/fichero")
        return looksLikeRepo(fallback) ? fallback : nil
    }
}
#endif
