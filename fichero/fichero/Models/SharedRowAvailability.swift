import Foundation

/// Which Shared Libraries rows to grey (`sharing.marks.off-greys-row`, #5739, #6360): a row whose host ANSWERED and no
/// longer lists its library for this device. A read that failed or was slow says nothing, so it greys nothing.
enum SharedRowAvailability {
    /// How long a host's answer is trusted before the next launch or focus asks again.
    static let throttle: TimeInterval = 60

    /// The row key the sidebar and `LibraryManager.greyedSharedRows` use.
    static func key(host: String, library: String) -> String { "\(host)|\(canonical(library))" }

    /// `libraries` the host did not list. `accessible` is nil when the read failed: nothing is greyed.
    static func unavailable(libraries: [String], accessible: [String]?) -> Set<String> {
        guard let accessible else { return [] }
        let listed = Set(accessible.map(canonical))
        return Set(libraries.filter { !listed.contains(canonical($0)) }.map(canonical))
    }

    /// False when this host was asked less than `throttle` seconds ago.
    static func shouldAsk(host: String, now: Date, lastAsked: [String: Date]) -> Bool {
        guard let last = lastAsked[host] else { return true }
        return now.timeIntervalSince(last) >= throttle
    }

    /// What the paired host says this device may open, over the pinned connection to THAT host (`PairingService(apiRoot:)`
    /// would dial this Mac's own engine in a release build). nil when no pin is stored for the host or the read fails.
    @MainActor static func readFromHost(
        _ root: URL, pin: String? = nil
    ) async -> [String]? {
        guard let pin = pin ?? RemoteAccessConfig.hostedBackendSPKIPin(hostString: root.absoluteString),
              let service = try? PairingService(apiRoot: root, expectedSPKIPin: pin) else { return nil }
        return try? await service.accessibleLibraryPaths()
    }

    private static func canonical(_ path: String) -> String {
        URL(fileURLWithPath: path).standardized.path.nfcNormalized
    }
}

extension LibraryManager {
    /// Asks each paired Mac once which libraries it still gives this device, at launch and when the app comes forward, and
    /// greys the rows it no longer lists. Uses the pairing read that already exists (`GET /api/authz/libraries`); a failed read
    /// greys nothing and logs once. `read` and `now` are the test seam.
    func checkSharedRows(
        now: Date = Date(),
        read: @escaping (URL) async -> [String]? = { await SharedRowAvailability.readFromHost($0) }
    ) async {
        for machine in pairedMachines {
            guard let root = URL(string: machine.id),
                  SharedRowAvailability.shouldAsk(host: machine.id, now: now, lastAsked: hostRowsLastAsked) else { continue }
            hostRowsLastAsked[machine.id] = now
            let accessible = await read(root)
            guard accessible != nil else {  // a failed or slow read changes nothing
                libraryManagerLogger.info("Could not ask \(machine.name, privacy: .public) which libraries it still shares")
                continue
            }
            let gone = SharedRowAvailability.unavailable(libraries: machine.libraries, accessible: accessible)
            greyedSharedRows.subtract(machine.libraries.map { SharedRowAvailability.key(host: machine.id, library: $0) })
            greyedSharedRows.formUnion(gone.map { "\(machine.id)|\($0)" })
        }
    }
}
