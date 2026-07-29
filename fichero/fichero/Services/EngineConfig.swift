import Foundation

/// Single source of truth for the Fichero engine base URL.
///
/// Every part of the app reads `EngineConfig.host` (engine root, e.g.
/// `https://127.0.0.1:8765`) or `EngineConfig.apiBaseURL` (the `/api` base)
/// instead of hardcoding `127.0.0.1:8765`. The host is user-configurable via
/// Settings -> Backend. Only the macOS embedded-engine path implicitly
/// resolves a blank host to localhost; mobile clients require an explicit
/// remote host instead. Malformed non-empty values stay invalid instead of
/// silently resolving to localhost.
enum EngineConfig {
    static let userDefaultsKey = "fichero.server.host"

    /// Pre-rename host key (#4227: engine -> server). Existing installs have
    /// their configured host stored under this key; `migrateLegacyHostKeyIfNeeded()`
    /// copies it forward once at launch, and the read paths keep a read-through
    /// fallback for non-app processes that never run the migration.
    static let legacyUserDefaultsKey = "fichero.engine.host"

    /// One-time, in-place key migration: if the canonical key has never been
    /// written but the legacy key holds a value, copy it forward. The legacy
    /// value is deliberately NOT deleted, so rolling back to a pre-rename build
    /// still finds the host. Idempotent; call early at app launch.
    static func migrateLegacyHostKeyIfNeeded() {
        let store = defaults
        if store.object(forKey: userDefaultsKey) == nil,
           let legacy = store.string(forKey: legacyUserDefaultsKey) {
            store.set(legacy, forKey: userDefaultsKey)
        }
    }

    /// The preference store this config reads and writes.
    ///
    /// COMPUTED, with no stored state — deliberately. Tests used
    /// `UserDefaults.standard`, which in a test host IS the developer's real
    /// app domain, so a green test run repointed the running app at a
    /// `.example` host that can never resolve; the user saw a connection
    /// failure and blamed the engine (#4221).
    ///
    /// Computing rather than storing buys three things: a test process cannot
    /// reach `app.fichero.fichero` with or without a setUp, since the test/prod
    /// decision is made at each access (snapshot-and-restore in teardown was
    /// already there and did not help — most runs on a loaded box die by kill);
    /// there is no global MUTABLE state, so no `nonisolated(unsafe)`, the
    /// annotation removed in #4216 exactly because it enforces nothing; and
    /// production is unchanged, as the marker below is absent outside a test
    /// host.
    ///
    /// The test-suite handle is a cached SINGLE instance, not built per access:
    /// `UserDefaults.didChangeNotification` carries the posting instance as its
    /// `object`, and NotificationCenter filters `object:` by IDENTITY — a fresh
    /// instance per access could never match the one a store wrote through, so
    /// a "no writes happened" test would pass vacuously. `.standard` is already
    /// a singleton; this makes the test path behave the same way. Immutable
    /// `let`, so still no `nonisolated(unsafe)` mutable global (#4216).
    static var defaults: UserDefaults {
        guard isRunningUnderTests else { return .standard }
        return testSuiteDefaults
    }

    /// Suite backing every preference read in a test process.
    static let testSuiteName = "app.fichero.fichero.tests"
    /// `nonisolated(unsafe)` because `UserDefaults` is not `Sendable`; it IS
    /// documented thread-safe, and this is an immutable `let` — the annotation
    /// silences the shared-state diagnostic, it does not reintroduce mutable
    /// global state (#4216's concern).
    nonisolated(unsafe) private static let testSuiteDefaults =
        UserDefaults(suiteName: testSuiteName) ?? .standard

