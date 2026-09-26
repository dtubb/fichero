import Foundation

/// Why this app and a remote engine cannot talk to each other (#5047, spec
/// `contract.runtime-compatibility`).
///
/// `backend_version` cannot answer this question: two builds can share a
/// contract, and one build can change it. Wire compatibility is decided by the
/// CONTRACT, and each end carries the identity of the contract document it was
/// built from — baked in, never recomputed at runtime.
///
/// Three distinct faults, because the remedies differ and the person reading the
/// refusal has to be able to tell them apart.
public enum ContractMismatch: Equatable, Sendable {
    /// The engine did not state a contract at all: too old to report one, or its
    /// generated identity is missing. "Cannot be verified", which under the
    /// design ruling refuses exactly as a known mismatch does — absence is never
    /// read as agreement.
    case engineDidNotStateContract

    /// Two builds from different days. Update the older side.
    case versionDiffers(app: String, engine: String)

    /// The same version published twice with different content — a release
    /// mistake, not a version skew, and updating to "the same version" will not
    /// fix it. Loud on its own terms, as the spec requires.
    case sameVersionDifferentContent(version: String, appSHA256: String, engineSHA256: String)

    /// Which side is behind, for a message that tells the person what to update.
    /// `nil` when there is nothing to order — no stated version, or equal
    /// versions differing only in content.
    public enum Side: Equatable, Sendable {
        case app
        case engine
    }

    public var olderSide: Side? {
        guard case .versionDiffers(let app, let engine) = self else { return nil }
        // Numeric comparison, so 2026.9.8 sorts BEFORE 2026.9.20 — a plain
        // lexicographic compare puts "2026.9.8" after it and would name the
        // wrong side as older, which is worse than naming neither.
        switch app.compare(engine, options: .numeric) {
        case .orderedAscending: return .app
        case .orderedDescending: return .engine
        case .orderedSame: return nil
        }
    }

    /// One short sentence naming the fault. The versions are always both named —
    /// a refusal that says only "incompatible" leaves the person with nothing to act on.
    public var headline: String {
        switch self {
        case .engineDidNotStateContract:
            return "This Mac can't confirm which Fichero version it's running"
        case .versionDiffers(let app, let engine):
            return "Fichero versions don't match: this device has \(app), the Mac has \(engine)"
        case .sameVersionDifferentContent(let version, _, _):
            return "Both sides say Fichero \(version), but they aren't the same build"
        }
    }

    public var detail: String {
        switch self {
        case .engineDidNotStateContract:
            return "The Mac is running a version of Fichero that's too old to check "
                + "compatibility. Update Fichero on the Mac, then connect again."
        case .versionDiffers(let app, let engine):
            switch olderSide {
            case .app:
                return "Update Fichero on this device to \(engine), then connect again."
            case .engine:
                return "Update Fichero on the Mac to \(app), then connect again."
            case nil:
                return "Update Fichero on both the Mac and this device, then connect again."
            }
        case .sameVersionDifferentContent:
            return "One of them was built from different code under the same version number. "
                + "Update both the Mac and this device to the same release, then connect again."
        }
    }
}

/// The connect-time compatibility check.
///
/// Pure, so the refusal decision is testable without an engine — the property
/// that matters most here, because a wrong answer either blocks every remote
/// connection or silently allows an incompatible one.
public enum ContractCompatibility {
    /// The app's own baked identity. Held here so tests can compare against an
    /// arbitrary pair without reaching for the generated constants.
    public static var appIdentity: (version: String, sha256: String) {
        (BakedContractIdentity.version, BakedContractIdentity.sha256)
    }

    /// `nil` means the two ends agree and the connection may proceed.
    ///
    /// Takes the OpenAPI-typed health field rather than loose strings, so a
    /// caller cannot transpose version and digest — impossible over checked.
    public static func mismatch(
        engine: Components.Schemas.ContractIdentity?,
        app: (version: String, sha256: String) = appIdentity
    ) -> ContractMismatch? {
        guard let engine else { return .engineDidNotStateContract }
        // Empty strings are an engine that answered without answering; treat
        // them as "did not state" rather than comparing "" to a real digest and
        // reporting a version mismatch against a blank version.
        let engineVersion = engine.version.trimmingCharacters(in: .whitespacesAndNewlines)
        let engineSHA = engine.sha256.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !engineVersion.isEmpty, !engineSHA.isEmpty else {
            return .engineDidNotStateContract
        }
        // The digest is the authority: same digest means the same document, so
        // the wire is compatible whatever else differs.
        guard engineSHA.caseInsensitiveCompare(app.sha256) != .orderedSame else { return nil }
        guard engineVersion == app.version else {
            return .versionDiffers(app: app.version, engine: engineVersion)
        }
        return .sameVersionDifferentContent(
            version: engineVersion,
            appSHA256: app.sha256,
            engineSHA256: engineSHA
        )
    }
}
