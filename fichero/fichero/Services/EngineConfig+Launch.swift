import FicheroAPIClient
import Foundation
#if canImport(AppKit)
import AppKit
#endif

extension EngineConfig {
    // MARK: - Client transport selection (in-process / UDS overrides)

    /// Which `ClientTransport` the app-wide `FicheroClient` should dial with.
    ///
    /// Default is `.https` (URLSession, cert-pinned where configured). Two debug
    /// environment overrides let a developer redirect the local engine
    /// connection without code changes — both are read once at client
    /// construction and both are honoured only for a local engine:
    ///
    /// - `FICHERO_FORCE_INMEMORY` (macOS only): drive the Python engine
    ///   in-process via PythonKit (`.inMemory`). Lets a `⌘R` Debug build run the
    ///   engine embedded in the app process — the "PythonKit for real" path.
    /// - `FICHERO_FORCE_UDS_PATH=/path/to/engine.sock`: dial the engine over an
    ///   AF_UNIX socket (`.uds`).
    ///
    /// In-process wins if both are set. A configured remote host keeps `.https`,
    /// except in a hermetic UI test whose explicit transport owns the launch.
    static var transportMode: TransportMode {
        localDebugTransportOverride() ?? transportMode(for: engineProvisioningStrategy())
    }

    /// Debug-only overrides for the LOCAL engine transport, or `nil` when none is
    /// set. Returns `nil` for a configured remote host outside UI testing.
    static func localDebugTransportOverride(
        environment env: [String: String] = ProcessInfo.processInfo.environment,
        hostRequiresRemoteConnection: Bool = requiresExternalBackendConnection,
        uiTesting: Bool = isUITesting()
    ) -> TransportMode? {
        // A hermetic UI test explicitly owns its transport; a developer's saved
        // remote host must not redirect it away from the test engine.
        guard uiTesting || !hostRequiresRemoteConnection else { return nil }
        #if os(macOS)
        if let flag = env["FICHERO_FORCE_INMEMORY"], isTruthy(flag) {
            return .inMemory
        }
        #endif
        if let socketPath = env["FICHERO_FORCE_UDS_PATH"], !socketPath.isEmpty {
            return .uds(path: socketPath)
        }
        // Path-free UDS: the app computes its own container socket path (the same
        // one the dev pre-action binds), so the Dev Local scheme can request UDS
        // with a plain `FICHERO_FORCE_UDS=1` and never hardcode a per-user path.
        if let flag = env["FICHERO_FORCE_UDS"], isTruthy(flag) {
            return .uds(path: udsSocketPath)
        }
        return nil
    }

    /// Treats common truthy spellings ("1", "true", "yes", "on") as enabled so
    /// `FICHERO_FORCE_INMEMORY=1` and `=true` both work; anything else is off.
    private static func isTruthy(_ value: String) -> Bool {
        ["1", "true", "yes", "on"].contains(value.trimmingCharacters(in: .whitespaces).lowercased())
    }

    // MARK: - Mac launch connection mode (#2381)

    /// How a macOS launch should establish its engine connection.
    ///
    /// A normal launch uses the embedded local engine — backend URL/debug
    /// fields stay out of regular Settings. Holding Option at launch instead
    /// exposes the explicit remote-client connection flow (scan/paste a host
    /// pairing link) for connecting this Mac to another Fichero host.
    enum MacLaunchConnectionMode: Equatable {
        /// Start the embedded local engine (the default for a normal launch).
        case embeddedLocal
        /// Present the remote-client connection chooser (Option held at launch).
        case remoteConnectionChooser
    }

    /// Pure launch-mode decision, dependency-injected so it can be unit-tested
    /// without AppKit or a real launch.
    ///
    /// - `optionKeyHeld`: was Option down as the app launched.
    /// - `isInteractiveLaunch`: false for Xcode Previews / Playgrounds / UI-test
    ///   / XCTest hosts, which drive the app non-interactively and must never
    ///   pop the chooser. The chooser only appears for a deliberate Option-held
    ///   interactive launch.
    static func macLaunchConnectionMode(
        optionKeyHeld: Bool,
        isInteractiveLaunch: Bool
    ) -> MacLaunchConnectionMode {
        guard isInteractiveLaunch, optionKeyHeld else {
            return .embeddedLocal
        }
        return .remoteConnectionChooser
    }

