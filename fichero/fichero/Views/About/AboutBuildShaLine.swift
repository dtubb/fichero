import SwiftUI

extension AboutInfo {
    /// "Build 2b9b216c34": the commit the app was built from (`FicheroBuildSHA`, stamped at embed time by
    /// `stamp_engine_version_into_app.sh`); nil when the bundle carries none or "unknown", so the box never prints a blank build.
    static func buildShaLine(_ sha: String?) -> String? {
        guard displayValue(sha) != "—", sha?.trimmingCharacters(in: .whitespacesAndNewlines) != "unknown" else { return nil }
        return "Build \(displayValue(sha))"
    }
}

/// The About box's build line (#6474), so a screenshot or a crash can be tied to the build that ran.
struct AboutBuildShaLine: View {
    var body: some View {
        if let line = AboutInfo.buildShaLine(Bundle.main.infoDictionary?["FicheroBuildSHA"] as? String) {
            Text(line)
                .font(.callout.monospaced())
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
                .accessibilityIdentifier("about.buildSha")
        }
    }
}
