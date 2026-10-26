import Foundation
import OSLog

/// The app's own log lines as one text file a person can share (#6124): this process's entries for the app's subsystem.
/// Values logged as private show as <private> outside a debugger; secrets are never logged.
enum LogExport {
    static let subsystem = "app.fichero.fichero"

    static func write(since seconds: TimeInterval = 3600) throws -> URL {
        let store = try OSLogStore(scope: .currentProcessIdentifier)
        let start = store.position(date: Date().addingTimeInterval(-seconds))
        let lines = try store.getEntries(at: start)
            .compactMap { $0 as? OSLogEntryLog }
            .filter { $0.subsystem == subsystem }
            .map { "\($0.date.formatted(.iso8601)) [\($0.category)] \($0.composedMessage)" }
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("fichero-log-\(Int(Date().timeIntervalSince1970)).txt")
        try lines.joined(separator: "\n").write(to: url, atomically: true, encoding: .utf8)
        return url
    }
}