    #if os(macOS)
    /// True when Option is currently held — a snapshot of AppKit's modifier
    /// flags read once at launch. Isolated here so `macLaunchConnectionMode`
    /// above stays a pure, AppKit-free, unit-testable decision.
    static func optionKeyHeldAtLaunch() -> Bool {
        NSEvent.modifierFlags.contains(.option)
    }
    #endif

    // MARK: - Engine provisioning strategy (#3109)

    /// How a launch obtains its engine — decided ONCE from explicit inputs
    /// instead of re-derived from scattered `#if DEBUG` / `usesCustomHost` /
    /// preview conditionals. `EmbeddedBackendService.start()` and both app
    /// entries consume this rather than each re-deciding (#2861/#3042).
    ///
    /// The future iOS in-process embed (#2865) slots in here as one more case;
    /// the seam is deliberate — do NOT implement it yet.
    enum EngineProvisioningStrategy: Equatable {
        /// Previews / XCTest host / UI-test: adopt an external engine if one is
        /// already up, else run inert. NEVER spawn or manage a lifecycle.
        case inert
        /// An explicit configured host (Settings), macOS or iOS: connect to it,
        /// never spawn a local engine.
        case configuredRemote
        /// iOS paired companion (or first-run setup): a remote host, no local
        /// engine ever (#2465 — never probe localhost).
        case iosCompanion
        /// macOS Debug: adopt a developer-run engine on :8765. The engine is
        /// deliberately NOT bundled in Debug (#3042), so this never spawns — if
        /// nothing is up it fails with the actionable start_backend.sh message.
        case debugExternal
        /// macOS Release: spawn the bundled engine, app-authoritative token
        /// (#2862). The only strategy that spawns and manages a lifecycle.
        case releaseEmbedded

        /// True only for the one strategy that spawns the bundled engine
        /// subprocess. Debug/remote/inert all adopt an engine they didn't spawn.
        var spawnsBundledEngine: Bool { self == .releaseEmbedded }

        /// True when startup connects to an explicit/remote host instead of a
        /// local engine — the old `requiresExternalBackendConnection` branch the
        /// app entries used.
        var connectsToRemoteHost: Bool {
            self == .configuredRemote || self == .iosCompanion
        }
    }

    /// Pure, dependency-injected provisioning decision so every input
    /// combination is unit-testable without a real launch, AppKit, or a build
    /// flag. Precedence: inert host → explicit configured host → platform
    /// default (iOS companion; macOS Debug-external / Release-embedded).
    static func engineProvisioningStrategy(
        _ inputs: EngineProvisioningInputs
    ) -> EngineProvisioningStrategy {
        if inputs.isInertHost { return .inert }
        guard inputs.isMacOS else {
            // iOS never runs a local engine. A valid Settings host →
            // configuredRemote; otherwise the paired companion / first-run setup.
            return inputs.hasExplicitConfiguredHost ? .configuredRemote : .iosCompanion
        }
        // macOS: a configured (or malformed) remote host wins over the local
        // engine, matching `requiresExternalBackendConnection`.
        if inputs.hostRequiresRemoteConnection { return .configuredRemote }
        return inputs.isDebugBuild ? .debugExternal : .releaseEmbedded
    }

    /// The explicit inputs the provisioning decision reads. Captured as a value
    /// so tests can enumerate every combination.
    struct EngineProvisioningInputs: Equatable {
        /// This platform runs a local engine (macOS true, iOS false).
        let isMacOS: Bool
        /// Compiled for Debug (the engine isn't bundled, #3042).
        let isDebugBuild: Bool
        /// Preview / XCTest host / UI-test — drive the app non-interactively.
        let isInertHost: Bool
        /// A configured OR malformed host is set (`requiresExternalBackendConnection`).
        let hostRequiresRemoteConnection: Bool
        /// A VALID `.configured` host is set (`hasConfiguredHost`) — distinguishes
        /// an iOS Settings host (configuredRemote) from a paired companion.
        let hasExplicitConfiguredHost: Bool
    }

    /// The live provisioning strategy — reads the real platform, build config,
    /// launch environment, and saved host. Impure boundary around the pure
    /// `engineProvisioningStrategy(_:)`, mirroring `optionKeyHeldAtLaunch`.
    static func engineProvisioningStrategy() -> EngineProvisioningStrategy {
        engineProvisioningStrategy(currentEngineProvisioningInputs())
    }

