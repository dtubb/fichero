import Foundation
import os

/// In-app main-thread stall measurement — Instruments made optional (#4550).
///
/// Why this exists (Daniel, 2026-08-08): the Instruments loop cost a whole
/// morning — every Hangs trace spends many minutes "modeling data" before a
/// single number comes out, and the SwiftUI instrument has produced zero rows
/// in five consecutive traces (#4547). The hang RATCHET only needs three
/// numbers per session (stall count, total, worst); the app can measure those
/// itself, on every ordinary run, for free.
///
/// Mechanism: a dedicated background thread sends ONE ping at a time to the
/// main queue and measures how long the main thread takes to run it. One
/// outstanding ping — never a flood — so a ping issued during a stall
/// measures that stall's remaining length honestly. Latency above 33ms (the
/// same threshold the Hangs instrument uses) is a stall and is appended to
/// `Logs/Fichero/stalls.log` beside the engine's log. Sessions APPEND with
/// SESSION headers (1MB rotation) — `check_hang_ratchet.py --stall-log`
/// measures the last one and holds it to the committed baseline.
///
/// Undercounting bias, stated: a stall can begin while the sampler sleeps
/// between pings, hiding up to one interval (16ms) of its start. That makes
/// measured durations a floor, never an exaggeration — the right bias for a
/// ratchet.
///
/// Off by default; costs nothing unless `FICHERO_STALL_LOG=1` is in the
/// environment (add it to the scheme's Run arguments to measure every ⌘R).
final class MainThreadStallSampler: @unchecked Sendable {
    static let shared = MainThreadStallSampler()

    /// The Hangs instrument's own "potential interaction delay" floor.
    static let stallThreshold: TimeInterval = 0.033
    private static let pingInterval: TimeInterval = 0.016

    private let logger = Logger(subsystem: "app.fichero.fichero", category: "StallSampler")
    private var running = false
    private var logHandle: FileHandle?

    /// One shared line format, parsed by `check_hang_ratchet.py --stall-log` —
    /// the two sides are pinned to each other by `MainThreadStallSamplerTests`.
    static func stallLine(date: Date, duration: TimeInterval) -> String {
        let iso = ISO8601DateFormatter().string(from: date)
        return String(format: "STALL %@ %.1fms", iso, duration * 1000)
    }

    static func startIfEnabled() {
        guard ProcessInfo.processInfo.environment["FICHERO_STALL_LOG"] == "1" else { return }
        shared.start()
    }

    private init() {}

    private func start() {
        guard !running else { return }
        running = true
        openLog()
        let thread = Thread { [weak self] in self?.sampleLoop() }
        thread.name = "fichero.stall-sampler"
        thread.qualityOfService = .utility
        thread.start()
        logger.info("Main-thread stall sampler running (threshold 33ms, sessions append)")
    }

    private func openLog() {
        do {
            let dir = try FileManager.default
                .url(for: .libraryDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
                .appendingPathComponent("Logs/Fichero", isDirectory: true)
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let file = dir.appendingPathComponent("stalls.log")
            // APPEND, never truncate (learned live 2026-08-08): truncating per
            // session let a 2-second relaunch blip DESTROY the just-recorded
            // session before the ratchet had baselined it. Sessions are
            // SESSION-headed; the ratchet reads the LAST COMPLETE one it is
            // pointed at, and a >1MB file rotates so it cannot grow forever.
            if let size = try? FileManager.default.attributesOfItem(atPath: file.path)[.size] as? Int,
               size > 1_000_000 {
                try? FileManager.default.removeItem(at: file)
            }
            if !FileManager.default.fileExists(atPath: file.path) {
                FileManager.default.createFile(atPath: file.path, contents: Data())
            }
            logHandle = try FileHandle(forWritingTo: file)
            logHandle?.seekToEndOfFile()
            let header = "SESSION \(ISO8601DateFormatter().string(from: Date()))\n"
            logHandle?.write(Data(header.utf8))
        } catch {
            // The sampler is instrumentation: it must never break the app —
            // but going quiet must be LOUD in the log, or an empty stalls.log
            // reads as a perfect session (absence-as-success).
            logger.error("Stall sampler could not open its log: \(error.localizedDescription) — sampling DISABLED")
            running = false
        }
    }

    private func sampleLoop() {
        while running {
            let pinged = Date()
            let done = DispatchSemaphore(value: 0)
            DispatchQueue.main.async { done.signal() }
            done.wait()
            let latency = Date().timeIntervalSince(pinged)
            if latency > Self.stallThreshold {
                record(latency: latency, at: pinged)
            }
            Thread.sleep(forTimeInterval: Self.pingInterval)
        }
    }

    private func record(latency: TimeInterval, at date: Date) {
        let line = Self.stallLine(date: date, duration: latency) + "\n"
        logHandle?.write(Data(line.utf8))
        // Mirror to unified logging so `log stream` shows stalls live.
        logger.warning("main-thread stall: \(Int(latency * 1000))ms")
    }
}
