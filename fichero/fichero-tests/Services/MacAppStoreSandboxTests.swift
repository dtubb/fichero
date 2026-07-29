//
//  MacAppStoreSandboxTests.swift
//  FicheroTests
//
//  The App Store build is sandboxed (#3749). Two things it may not do that the
//  DMG build does freely: keep the nested engine under Contents/Resources (an
//  invalid bundle structure at MAS ingestion), and discover the holder of :8765
//  by shelling out to lsof (the sandbox permits no view of other processes).
//
//  These cover the halves that are testable without a signed bundle: the engine
//  lookup ORDER, and the loopback port probe that replaces lsof. The signing
//  itself is asserted by the build phase, which fails the build if the engine
//  comes out without com.apple.security.inherit.
//
//  NOTE: this suite compiles into the DMG test target, where FICHERO_APP_STORE
//  is NOT defined — so it tests the code paths that are shared by both channels.
//  portIsAcceptingConnections() is deliberately compiled into BOTH builds for
//  exactly that reason: the sandbox-safe path must stay exercised by the suite.
//

@testable import Fichero
import Foundation
import Testing

@Suite("Mac App Store sandbox (#3749)")
@MainActor
struct MacAppStoreSandboxTests {

    // MARK: - Nested engine placement

    @Test("engine is looked for in Contents/Helpers BEFORE Contents/Resources")
    func helpersIsPreferredOverResources() {
        let paths = EmbeddedBackendService.engineBundleSubpaths
        let helpers = paths.firstIndex { $0.hasPrefix("Contents/Helpers/") }
        let resources = paths.firstIndex { $0.hasPrefix("Contents/Resources/") }

        #expect(helpers != nil, "the App Store build embeds the engine in Contents/Helpers")
        #expect(resources != nil, "the DMG build still embeds the engine in Contents/Resources")

        // Order is the point, not mere membership. If a build somehow shipped the
        // engine in BOTH places, the sandbox-legal one must win — otherwise a MAS
        // bundle could launch the copy sitting in an invalid location.
        #expect(helpers! < resources!, "Contents/Helpers must be probed first")
    }

    @Test("every candidate is a designated code location — never bare Resources")
    func candidatesAreDesignatedCodeLocations() {
        // TN2206: nested executable code lives in MacOS / Frameworks / Helpers /
        // PlugIns / XPCServices / Library. Contents/Resources is not a designated
        // code location; it survives notarization but is an invalid bundle
        // structure at App Store ingestion. Resources stays in the list ONLY as
        // the DMG fallback, so the assertion is about what we PREFER, not a ban.
        let paths = EmbeddedBackendService.engineBundleSubpaths
        #expect(paths.first == "Contents/Helpers/Fichero Engine.app")
        #expect(paths.allSatisfy { $0.hasSuffix("/Fichero Engine.app") })
    }

    // MARK: - Sandbox-safe port probe (the lsof replacement)

    @Test("no listener → port reports free")
    func closedPortIsNotAccepting() throws {
        // Bind and immediately release a port: nothing is listening on it now, so
        // the probe must say free. (Taking it first makes the number one we know
        // is otherwise unused, instead of guessing a constant that CI might hold.)
        let port = try Self.withEphemeralListener { port, _ in port }
        #expect(EmbeddedBackendService.portIsAcceptingConnections(port) == false)
    }

    @Test("live listener → port reports in use, without lsof or a PID")
    func openPortIsAccepting() throws {
        try Self.withEphemeralListener { port, _ in
            // The whole contract: it answers "is this taken?" and nothing else.
            // No process enumeration, no PID — a sandboxed app has no business
            // knowing who the holder is, and could not signal them anyway.
            #expect(EmbeddedBackendService.portIsAcceptingConnections(port) == true)
        }
    }

    @Test("probe is repeatable — it never leaks the descriptors it opens")
    func probeIsRepeatable() throws {
        // A leaked fd per call would exhaust the process's descriptor table on a
        // retry loop (the connection view retries on a timer). 200 probes against
        // a closed port must all answer the same, and a live one must still work
        // afterwards — which it cannot if the descriptors were never released.
        let port = try Self.withEphemeralListener { port, _ in port }
        for _ in 0..<200 {
            #expect(EmbeddedBackendService.portIsAcceptingConnections(port) == false)
        }
        try Self.withEphemeralListener { livePort, _ in
            #expect(EmbeddedBackendService.portIsAcceptingConnections(livePort) == true)
        }
    }

    // MARK: - Helpers

    /// Bind + listen on an OS-assigned loopback port, hand it to `body`, then
    /// close. Returns whatever `body` returns.
    @discardableResult
    private static func withEphemeralListener<T>(
        _ body: (UInt16, Int32) throws -> T
    ) throws -> T {
        let sock = socket(AF_INET, SOCK_STREAM, 0)
        try #require(sock >= 0)
        defer { close(sock) }

        var yes: Int32 = 1
        setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))

        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = 0  // let the OS pick a free port
        addr.sin_addr.s_addr = inet_addr("127.0.0.1")

        let bound = withUnsafePointer(to: &addr) { raw in
            raw.withMemoryRebound(to: sockaddr.self, capacity: 1) { addrPtr in
                bind(sock, addrPtr, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        try #require(bound == 0)
        try #require(listen(sock, 1) == 0)

        // Read back the port the OS actually assigned.
        var assigned = sockaddr_in()
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        let named = withUnsafeMutablePointer(to: &assigned) { raw in
            raw.withMemoryRebound(to: sockaddr.self, capacity: 1) { addrPtr in
                getsockname(sock, addrPtr, &len)
            }
        }
        try #require(named == 0)

        return try body(UInt16(bigEndian: assigned.sin_port), sock)
    }
}
