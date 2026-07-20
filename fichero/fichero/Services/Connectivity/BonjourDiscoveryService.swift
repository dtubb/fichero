#if os(iOS) || os(tvOS) || os(visionOS)
import Foundation
import SwiftUI

// A discovered Fichero Mac on the local network. `internal` (not private):
// exposed by BonjourDiscoveryService.hosts and read by the Connect UI
// (ConnectDiscoveredMacsSectionIOS / RemoteConnectionSetupView).
struct BonjourHostRecord: Identifiable, Equatable {
    let id: String
    let displayName: String
    let reachableURL: String?

    var hasReachableURL: Bool {
        guard let reachableURL else { return false }
        return !reachableURL.isEmpty
    }
}

/// Browses the LAN for `_fichero._tcp` services so an iOS device can find a Mac
/// to pair with (#3102). Discovery only surfaces *which* Mac is present; the QR
/// scan grants trust. Split out of FicheroApp_iOS.swift by file_length, then
/// moved here (cross-platform NetService discovery logic → Services/Connectivity).
final class BonjourDiscoveryService: NSObject, ObservableObject {
    @Published private(set) var hosts: [BonjourHostRecord] = []

    private let browser = NetServiceBrowser()
    private var services: [String: NetService] = [:]
    private var records: [String: BonjourHostRecord] = [:]
    private var started = false

    override init() {
        super.init()
        browser.delegate = self
    }

    func start() {
        guard !started else { return }
        started = true
        browser.searchForServices(ofType: "_fichero._tcp.", inDomain: "local.")
    }

    private func refreshHosts() {
        hosts = records.values.sorted {
            $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending
        }
    }

    private func recordID(for service: NetService) -> String {
        "\(service.domain)|\(service.type)|\(service.name)"
    }

    private func decodeTXTRecord(for service: NetService) -> [String: String] {
        guard let txtData = service.txtRecordData() else { return [:] }
        return NetService.dictionary(fromTXTRecord: txtData).reduce(into: [:]) { partialResult, pair in
            partialResult[pair.key] = String(data: pair.value, encoding: .utf8) ?? ""
        }
    }

    private func handleFound(_ service: NetService, moreComing: Bool) {
        let id = recordID(for: service)
        services[id] = service
        service.delegate = self
        service.resolve(withTimeout: 5)

        records[id] = BonjourHostRecord(
            id: id,
            displayName: service.name,
            reachableURL: nil
        )
        if !moreComing {
            refreshHosts()
        }
    }

    private func handleRemoved(_ service: NetService, moreComing: Bool) {
        let id = recordID(for: service)
        services[id] = nil
        records[id] = nil
        if !moreComing {
            refreshHosts()
        }
    }

    private func handleResolved(_ sender: NetService) {
        let id = recordID(for: sender)
        let txtRecord = decodeTXTRecord(for: sender)
        let reachableURL = txtRecord["public_url"]
            .flatMap {
                try? validatedRemoteURL(
                    from: $0,
                    allowLocalhost: false,
                    requireSecureTransportForRemote: true
                ).absoluteString
            }
        records[id] = BonjourHostRecord(
            id: id,
            displayName: sender.name,
            reachableURL: reachableURL
        )
        refreshHosts()
    }

    private func handleResolveFailure(_ sender: NetService) {
        let id = recordID(for: sender)
        records[id] = BonjourHostRecord(
            id: id,
            displayName: sender.name,
            reachableURL: nil
        )
        refreshHosts()
    }
}

extension BonjourDiscoveryService: NetServiceBrowserDelegate {
    func netServiceBrowser(
        _ browser: NetServiceBrowser,
        didFind service: NetService,
        moreComing: Bool
    ) {
        handleFound(service, moreComing: moreComing)
    }

    func netServiceBrowser(
        _ browser: NetServiceBrowser,
        didRemove service: NetService,
        moreComing: Bool
    ) {
        handleRemoved(service, moreComing: moreComing)
    }
}

extension BonjourDiscoveryService: NetServiceDelegate {
    func netServiceDidResolveAddress(_ sender: NetService) {
        handleResolved(sender)
    }

    func netService(_ sender: NetService, didNotResolve errorDict: [String: NSNumber]) {
        handleResolveFailure(sender)
    }
}
#endif
