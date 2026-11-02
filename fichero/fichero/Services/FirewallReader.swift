#if os(macOS)
import Foundation

/// Runs `socketfilterfw` (no admin needed for these two reads) off the main actor and hands the text to `FirewallCheck`.
/// A tool that is missing, refused or slow reads as `.unknown`, so the sheet never claims a block it did not see.
enum FirewallReader {
    static func read() async -> FirewallCheck.Verdict {
        await Task.detached(priority: .utility) {
            FirewallCheck.read { arguments in
                let process = Process()
                process.executableURL = URL(fileURLWithPath: FirewallCheck.tool)
                process.arguments = arguments
                let pipe = Pipe()
                process.standardOutput = pipe
                process.standardError = FileHandle.nullDevice
                guard (try? process.run()) != nil else { return nil }
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                return process.terminationStatus == 0 ? String(data: data, encoding: .utf8) : nil
            }
        }.value
    }
}
#endif