    static func currentEngineProvisioningInputs() -> EngineProvisioningInputs {
        let env = ProcessInfo.processInfo.environment
        let isPreview = env["XCODE_RUNNING_FOR_PREVIEWS"] == "1"
            || env["XCODE_RUNNING_FOR_PLAYGROUNDS"] == "1"
        return EngineProvisioningInputs(
            isMacOS: allowsEmbeddedLocalDefault,
            isDebugBuild: isDebugBuild,
            isInertHost: isPreview || isRunningXCTests() || (isUITesting() && !isEmbeddedEngineUITesting()),
            hostRequiresRemoteConnection: requiresExternalBackendConnection,
            hasExplicitConfiguredHost: hasConfiguredHost
        )
    }

    private static var isDebugBuild: Bool {
        #if DEBUG
        return true
        #else
        return false
        #endif
    }

    // MARK: - Engine transport selection (UDS for the embedded engine)

    /// The AF_UNIX socket the embedded (`.releaseEmbedded`) engine binds and the
    /// app client dials over UDS. Kept SHORT and stable to stay well under the
    /// ~104-byte `sun_path` limit (`struct sockaddr_un`) that a longer path would
    /// overflow. Lives in Application Support so it is per-user and survives
    /// launches; the parent `Fichero/` dir is created 0700 if missing. This one
    /// path is shared by the client transport (`transportMode`) and the engine
    /// spawn env (`FICHERO_UDS_PATH`), so both ends agree on the socket.
    static var udsSocketPath: String {
        // Must fit the AF_UNIX `sun_path` limit (~104 bytes on macOS). In the App
        // Store sandbox the container prefix (~/Library/Containers/<id>/Data/) is
        // already ~62 bytes, so the old `…/Library/Application Support/Fichero/
        // engine.sock` (+47) overflowed at ~109. The container `tmp` (a) is always
        // writable in the sandbox, (b) is short, and (c) is shared with the
        // sandbox-inherited engine subprocess — so a short name there stays well
        // under the limit. The engine gets the exact absolute path via env.
        let dir = NSTemporaryDirectory() as NSString
        let path = dir.appendingPathComponent("fichero.sock")
        // Fail loud rather than silently binding a truncated path: if even this is
        // over the limit (pathological container prefix), that's a real bug.
        assert(path.utf8.count <= 104, "UDS socket path exceeds sun_path limit: \(path)")
        return path
    }

    /// Pure strategy → transport mapping, dependency-injected so all five cases
    /// are unit-testable without a real launch. Only `.releaseEmbedded` (the
    /// bundled-engine spawn) binds a UDS, so only it dials one; every other
    /// strategy keeps the existing HTTPS path unchanged.
    static func transportMode(for strategy: EngineProvisioningStrategy) -> TransportMode {
        switch strategy {
        case .releaseEmbedded:
            return .uds(path: udsSocketPath)
        case .debugExternal, .configuredRemote, .iosCompanion, .inert:
            return .https
        }
    }

    // MARK: - iOS companion launch phase (#3113)

    /// The phase an iOS launch/reconnect resolves to. iOS has no local engine,
    /// so the only three honest outcomes are: first-run pairing, connected, or a
    /// configured-but-down host — never a blank screen, never localhost (#2465).
    enum IOSLaunchPhase: Equatable {
        /// No paired library yet — show `RemoteConnectionSetupView` (first-run).
        case setupNeeded
        /// Paired host reachable and authenticated — render the workspace.
        case ready
        /// Paired host configured but not answering — show the diagnosis, NEVER
        /// the pairing prompt (the #2807/#2864 invariant).
        case unreachable
    }

    /// Pure iOS launch-phase decision, dependency-injected so every
    /// (paired?, reachable?) combination is unit-testable without a real probe —
    /// same shape as `engineProvisioningStrategy`. The live `reconnectToConfiguredHost`
    /// boundary reads `RemoteAccessConfig.hasPairedLibraryPath` for `hasPairedLibrary`
    /// and the readiness probe for `isReachable`.
    ///
    /// An unpaired install is `setupNeeded` regardless of reachability — iOS
    /// must NEVER probe localhost (#2465), so a fresh install shows first-run
    /// setup instead of a pointless probe-then-unreachable flash.
    static func iosLaunchPhase(
        hasPairedLibrary: Bool,
        isReachable: Bool
    ) -> IOSLaunchPhase {
        guard hasPairedLibrary else { return .setupNeeded }
        return isReachable ? .ready : .unreachable
    }
}
