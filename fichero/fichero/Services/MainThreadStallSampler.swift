import Darwin
import Foundation
import os

// MARK: - Mid-stall main-thread backtrace (Daniel, 2026-08-08: "our stall
// sampler should tell us WHERE it's happening, not just that it's happening")
//
// The watcher thread cannot read another thread's stack from Swift, so when a
// ping is overdue it sends the MAIN thread SIGPROF; the handler — running ON
// the stalled main thread, interrupting whatever is blocking it — records raw
// return addresses into a preallocated buffer, and the watcher symbolicates
// them after the stall completes. `backtrace` is the standard practice for
// debug samplers even though it is not on the paper async-signal-safe list;
// this whole file is DEBUG tooling behind FICHERO_STALL_LOG=1 and never ships
// enabled. The signal can surface as EINTR in main-thread syscalls — one more
// reason this stays env-gated.

private let stallBacktraceMax = 64
// nonisolated(unsafe) DELIBERATELY: a signal handler cannot take locks or
// actors. One writer (the handler, on the stalled main thread) and one reader
// (the watcher, which waits on `stallBacktraceReady` before touching the
// buffer); plain Int32/pointer stores are single-copy atomic on arm64. Debug
// tooling behind FICHERO_STALL_LOG=1.
private nonisolated(unsafe) var stallBacktraceBuffer =
    [UnsafeMutableRawPointer?](repeating: nil, count: stallBacktraceMax)
private nonisolated(unsafe) var stallBacktraceCount: Int32 = 0
/// 0 = idle, 1 = handler finished writing the buffer.
private nonisolated(unsafe) var stallBacktraceReady: Int32 = 0

@_silgen_name("backtrace")
private func ficheroBacktrace(
    _ buffer: UnsafeMutablePointer<UnsafeMutableRawPointer?>, _ size: Int32
) -> Int32

@_silgen_name("backtrace_symbols")
private func ficheroBacktraceSymbols(
    _ buffer: UnsafePointer<UnsafeMutableRawPointer?>, _ size: Int32
) -> UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>?

private func stallSignalHandler(_ signal: Int32) {
    stallBacktraceCount = stallBacktraceBuffer.withUnsafeMutableBufferPointer { buf in
        guard let base = buf.baseAddress else { return 0 }
        return ficheroBacktrace(base, Int32(stallBacktraceMax))
    }
    stallBacktraceReady = 1
}

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
        // Called from applicationDidFinishLaunching — ON the main thread —
        // so this pthread_self IS the main thread, the SIGPROF target.
        assert(Thread.isMainThread, "start() must run on main to capture its pthread")
        mainPthread = pthread_self()
        signal(SIGPROF, stallSignalHandler)
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

    /// The main thread's pthread, captured in `start()` (which runs in
    /// `applicationDidFinishLaunching`, on main) — the SIGPROF target.
    private var mainPthread: pthread_t?

    private func sampleLoop() {
        while running {
            let pinged = Date()
            let done = DispatchSemaphore(value: 0)
            DispatchQueue.main.async { done.signal() }
            var frames: [String] = []
            if done.wait(timeout: .now() + Self.stallThreshold) == .timedOut {
                // The stall is IN PROGRESS — sample the main thread now,
                // mid-stall, so the log names the culprit (Daniel,
                // 2026-08-08), then wait out the remainder to measure the
                // full duration.
                frames = captureMainThreadBacktrace()
                done.wait()
            }
            let latency = Date().timeIntervalSince(pinged)
            if latency > Self.stallThreshold {
                record(latency: latency, at: pinged, frames: frames)
            }
            Thread.sleep(forTimeInterval: Self.pingInterval)
        }
    }

    private func captureMainThreadBacktrace() -> [String] {
        guard let mainPthread else { return [] }
        stallBacktraceReady = 0
        guard pthread_kill(mainPthread, SIGPROF) == 0 else { return [] }
        var spins = 0
        while stallBacktraceReady == 0 && spins < 2000 {  // ≤200ms
            usleep(100)
            spins += 1
        }
        guard stallBacktraceReady == 1, stallBacktraceCount > 0 else { return [] }
        let count = stallBacktraceCount
        guard let symbols = stallBacktraceBuffer.withUnsafeBufferPointer({ buf -> UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>? in
            guard let base = buf.baseAddress else { return nil }
            return ficheroBacktraceSymbols(base, count)
        }) else { return [] }
        defer { free(symbols) }
        var lines: [String] = []
        for index in 0..<Int(count) {
            guard let cString = symbols[index] else { continue }
            lines.append(String(cString: cString))
        }
        // Drop the capture machinery's own frames (the SIGPROF handler and
        // the signal trampoline top every capture — Daniel's first live log
        // showed only those). Then prefer the app's frames; keep system
        // frames only when nothing else survives (a pure-AppKit stall is
        // still an answer).
        let meaningful = lines.drop { line in
            line.contains("stallSignalHandler") || line.contains("_sigtramp")
                || line.contains("ficheroBacktrace")
        }
        let appFrames = meaningful.filter { $0.contains("Fichero") && !$0.contains("stallSignalHandler") }
        return Array((appFrames.isEmpty ? Array(meaningful) : appFrames).prefix(12))
    }

    private func record(latency: TimeInterval, at date: Date, frames: [String] = []) {
        var block = Self.stallLine(date: date, duration: latency) + "\n"
        // Frame lines are indented so the ratchet's ^STALL parser skips them.
        for frame in frames {
            block += "  \(frame)\n"
        }
        logHandle?.write(Data(block.utf8))
        // Mirror to unified logging so `log stream` shows stalls live.
        let top = frames.first.map { " — \($0)" } ?? ""
        logger.warning("main-thread stall: \(Int(latency * 1000))ms\(top)")
    }
}