    /// True inside an XCTest/Swift Testing host process.
    ///
    /// Cached `let`: the answer cannot change mid-process, and the computed
    /// form re-materialized the entire environment dictionary on every
    /// `defaults` access — which sits on the launch path (#4036).
    ///
    /// Deliberately NOT keyed on `XCTestSessionIdentifier`: XCUITest injects
    /// that into the APP UNDER TEST too, which would silently repoint a
    /// UI-tested app at the throwaway suite — so UI tests would stop
    /// exercising the real preference path, and stale state would persist in
    /// the suite across runs. The app-under-test's isolation comes from
    /// `FICHERO_UITEST_HOME`, not from this seam. The two remaining markers
    /// are set only for the process that hosts the tests themselves.
    static let isRunningUnderTests: Bool = {
        let environment = ProcessInfo.processInfo.environment
        return environment["XCTestConfigurationFilePath"] != nil
            || environment["XCTestBundlePath"] != nil
    }()

    static let multiuserEnabledKey = "fichero.multiuser.enabled"
    static let defaultHostString = "https://127.0.0.1:8765"
    static let engineHostDidChangeNotification = Notification.Name("engineHostDidChange")

    enum HostConfiguration: Equatable {
        case embeddedLocal
        case configured(URL)
        case invalid(String)

        var hostString: String {
            switch self {
            case .embeddedLocal:
                return EngineConfig.defaultHostString
            case let .configured(url):
                return url.absoluteString
            case let .invalid(raw):
                return raw
            }
        }

        var host: URL {
            switch self {
            case .embeddedLocal:
                return EngineConfig.makeDefaultHostURL()
            case let .configured(url):
                return url
            case let .invalid(raw):
                return EngineConfig.makeInvalidHostURL(raw)
            }
        }

        var usesCustomHost: Bool {
            if case .embeddedLocal = self {
                return false
            }
            return true
        }

        var requiresExternalBackendConnection: Bool {
            switch self {
            case .embeddedLocal:
                return false
            case .configured, .invalid:
                return true
            }
        }

        var engineIsLocal: Bool {
            switch self {
            case .embeddedLocal:
                return true
            case let .configured(url):
                return EngineConfig.isLocalHost(url)
            case .invalid:
                return false
            }
        }
    }

    static var hostString: String {
        resolvedHostConfiguration.hostString
    }

    /// Engine root — host + port, no `/api`, no trailing slash.
    /// (e.g. `https://127.0.0.1:8765`)
    static var host: URL {
        #if os(macOS)
        // macOS runs the engine locally. Keep the host app on loopback;
        // publicBaseURL is only for QR/invite payloads consumed by others (#2604).
        return resolvedHostConfiguration.host
        #else
        // iOS/iPadOS never runs a local engine. Connect straight to the
        // saved/paired remote host as the first candidate — never probe
        // localhost, which has no engine and only times out before the real
        // (remote) host is tried (#2465). Falls back to the resolved sentinel
        // when nothing is paired yet, preserving the setup-screen behaviour.
        return connectionCandidates.first ?? resolvedHostConfiguration.host
        #endif
    }

    // MARK: - Connection candidate ordering

    /// Engine hosts to attempt, in priority order, when establishing the
    /// initial connection. The first reachable candidate wins.
    ///
    /// Branches by platform because only macOS runs a local engine:
    /// - **macOS** tries the local engine (`defaultHostString`) first and a
    ///   configured non-loopback remote host (if any) as the fallback.
    /// - **iOS / iPadOS** has no local engine, so the saved/paired remote host
    ///   is the first (and only) candidate. localhost is omitted entirely —
    ///   probing it just times out and delays connecting to the real engine
    ///   (#2465).
    static var connectionCandidates: [URL] {
        orderedConnectionCandidates(
            savedHostString: defaults.string(forKey: userDefaultsKey)
                ?? defaults.string(forKey: legacyUserDefaultsKey),
            isMacOS: allowsEmbeddedLocalDefault
        )
    }

