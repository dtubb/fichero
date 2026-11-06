#if os(macOS)
import Foundation
import os

/// Sharing over Tailscale, made by the APP (t55, #5317): the sandboxed engine cannot run the Tailscale CLI, so its own
/// forward never appeared and links named no tailnet address. When Sharing is on and Tailscale runs, the app publishes
/// the engine's loopback listener on the tailnet (`tailscale serve --bg --https=8765 https+insecure://127.0.0.1:8765`),
/// the same forward the engine makes when it can, and never replaces a forward it did not make. `--bg` keeps it in
/// Tailscale across restarts; the engine is told (`FICHERO_TAILNET_URL`, `FICHERO_TAILNET_FORWARD=app`) so its link
/// names the tailnet address first. A sandboxed app build cannot run the CLI either: then this logs why and the
/// Sharing pane's one command (`tailnet_serve_command`) stays the way.
enum TailnetForwardMaker {
    static let madeURLKey = "fichero.tailnet.appForwardURL"
    static let candidates = [
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
        "/usr/local/bin/tailscale",
        "/opt/homebrew/bin/tailscale"
    ]
    private static let logger = Logger(subsystem: "app.fichero.fichero", category: "TailnetForward")

    /// The tailnet address the app's forward serves, from the last time it was made or found; nil when none.
    static var madeURL: String? { UserDefaults.standard.string(forKey: madeURLKey) }

    /// What the engine is told so its link names the tailnet address first.
    static var engineEnvironment: [String: String] {
        guard let url = madeURL else { return [:] }
        return ["FICHERO_TAILNET_URL": url, "FICHERO_TAILNET_FORWARD": "app"]
    }

    static func wanted(port: Int) -> String { "https+insecure://127.0.0.1:\(port)" }

    /// This Mac's `https://<name>.<tailnet>.ts.net` from `tailscale status --json`, or nil when not running.
    static func tailnetURL(fromStatus json: Data) -> String? {
        guard let status = try? JSONSerialization.jsonObject(with: json) as? [String: Any],
              status["BackendState"] as? String == "Running",
              let selfNode = status["Self"] as? [String: Any],
              let dns = (selfNode["DNSName"] as? String)?.lowercased() else { return nil }
        let name = dns.hasSuffix(".") ? String(dns.dropLast()) : dns
        return name.hasSuffix(".ts.net") ? "https://\(name)" : nil
    }

    /// What the tailnet `port` serves, from `tailscale serve status --json` (the engine's `forward_target`).
    static func forwardTarget(fromServeStatus json: Data, port: Int) -> String? {
        guard let status = try? JSONSerialization.jsonObject(with: json) as? [String: Any],
              let entry = (status["TCP"] as? [String: Any])?[String(port)] as? [String: Any] else { return nil }
        if let tcp = entry["TCPForward"] as? String { return "tcp://\(tcp)" }
        guard entry["HTTPS"] as? Bool == true else { return "other" }
        for (hostPort, web) in (status["Web"] as? [String: Any]) ?? [:] where hostPort.hasSuffix(":\(port)") {
            let handlers = (web as? [String: Any])?["Handlers"] as? [String: Any]
            if let proxy = (handlers?["/"] as? [String: Any])?["Proxy"] as? String { return proxy }
        }
        return "https"
    }

    /// Makes the forward when Sharing is on and Tailscale runs; records the tailnet address it serves. Off the main
    /// actor: each CLI call may take a second.
    @discardableResult
    static func ensure(port: Int = 8765) async -> String? {
        await Task.detached(priority: .utility) { ensureNow(port: port) }.value
    }

    private static func ensureNow(port: Int) -> String? {
        guard let cli = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) }) else {
            return forget("Tailscale is not installed")
        }
        guard let status = run(cli, ["status", "--json"]), let url = tailnetURL(fromStatus: status) else {
            return forget("Tailscale did not answer, or is not running and logged in")
        }
        let want = wanted(port: port)
        let current = served(cli, port: port)
        if let current, current != want {
            return forget("tailnet port \(port) already serves \(current); a forward Fichero did not make stays")
        }
        if current == nil {
            _ = run(cli, ["serve", "--bg", "--https=\(port)", want])
            guard served(cli, port: port) == want else { return forget("tailscale serve did not publish port \(port)") }
        }
        logger.info("Sharing over Tailscale: \(url, privacy: .public):\(port) -> 127.0.0.1:\(port), made by the app")
        UserDefaults.standard.set(url, forKey: madeURLKey)
        return url
    }

    private static func served(_ cli: String, port: Int) -> String? {
        run(cli, ["serve", "status", "--json"]).flatMap { forwardTarget(fromServeStatus: $0, port: port) }
    }

    private static func forget(_ why: String) -> String? {
        logger.warning("Sharing over Tailscale: no forward from the app: \(why, privacy: .public)")
        UserDefaults.standard.removeObject(forKey: madeURLKey)
        return nil
    }

    // ponytail: no timeout; a stuck CLI holds only this detached task, never the app.
    private static func run(_ cli: String, _ args: [String]) -> Data? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: cli)
        process.arguments = args
        let out = Pipe()
        process.standardOutput = out
        process.standardError = Pipe()
        do { try process.run() } catch {
            logger.warning("Sharing over Tailscale: could not run \(cli, privacy: .public): \(error, privacy: .public)")
            return nil
        }
        let data = out.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return process.terminationStatus == 0 ? data : nil
    }
}
#endif
