import FicheroAPIClient
@testable import Fichero
import Foundation
import Testing

/// The TCP port pre-flight must not run for an engine that binds no TCP port
/// (#4400).
///
/// The pre-flight predates UDS. A shipping `.releaseEmbedded` engine binds a
/// UNIX-domain socket in the app container — the engine logs "no TCP port, no
/// TLS" — so port 8765 belongs to somebody else entirely. Probing it anyway was
/// not a harmless extra check; it was the dead end:
///
///   1. Anything at all holding 8765 raised "Port 8765 Is In Use".
///   2. The only non-destructive answer, "Use the Existing Server", adopted
///      that process AND skipped `launchEmbeddedBackend()`.
///   3. The client then dialled the UDS socket, which nobody was serving,
///      and timed out after 30 seconds.
///   4. `pendingPortConflictResolution` had been consumed, so the same prompt
///      returned, and the loop repeated.
///
/// On App Store builds the sandbox makes the holder PID unknowable, so "Stop
/// it" is dropped and the user is offered only Use it / Quit — meaning Quit was
/// the only escape. That is the shape #4421's standing rule rejects: an
/// affordance that cannot succeed.
struct PortPreflightTransportTests {

    /// The rule, stated as the question it answers: is 8765 ours?
    @Test("only an HTTPS engine owns the TCP port")
    func onlyHTTPSOwnsThePort() {
        #expect(EmbeddedBackendService.portPreflightApplies(transportMode: .https))
        #expect(!EmbeddedBackendService.portPreflightApplies(transportMode: .uds(path: "/tmp/fichero.sock")))
        #if os(macOS)
        #expect(!EmbeddedBackendService.portPreflightApplies(transportMode: .inMemory))
        #endif
    }

    /// The socket path is irrelevant to the decision — it is the TRANSPORT that
    /// decides, not which socket. Pinned because a path-sensitive answer would
    /// pass the case above and still re-open the dead end for the container
    /// socket a shipping build actually uses.
    @Test("no UDS path makes the port ours again")
    func noSocketPathReopensThePreflight() {
        let paths = [
            "/tmp/fichero.sock",
            EngineConfig.udsSocketPath,
            ""
        ]
        for path in paths {
            #expect(!EmbeddedBackendService.portPreflightApplies(transportMode: .uds(path: path)))
        }
    }

    /// The shipping configuration, tied to the strategy that produces it. This
    /// is the assertion that would have caught the bug: `.releaseEmbedded` is
    /// what a Release macOS build with no configured host resolves to, and it
    /// is precisely the strategy that ran the pre-flight.
    @Test("the shipping strategy resolves to a transport the pre-flight skips")
    func theShippingStrategySkipsThePreflight() {
        let shipping = EngineConfig.transportMode(for: .releaseEmbedded)

        #expect(shipping == .uds(path: EngineConfig.udsSocketPath))
        #expect(!EmbeddedBackendService.portPreflightApplies(transportMode: shipping))
    }

    /// The pre-flight is skipped, not deleted. `.debugExternal` and the remote
    /// strategies still dial HTTPS, and a genuine TCP conflict there is still
    /// the user's to resolve — the fix narrows the question to where it is
    /// meaningful rather than removing a fail-closed path.
    @Test("the HTTPS strategies keep their port pre-flight")
    func httpsStrategiesKeepThePreflight() {
        for strategy in [
            EngineConfig.EngineProvisioningStrategy.debugExternal,
            .configuredRemote,
            .iosCompanion,
            .inert
        ] {
            let mode = EngineConfig.transportMode(for: strategy)
            #expect(mode == .https)
            #expect(EmbeddedBackendService.portPreflightApplies(transportMode: mode))
        }
    }

    /// The orphan sweep must NOT be gated on the same condition. An engine this
    /// app spawned in a previous session is ours to reap whichever transport it
    /// was reached over, and reaping it is what frees a stale socket before we
    /// bind — the other half of #4400. Asserted against the source because the
    /// sweep shells out to pgrep/kill and cannot run in a test.
    @Test("the orphan sweep still runs on every transport")
    func theOrphanSweepIsNotGated() throws {
        let source = try AppSource.text("Services/EmbeddedBackendService+Ports.swift")

        // Scope to the non-App-Store half of `resolvePortConflict`, because the
        // sandboxed half legitimately guards FIRST — it has no sweep to protect.
        // Comparing raw offsets across the whole file would compare the sweep
        // against the MAS branch's guard and read as ordered when it is not.
        let body = try #require(source.range(of: "func resolvePortConflict()"))
        let nonAppStore = try #require(
            source.range(of: "#else", range: body.upperBound..<source.endIndex)
        )
        let branch = source[nonAppStore.upperBound...]

        let sweep = try #require(branch.range(of: "Self.terminateOrphanEngines()"))
        let guardClause = try #require(branch.range(of: "guard Self.portPreflightApplies"))

        // The sweep has to come FIRST. Behind the guard it would stop reaping
        // our own orphans on exactly the path that ships, and a stale socket
        // would survive into the next launch — the other half of #4400.
        #expect(sweep.upperBound < guardClause.lowerBound)
    }
}
