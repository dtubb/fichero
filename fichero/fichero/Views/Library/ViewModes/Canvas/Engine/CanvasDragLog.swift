import Foundation
import os

/// What a canvas drag did, in the unified log (maintainer 2026-10-09: a click and drag "doesn't always
/// work"). Each drag says when it began, how many move events it saw, how long it took and where it
/// was dropped; a press that never became a drag says why. Read with:
/// `log stream --predicate 'subsystem == "app.fichero.fichero" AND category == "canvas.drag"'`
@MainActor
enum CanvasDragLog {
    private static let log = Logger(subsystem: "app.fichero.fichero", category: "canvas.drag")
    private static var startedAt: ContinuousClock.Instant?
    private static var moves = 0

    static func began(_ id: String) {
        startedAt = .now
        moves = 0
        log.info("drag began on \(id, privacy: .public)")
    }

    static func moved() { moves += 1 }

    static func ended(_ id: String, dropTarget: String?) {
        let took = startedAt.map { ContinuousClock.now - $0 } ?? .zero
        log.info("""
            drag ended on \(id, privacy: .public) after \(took.formatted(.units(allowed: [.milliseconds])), privacy: .public), \
            \(moves) moves, dropped on \(dropTarget ?? "the board", privacy: .public)
            """)
        startedAt = nil
    }

    static func refused(_ why: String) {
        log.debug("press did not start a drag: \(why, privacy: .public)")
    }
}
