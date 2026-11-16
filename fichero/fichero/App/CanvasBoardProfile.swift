import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "InteractionProfile")

/// Click and drag timing on the 2D Library board (`library.canvas.click-and-drag-are-timed`, #5253).
///
/// SwiftUI's gestures never see the mouse-down (a tap ends on the release, a drag begins after a few
/// points of travel), so the press is read from AppKit by the board's scroll-capture view, which
/// passes every event on untouched. Between the press and the frame after the release, every board
/// resolve and every reconcile is counted and timed, so a slow click names where its time went.
@MainActor
enum CanvasBoardProfile {
    enum Work { case resolve, reconcile }

    struct Press {
        let started: UInt64
        var released: UInt64?
        var waits: [UInt64] = []
        var resolves = 0
        var resolveNanos: UInt64 = 0
        var reconciles = 0
        var reconcileNanos: UInt64 = 0
    }

    private(set) static var press: Press?

    private static var now: UInt64 { DispatchTime.now().uptimeNanoseconds }

    /// A left-button event on the board. The release closes the press on the main thread's next
    /// turn, after the commit that draws what the click did; `onLogged` receives the line.
    static func mouse(_ phase: PreviewPointerPhase, onLogged: ((String) -> Void)? = nil) {
        switch phase {
        case .pressed:
            press = Press(started: now)
        case .dragged:
            guard press != nil else { return }
            let stamp = now
            DispatchQueue.main.async {
                MainActor.assumeIsolated { press?.waits.append(now &- stamp) }
            }
        case .released:
            guard press != nil else { return }
            press?.released = now
            DispatchQueue.main.async {
                MainActor.assumeIsolated {
                    guard let finished = press, finished.released != nil else { return }
                    press = nil
                    let line = summary(finished, ended: now)
                    logger.info("⏱ \(line, privacy: .public)")
                    onLogged?(line)
                }
            }
        }
    }

    /// Run one resolve or reconcile, counting it and its time against an open press.
    static func timing<Result>(_ work: Work, _ body: () -> Result) -> Result {
        guard press != nil else { return body() }
        let started = now
        defer {
            let spent = now &- started
            switch work {
            case .resolve:
                press?.resolves += 1
                press?.resolveNanos &+= spent
            case .reconcile:
                press?.reconciles += 1
                press?.reconcileNanos &+= spent
            }
        }
        return body()
    }

    /// "canvas click took 180.0ms: held 90.0ms, release → drawn 90.0ms; resolved 4 times, 60.0ms;
    /// reconciled 4 times, 20.0ms". A drag adds its moves after the total.
    nonisolated static func summary(_ press: Press, ended: UInt64) -> String {
        func ms(_ nanos: UInt64) -> Double { Double(nanos) / 1_000_000 }
        let released = press.released ?? ended
        var head = String(format: "canvas %@ took %.1fms", press.waits.isEmpty ? "click" : "drag", ms(ended &- press.started))
        if !press.waits.isEmpty {
            let waits = press.waits.map(ms)
            head += String(
                format: ": %d moves, average %.1fms, slowest %.1fms;",
                waits.count, waits.reduce(0, +) / Double(waits.count), waits.max() ?? 0
            )
        } else {
            head += String(format: ": held %.1fms,", ms(released &- press.started))
        }
        return head + String(
            format: " release → drawn %.1fms; resolved %d times, %.1fms; reconciled %d times, %.1fms",
            ms(ended &- released), press.resolves, ms(press.resolveNanos), press.reconciles, ms(press.reconcileNanos)
        )
    }
}
