#if canImport(AppKit)
import Network
import Observation

/// The Fichero Macs on this network, found by browsing Bonjour (`_fichero._tcp`) for "Connect This Mac to Another
/// Fichero" (sharing.mac-finds-host, #5892). Presence only: the TXT record's `public_url` is the address to offer, and
/// the pairing code or invite grants trust. Which of these are shown is `HostChoices.offered`.
/// Main-actor isolated, so it is Sendable: the browser's handler (a @Sendable closure) may hold it weakly and hop back
/// to the main actor to publish what it found.
@MainActor @Observable
final class NearbyHosts {
    private(set) var found: [HostChoices.Found] = []
    /// True from start() to stop(): the Connect sheet says "Searching…" while it is and nothing is found yet.
    private(set) var searching = false
    private var browser: NWBrowser?

    func start() {
        guard browser == nil else { return }
        searching = true
        let browser = NWBrowser(for: .bonjourWithTXTRecord(type: "_fichero._tcp", domain: "local."), using: .tcp)
        browser.browseResultsChangedHandler = { [weak self] results, _ in
            let hosts = results.compactMap { result -> HostChoices.Found? in
                guard case let .service(name, _, _, _) = result.endpoint else { return nil }
                var url: String?
                if case let .bonjour(txt) = result.metadata { url = txt["public_url"] }
                return .init(name: name, publicURL: url?.isEmpty == false ? url : nil)
            }
            Task { @MainActor [weak self] in self?.found = hosts }
        }
        browser.start(queue: .main)
        self.browser = browser
    }

    func stop() {
        browser?.cancel()
        browser = nil
        searching = false
    }
}
#endif
