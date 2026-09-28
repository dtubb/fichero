//
//  EngineSocketConflictTests.swift
//  FicheroTests
//
//  Another Fichero engine answering on the container socket is a CONFLICT, never a second engine
//  (2026-09-28: the installed /Applications build started alongside a dev build, each engine rewrote
//  the one `.api-key`, and the app got 401 on some requests and 200 on others). A real AF_UNIX listener
//  stands in for the other engine; nothing else is faked.
//

@testable import Fichero
import Darwin
import Foundation
import Testing

@Suite("Another engine on the socket (2026-09-28)")
@MainActor
struct EngineSocketConflictTests {

    /// A listening AF_UNIX socket at a short path -- the "other engine". Answers connects; serves nothing.
    private final class FakeLiveSocket {
        let path: String
        private var descriptor: Int32 = -1

        init() throws {
            path = "/tmp/fsc-\(UUID().uuidString.prefix(8)).sock"
            unlink(path)
            descriptor = socket(AF_UNIX, SOCK_STREAM, 0)
            var address = sockaddr_un()
            address.sun_family = sa_family_t(AF_UNIX)
            let bytes = Array(path.utf8)
            withUnsafeMutableBytes(of: &address.sun_path) { raw in
                raw.copyBytes(from: bytes)
                raw[bytes.count] = 0
            }
            let bound = withUnsafePointer(to: &address) { pointer in
                pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    bind(descriptor, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
                }
            }
            #expect(bound == 0)
            #expect(listen(descriptor, 4) == 0)
        }

        /// The engine died: the listener closes, the socket FILE stays behind.
        func die() {
            close(descriptor)
            descriptor = -1
        }

        deinit {
            if descriptor >= 0 { close(descriptor) }
            unlink(path)
        }
    }

    @Test("a live socket answers; a dead engine's leftover file and a missing path do not")
    func liveness() throws {
        let other = try FakeLiveSocket()
        #expect(EngineSocketConflict.isLive(socketPath: other.path), "an engine answers: live")
        other.die()
        #expect(FileManager.default.fileExists(atPath: other.path), "the socket file is still there")
        #expect(!EngineSocketConflict.isLive(socketPath: other.path),
                "nothing listening behind it: not live, so the spawn goes ahead as before")
        #expect(!EngineSocketConflict.isLive(socketPath: "/tmp/fsc-never-\(UUID().uuidString.prefix(8)).sock"))
    }

    @Test("a live socket never gets a second engine: the person decides, Stop it only with a pid")
    func decision() {
        typealias Choice = EmbeddedBackendService.PortConflictResolution
        #expect(EngineSocketConflict.decision(socketLive: false, holderPID: nil, pendingChoice: nil) == .spawnOurs)
        #expect(EngineSocketConflict.decision(socketLive: true, holderPID: nil, pendingChoice: nil) == .surface)
        #expect(EngineSocketConflict.decision(socketLive: true, holderPID: 42, pendingChoice: nil) == .surface)
        #expect(EngineSocketConflict.decision(socketLive: true, holderPID: nil, pendingChoice: Choice.useIt) == .adoptExisting)
        #expect(EngineSocketConflict.decision(socketLive: true, holderPID: nil, pendingChoice: Choice.stopIt) == .surface,
                "no pid to stop: asked again, never a blind spawn over the live one")
        #expect(EngineSocketConflict.decision(socketLive: true, holderPID: 42, pendingChoice: Choice.stopIt)
                == .stopThenSpawn(pid: 42))
    }

    @Test("the pre-flight over a fake live socket throws socketInUse instead of spawning")
    func preflightRefusesToSpawn() async throws {
        let other = try FakeLiveSocket()
        let service = EmbeddedBackendService()
        await #expect(throws: BackendError.self) {
            _ = try await service.resolveLiveSocket(other.path, mayStop: false)
        }
        other.die()
        let afterDeath = try await service.resolveLiveSocket(other.path, mayStop: false)
        #expect(afterDeath == nil, "the other engine gone: the pre-flight lets the spawn go ahead")
    }

    @Test("the window names the other engine as far as it is known, and offers the conflict choice")
    func presentation() {
        let session = EngineSession()
        session.markSocketConflict(pid: nil, version: "0.9.3")
        #expect(session.phase == .portConflict(pid: nil))
        #expect(session.diagnosis == EngineSession.Conflict.socket(pid: nil, version: "0.9.3").sentence)
        #expect(session.diagnosis?.hasPrefix("Another Fichero engine (version 0.9.3) is already running") == true)
        let shown = ConnectionPresentation.status(
            phase: session.phase, ownership: .appManaged, accessError: nil, authBroken: false, conflict: session.conflict
        )
        #expect(shown.title == "Another Fichero Is Running")
        #expect(shown.action == .resolvePortConflict)
        #expect(EngineSession.Conflict.socket(pid: 71, version: nil).sentence.hasPrefix("Another Fichero engine, PID 71,"))
        // The owning app (engine_owner, 7c00a47ed), in words -- the installed app of the 2026-09-28 401s.
        let installed = EngineSession.Conflict.socket(pid: 71, version: "0.9.3", owner: "/Applications/Fichero.app").sentence
        #expect(installed.hasPrefix("Another Fichero engine (version 0.9.3), PID 71, from Fichero.app in /Applications is"))
        #expect(EngineConflict.ownerPhrase("dev external") == "started from a script")
        #expect(EngineConflict.ownerPhrase(nil) == nil)

        session.markPortConflict(pid: 9)
        #expect(ConnectionPresentation.status(
            phase: session.phase, ownership: .appManaged, accessError: nil, authBroken: false, conflict: session.conflict
        ).title == "Port 8765 Is In Use", "a held port is still worded as a port")
    }
}
