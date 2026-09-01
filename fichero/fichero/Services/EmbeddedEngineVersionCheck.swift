import Foundation

/// Does the engine answering us match the engine this app shipped? (Daniel,
/// 2026-09-01.)
///
/// ## The failure this exists for
///
/// A `Fichero (Dev Embedded)` build printed `Embedded engine version: 2026.8.27`
/// from a checkout whose `fichero-server/pyproject.toml` had moved on, and
/// nothing anywhere said so — not the build, which was internally consistent,
/// and not the app, which never asked. The staged engine's version label is
/// written by `briefcase create` and NEVER refreshed by `briefcase update`, so a
/// hand-run `update -r` re-installs current code under a fossilised label. The
/// restage scripts now recreate the template when the label drifts; this type is
/// the second line — the one that catches a stale bundle that got embedded
/// anyway, and the one that runs on a user's machine where no script does.
///
/// ## What is compared
///
/// Three versions, from three independent places:
///   - **running** — `backend_version` from `GET /api/health`: the engine that
///     actually answered, resolved from its installed distribution metadata.
///   - **embedded** — `FicheroEmbeddedEngineVersion` in the app's `Info.plist`:
///     the `CFBundleShortVersionString` of the engine bundle the embed phase
///     copied. What is INSIDE this app.
///   - **expected** — `FicheroExpectedEngineVersion`: `version` from the
///     checkout's `fichero-server/pyproject.toml` at build time. What this app
///     SHOULD have got.
///
/// Both stamps are written by `scripts/stamp_engine_version_into_app.sh` from
/// the Xcode "Embed Fichero Server" phase, guarded by
/// `scripts/check_engine_version_stamp.py`.
///
/// The comparison is pure and lives here alone, so the ruling can be tested
/// without an engine, a bundle, or a window.
enum EmbeddedEngineVersionCheck {
    /// The two build-time stamps, as read from the app bundle.
    struct Stamps: Equatable {
        /// `FicheroEmbeddedEngineVersion` — the engine bundle actually copied.
        let embedded: String?
        /// `FicheroExpectedEngineVersion` — the checkout's engine version.
        let expected: String?

        init(embedded: String?, expected: String?) {
            self.embedded = embedded
            self.expected = expected
        }

        static let unstamped = Stamps(embedded: nil, expected: nil)
    }

    /// Info.plist keys. Named once, here, so the guard script and the stamping
    /// script can be checked against the same two literals.
    static let embeddedVersionKey = "FicheroEmbeddedEngineVersion"
    static let expectedVersionKey = "FicheroExpectedEngineVersion"

    enum Verdict: Equatable {
        /// Nothing to check: not an embedded engine, or health reported no
        /// version. A remote/dev-external engine legitimately runs its own
        /// version and is not this check's business.
        case notApplicable
        /// An embedded build carrying no stamps — the embed phase did not run
        /// or did not write them. The check is BLIND, which is not the same as
        /// clean: logged, never shown, because previews and unit hosts land
        /// here too and a banner there would be noise.
        case unstamped
        /// Running engine, embedded stamp and expected version all agree.
        case matches(String)
        /// They do not. `running` is what answered; `expected` is what this
        /// build should be talking to.
        case mismatch(running: String, expected: String)
    }

    /// The ruling. Pure.
    ///
    /// `isEmbedded` gates the whole check: only a build that ships its own
    /// engine can meaningfully claim which engine it *should* be talking to.
    ///
    /// A missing `expected` stamp falls back to `embedded` (and vice versa)
    /// rather than reporting a mismatch against an empty string — a half-stamped
    /// bundle is a stamping bug, not an engine mismatch, and must not accuse the
    /// engine of something the build got wrong.
    static func verdict(isEmbedded: Bool, reportedVersion: String?, stamps: Stamps) -> Verdict {
        guard isEmbedded else { return .notApplicable }
        guard let running = reportedVersion, !running.isEmpty else { return .notApplicable }
        let embedded = stamps.embedded.flatMap { $0.isEmpty ? nil : $0 }
        let expected = stamps.expected.flatMap { $0.isEmpty ? nil : $0 }
        guard let reference = expected ?? embedded else { return .unstamped }
        // Every known version must agree. Comparing only against `expected`
        // would miss the case the stamps exist to expose: an embed phase that
        // copied a stage older than the checkout it was built from.
        let known = [running, embedded ?? reference, reference]
        guard Set(known).count == 1 else {
            return .mismatch(running: running, expected: reference)
        }
        return .matches(running)
    }

    /// The user-facing sentence, or nil when there is nothing to say. One
    /// sentence, naming both versions and the remedy — the banner shows exactly
    /// this string.
    static func warning(for verdict: Verdict) -> String? {
        guard case .mismatch(let running, let expected) = verdict else { return nil }
        return "Embedded engine is \(running), app expected \(expected) — restage the engine."
    }

    /// Read the two stamps off a bundle. `Bundle.main` in the app; injectable so
    /// tests never touch the host bundle.
    static func stamps(from bundle: Bundle) -> Stamps {
        Stamps(
            embedded: bundle.object(forInfoDictionaryKey: embeddedVersionKey) as? String,
            expected: bundle.object(forInfoDictionaryKey: expectedVersionKey) as? String
        )
    }
}
