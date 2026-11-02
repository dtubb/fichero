import Foundation

/// `sharing.firewall-prompt-says-what-to-click` (Step 3.2): reads what macOS's application firewall says about the
/// engine, from the two outputs of `socketfilterfw` that need no admin (`--getglobalstate`, `--listapps`).
/// Pure parsing; the tool is run by `FirewallCheck.read` through an injected runner so tests never spawn it.
enum FirewallCheck {
    enum Verdict: Equatable {
        case notBlocking
        case blocking
        /// The firewall has no entry for the engine (or the tool could not be read): nothing to claim either way.
        case unknown
    }

    static let tool = "/usr/libexec/ApplicationFirewall/socketfilterfw"
    static let engineAppName = "Fichero Server"

    /// The sentence the sheet shows in place of a link that cannot work.
    static let blockedSentence =
        "macOS is blocking other devices from reaching Fichero. "
            + "Open System Settings › Network › Firewall › Options and allow Fichero Server."

    static func verdict(globalState: String, listApps: String, appName: String = engineAppName) -> Verdict {
        let state = globalState.lowercased()
        if state.contains("disabled") || state.contains("state = 0") { return .notBlocking }
        guard state.contains("enabled") || state.contains("state = 1") || state.contains("state = 2") else { return .unknown }
        // `--listapps`: a "N :  /path/App.app" line, then "( Allow|Block incoming connections )".
        let lines = listApps.components(separatedBy: .newlines)
        for (index, line) in lines.enumerated() where line.contains(appName) {
            for next in lines[(index + 1)...] {
                let text = next.lowercased()
                if text.contains("block incoming") { return .blocking }
                if text.contains("allow incoming") { return .notBlocking }
                if text.contains(" :  ") || text.range(of: #"^\s*\d+\s*:"#, options: .regularExpression) != nil { break }
            }
        }
        return .unknown
    }

    /// Runs the tool through `run` (arguments → stdout, nil when it cannot run). Unreadable is `.unknown`, never a guess.
    static func read(run: ([String]) -> String?) -> Verdict {
        guard let state = run(["--getglobalstate"]), let apps = run(["--listapps"]) else { return .unknown }
        return verdict(globalState: state, listApps: apps)
    }
}
