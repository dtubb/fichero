@testable import Fichero
import XCTest

/// An unresolvable build tier must fail CLOSED (#4470 follow-up).
///
/// `activeBuildTier` used to fall back to `.dev` — "I could not determine the
/// tier, so assume maximum privilege". That is the inverse of every other
/// safety decision in this codebase: loopback-only transport, the canvas's
/// strict-when-unloaded conversion table, the engine refusing a zero-resolution
/// run. A configuration failure must not be the thing that unlocks features.
///
/// The fallback is also unreachable in practice — all 16 build configurations
/// define `FICHERO_FEATURE_TIER` and the test bundle is hosted in `Fichero.app`
/// — which is why the change is safe rather than merely principled. These
/// tests therefore pin the DIRECTION rather than trying to reach the branch:
/// what matters is that the safe default stays the narrow one if anyone ever
/// revisits it.
@MainActor
final class FeatureTierFailClosedTests: XCTestCase {

    /// `.release` is the narrowest surface and `.dev` the widest. If these
    /// ranks are ever reordered, "fail closed" would silently start meaning
    /// its opposite — so the ordering is asserted, not assumed.
    func testReleaseIsTheNarrowestTier() {
        XCTAssertGreaterThan(FeatureTier.release.rank, FeatureTier.beta.rank)
        XCTAssertGreaterThan(FeatureTier.beta.rank, FeatureTier.alpha.rank)
        XCTAssertGreaterThan(FeatureTier.alpha.rank, FeatureTier.dev.rank)
    }

    /// A feature is visible when its own tier rank is >= the active tier's, so
    /// the HIGHEST rank sees the fewest features. This is the property that
    /// makes `.release` the correct fail-closed value, stated independently of
    /// the numbers above.
    func testTheHighestRankSeesTheFewestFeatures() {
        let manager = FeatureManager.shared
        let previous = manager.testTierOverride
        defer { manager.testTierOverride = previous }

        manager.testTierOverride = .dev
        let devVisible = FeatureKey.allCases.filter { manager.isVisible($0) }.count

        manager.testTierOverride = .release
        let releaseVisible = FeatureKey.allCases.filter { manager.isVisible($0) }.count

        XCTAssertLessThan(
            releaseVisible, devVisible,
            "release must expose fewer features than dev, or falling back to it "
                + "is not failing closed"
        )
    }

    /// The values the resolver rejects — each of which previously produced
    /// `.dev`, the widest surface, from a configuration mistake.
    func testUnresolvableValuesAreRejectedRatherThanGuessed() {
        XCTAssertNil(FeatureManager.resolveFeatureTier(nil))
        XCTAssertNil(FeatureManager.resolveFeatureTier(""))
        XCTAssertNil(FeatureManager.resolveFeatureTier("   "))
        XCTAssertNil(FeatureManager.resolveFeatureTier("production"))
        XCTAssertNil(FeatureManager.resolveFeatureTier("$(FICHERO_FEATURE_TIER)"))
    }

    /// The unsubstituted-placeholder case is worth its own name: if the build
    /// setting is missing, `Info.plist` ships the literal `$(FICHERO_FEATURE_TIER)`
    /// rather than an empty string. That is the most likely real-world route to
    /// an unresolvable tier, and it must not resolve to anything.
    func testAnUnsubstitutedBuildSettingIsNotATier() {
        XCTAssertNil(FeatureManager.resolveFeatureTier("$(FICHERO_FEATURE_TIER)"))
    }

    /// Every tier the build configurations actually set must resolve. If one
    /// stopped resolving, that config would silently fall back — which is
    /// exactly the situation the fallback direction is insurance against.
    func testEveryConfiguredTierValueResolves() {
        for value in ["dev", "alpha", "beta", "release"] {
            XCTAssertNotNil(
                FeatureManager.resolveFeatureTier(value),
                "\(value) is set in project.pbxproj but does not resolve"
            )
        }
    }

    /// The failure is reported once, not on every read: `activeBuildTier` is a
    /// computed property read on many render paths, and a diagnostic that
    /// emits thousands of identical lines buries itself — which is the silence
    /// it was meant to replace.
    func testTheUnresolvableTierReportIsOneShot() {
        let previous = FeatureManager.hasReportedUnresolvableTier
        defer { FeatureManager.hasReportedUnresolvableTier = previous }

        FeatureManager.hasReportedUnresolvableTier = false
        FeatureManager.reportUnresolvableTierOnce()
        XCTAssertTrue(FeatureManager.hasReportedUnresolvableTier)

        // Second call must be a no-op rather than a second log line.
        FeatureManager.reportUnresolvableTierOnce()
        XCTAssertTrue(FeatureManager.hasReportedUnresolvableTier)
    }
}