    /// Pure, dependency-injected ordering used by `connectionCandidates`.
    /// `savedHostString` is the persisted `fichero.server.host`; `isMacOS`
    /// selects the platform branch. Exposed (rather than inlined) so the
    /// ordering can be unit-tested without mutating `UserDefaults` or the
    /// build platform.
    static func orderedConnectionCandidates(
        savedHostString: String?,
        isMacOS: Bool
    ) -> [URL] {
        let savedRemote: URL?
        if case let .configured(url) = hostConfiguration(
            from: savedHostString,
            allowsImplicitEmbeddedLocalDefault: false
        ) {
            savedRemote = url
        } else {
            savedRemote = nil
        }

        guard isMacOS else {
            // iOS: saved/paired remote first, localhost never.
            return savedRemote.map { [$0] } ?? []
        }

        // macOS: local engine first, configured non-loopback remote fallback.
        var candidates = [makeDefaultHostURL()]
        if let savedRemote,
           let savedHost = savedRemote.host?.lowercased(),
           !isLoopbackHostLiteral(savedHost) {
            candidates.append(savedRemote)
        }
        return candidates
    }

    /// API base — the engine root with the `/api` prefix.
    /// (e.g. `https://127.0.0.1:8765/api`)
    static var apiBaseURL: URL {
        host.appendingPathComponent("api")
    }

    static var usesCustomHost: Bool {
        resolvedHostConfiguration.usesCustomHost
    }

    static var hasConfiguredHost: Bool {
        if case .configured = resolvedHostConfiguration {
            return true
        }
        return false
    }

    /// True when startup should connect to an explicit configured backend
    /// instead of launching or restarting the embedded engine.
    static var requiresExternalBackendConnection: Bool {
        resolvedHostConfiguration.requiresExternalBackendConnection
    }

    static var multiuserEnabled: Bool {
        let defaults = Self.defaults
        guard defaults.object(forKey: multiuserEnabledKey) != nil else {
            // Default OFF: multi-user is a shared/multi-person feature and the frontend
            // has no login flow yet (#2022 auth is cli-only). Defaulting ON spawns the
            // backend with FICHERO_MULTIUSER=1, whose fail-closed ACL choke-point then
            // 401/403s the app's own requests so no library loads.
            return false
        }
        return defaults.bool(forKey: multiuserEnabledKey)
    }

    /// True when the configured engine host is localhost / 127.0.0.1 / ::1.
    /// Use this to guard "Reveal in Finder" and any other action that assumes
    /// the engine and the app share a local filesystem. When the engine is
    /// remote these actions must be hidden — local paths are meaningless.
    static var engineIsLocal: Bool {
        resolvedHostConfiguration.engineIsLocal
    }
}

// MARK: - Host configuration resolution

extension EngineConfig {
    static func hostConfiguration(from raw: String?) -> HostConfiguration {
        hostConfiguration(
            from: raw,
            allowsImplicitEmbeddedLocalDefault: allowsEmbeddedLocalDefault
        )
    }

    static func hostConfiguration(
        from raw: String?,
        allowsImplicitEmbeddedLocalDefault: Bool
    ) -> HostConfiguration {
        guard let normalized = normalizedHostString(raw) else {
            return allowsImplicitEmbeddedLocalDefault ? .embeddedLocal : .invalid("")
        }
        guard let url = makeURL(normalized), url.host != nil else {
            return .invalid(normalized)
        }
        guard url.scheme?.lowercased() == "https" else {
            return .invalid(normalized)
        }
        return .configured(url)
    }

    private static var resolvedHostConfiguration: HostConfiguration {
        hostConfiguration(from: defaults.string(forKey: userDefaultsKey)
            ?? defaults.string(forKey: legacyUserDefaultsKey))
    }

    private static func normalizedHostString(_ raw: String?) -> String? {
        guard let raw else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        return trimmed.replacingOccurrences(of: "/+$", with: "", options: .regularExpression)
    }

    // Promoted from `private` to internal: `EngineConfig+Launch.swift` reads this
    // cross-file (same-file extensions keep private access, separate files do not).
    static var allowsEmbeddedLocalDefault: Bool {
        #if os(macOS)
        true
        #else
        false
        #endif
    }

