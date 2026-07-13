import FicheroAPIClient
import Foundation
import Observation

/// Observable domain store for the known-library registry — the recents/open
/// picker's source of truth. Relocated from `Views/Menu/FileMenuCommands.swift`
/// into the store layer (#3677) so it sits with the other `@Observable` stores
/// and is the single accessor for its endpoints (observable-data-layer mandate).
///
/// Endpoints owned (reached through the generated OpenAPI client, never a raw
/// URLSession):
///   - `GET  /api/registry`                    — on-disk known-library registry (local host)
///   - `POST /api/registry/add`                — record an opened/saved library
///   - `DELETE /api/registry/{library_path}`   — forget a library
///   - `GET  /api/authz/libraries`             — libraries this credential may open (remote host)
@MainActor
@Observable
final class KnownLibraryRegistryStore {
    static let shared = KnownLibraryRegistryStore()

    private(set) var libraries: [KnownLibraryMenuEntry] = []
    private(set) var fetchError: String?

    private let apiClient = APIClient()
    @ObservationIgnored private nonisolated(unsafe) var hostChangeObservation: NSObjectProtocol?

    private init() {
        // Rebind on a pairing / Settings host change (#2349) — otherwise the
        // known-library registry menu keeps querying the launch host (localhost)
        // after the app has moved to a remote engine.
        hostChangeObservation = NotificationCenter.default.addObserver(
            forName: EngineConfig.engineHostDidChangeNotification,
            object: nil,
            queue: nil
        ) { [weak self] _ in
            Task { @MainActor in
                self?.apiClient.reconfigure(baseURL: EngineConfig.host)
            }
        }
    }

    deinit {
        if let hostChangeObservation {
            NotificationCenter.default.removeObserver(hostChangeObservation)
        }
    }

    /// Whether the app's engine is a remote Mac rather than the loopback/embedded
    /// engine. Remote hosts source the picker from the per-user authz endpoint
    /// (`/api/authz/libraries`) — role-aware, and NOT gated on the local
    /// filesystem — while local hosts keep using the on-disk registry (#3151).
    private var hostIsRemote: Bool { !BackendHost.appDefault.isLocal }

    func refresh() async {
        if hostIsRemote {
            await refreshAccessible()
        } else {
            await refreshRegistry()
        }
    }

    /// Local host: the on-disk known-library registry (`GET /api/registry`).
    private func refreshRegistry() async {
        do {
            let response = try await apiClient.api.listKnownLibrariesApiRegistryGet(.init())
            switch response {
            case .ok(let okResponse):
                let body = try okResponse.body.json
                libraries = body.libraries.map { lib in
                    KnownLibraryMenuEntry(
                        id: lib.id ?? lib.path,
                        path: lib.path,
                        name: lib.name,
                        addedAt: lib.addedAt,
                        lastAccessed: lib.lastAccessed
                    )
                }
                fetchError = nil
            default:
                fetchError = "Unexpected response from registry"
            }
        } catch {
            fetchError = error.localizedDescription
        }
    }

    /// Remote host: the libraries this credential may open (#3151), from
    /// `GET /api/authz/libraries`. Ordered recents-first using the per-host MRU
    /// so the picker leads with what the user actually opens on this engine.
    private func refreshAccessible() async {
        do {
            let response = try await apiClient.api.listAccessibleLibrariesApiAuthzLibrariesGet()
            switch response {
            case .ok(let okResponse):
                let body = try okResponse.body.json
                let entries = body.items.map { lib in
                    KnownLibraryMenuEntry(
                        id: lib.libraryPath,
                        path: lib.libraryPath,
                        name: lib.libraryName,
                        addedAt: nil,
                        lastAccessed: nil
                    )
                }
                let recents = RemoteLibraryRecents.paths(forHost: EngineConfig.host.absoluteString)
                libraries = Self.recentsFirst(entries, recents: recents)
                fetchError = nil
            default:
                fetchError = "Unexpected response from libraries"
            }
        } catch {
            fetchError = error.localizedDescription
        }
    }

    /// Partition `entries` so any whose path is in `recents` come first, in
    /// recents order; the rest keep the server order. A partition (not a
    /// comparator sort) because Swift's `sort` isn't guaranteed stable — the
    /// non-recent tail must preserve the server's ordering exactly. (#3151)
    static func recentsFirst(
        _ entries: [KnownLibraryMenuEntry],
        recents: [String]
    ) -> [KnownLibraryMenuEntry] {
        guard !recents.isEmpty else { return entries }
        let byPath = Dictionary(entries.map { ($0.path, $0) }, uniquingKeysWith: { first, _ in first })
        let head = recents.compactMap { byPath[$0] }
        let recentPaths = Set(recents)
        let tail = entries.filter { !recentPaths.contains($0.path) }
        return head + tail
    }

    func noteOpenedLibrary(url: URL, displayName: String?) async {
        guard !LibraryManager.shared.isTemporaryLibrary(url) else { return }
        guard url.pathExtension.lowercased() == "fichero" else { return }

        do {
            // NFC-normalize path + name (#3076) so the global registry keys this
            // library canonically and never records a second NFD variant.
            // `POST /api/registry/add` via the shared typed client (#3030).
            let response = try await apiClient.api.addKnownLibraryApiRegistryAddPost(
                query: .init(
                    path: url.path.nfcNormalized,
                    name: (displayName ?? url.lastPathComponent).nfcNormalized
                )
            )
            if case .ok = response {
                await refresh()
            }
        } catch {
            // Best-effort only: menu recents should never block opening/saving a library.
        }
    }

    func remove(path: String) async {
        // Compare/address by NFC (#3076): registry entries from `refresh()` are
        // NFC (backend #3071), so normalize the incoming path or an NFD caller
        // would fail to match and silently leave the entry behind.
        let path = path.nfcNormalized
        do {
            // `DELETE /api/registry/{library_path}` (#3030); the runtime
            // percent-encodes the path param, and the backend decodes it back.
            let response = try await apiClient.api.removeKnownLibraryApiRegistryLibraryPathDelete(
                path: .init(libraryPath: path)
            )
            if case .ok = response {
                libraries.removeAll { $0.path.nfcNormalized == path }
            } else {
                await refresh()
            }
        } catch {
            await refresh()
        }
    }

    func clearAll() async {
        let paths = libraries.map(\.path)
        for path in paths {
            await remove(path: path)
        }
    }
}

struct KnownLibraryMenuEntry: Identifiable, Equatable {
    let id: String
    let path: String
    let name: String?
    let addedAt: Date?
    let lastAccessed: Date?

    var displayName: String {
        if let trimmedName = name?.trimmingCharacters(in: .whitespacesAndNewlines),
           !trimmedName.isEmpty {
            return trimmedName
        }

        return URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent
    }
}