    private static func makeURL(_ string: String) -> URL? {
        URL(string: string)
    }

    private static func isLocalHost(_ url: URL) -> Bool {
        guard let host = url.host?.lowercased() else { return false }
        return isLoopbackHostLiteral(host)
    }

    // Promoted from `fileprivate` to internal: `validatedRemoteURL` in
    // `RemoteAccessConfig.swift` references this cross-file.
    static func isLoopbackHostLiteral(_ host: String) -> Bool {
        if host == "localhost" {
            return true
        }

        let trimmedHost = host.trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        if isIPv4LoopbackLiteral(trimmedHost) {
            return true
        }
        return isIPv6LoopbackLiteral(trimmedHost)
    }

    private static func isIPv4LoopbackLiteral(_ host: String) -> Bool {
        let octets = host.split(separator: ".", omittingEmptySubsequences: false)
        guard octets.count == 4 else { return false }
        let numbers = octets.compactMap { Int($0) }
        guard numbers.count == 4, numbers.allSatisfy({ (0...255).contains($0) }) else { return false }
        return numbers[0] == 127
    }

    private static func isIPv6LoopbackLiteral(_ host: String) -> Bool {
        let normalized = host.lowercased()
        if normalized == "::1" || normalized == "0:0:0:0:0:0:0:1" {
            return true
        }

        guard let mappedRange = normalized.range(of: "::ffff:") else {
            return false
        }
        let mappedIPv4 = String(normalized[mappedRange.upperBound...])
        return isIPv4LoopbackLiteral(mappedIPv4)
    }

    private static func makeDefaultHostURL() -> URL {
        guard let url = URL(string: defaultHostString) else {
            preconditionFailure("EngineConfig: malformed default URL literal '\(defaultHostString)'")
        }
        return url
    }

    private static func makeInvalidHostURL(_ raw: String) -> URL {
        var components = URLComponents()
        components.scheme = "invalid"
        components.host = "configured-engine"
        components.path = "/" + raw
        guard let url = components.url else {
            preconditionFailure("EngineConfig: unable to build invalid host sentinel for '\(raw)'")
        }
        return url
    }
}

/// Describes WHERE a library's engine lives so the sidebar can show a small
/// local-vs-remote badge on each library row (#2574). "Front-end-first":
/// today every open library shares the app-level `EngineConfig` host, so the
/// descriptor is derived from it via ``current()``. Once a per-library
/// `host` lands on `LibraryReference`, only that one call site changes — the
/// badge UI keeps reading `library.locationDescriptor`.
struct LibraryLocationDescriptor: Equatable {
    /// True when the engine runs on the same machine as the app.
    let isLocal: Bool
    /// Short human label, e.g. "On this Mac" or "On studio.local".
    let label: String
    /// SF Symbol for the badge.
    let systemImage: String

    /// Derives the descriptor from the app-level `EngineConfig` host — the
    /// default host every library shared before per-library hosts (#2866).
    static func current() -> LibraryLocationDescriptor {
        forHost(.appDefault)
    }

    /// Derives the descriptor from a SPECIFIC backend host (#3112/#2574). Now
    /// that each `LibraryReference` carries its own `host`, the sidebar badge
    /// reads that host rather than the single global — so a remote library
    /// shows its remote host even while a local library sits beside it.
    static func forHost(_ host: BackendHost) -> LibraryLocationDescriptor {
        if host.isLocal {
            #if os(macOS)
            return LibraryLocationDescriptor(
                isLocal: true,
                label: "On this Mac",
                systemImage: "laptopcomputer"
            )
            #else
            return LibraryLocationDescriptor(
                isLocal: true,
                label: "On this device",
                systemImage: "ipad"
            )
            #endif
        }
        let hostName = host.url.host ?? host.url.absoluteString
        return LibraryLocationDescriptor(
            isLocal: false,
            label: "On \(hostName)",
            systemImage: "network"
        )
    }
}
