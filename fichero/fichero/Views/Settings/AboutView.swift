import SwiftUI

/// Standard About window (#2557): app icon, name, version + build, a tagline,
/// and credits / license. All copy lives in one place at the top so it's easy to
/// refine without touching layout.
///
/// NOTE (#2557): the tagline below is CONSTITUTION-derived — the exact
/// "literary-carpentry" wording the maintainer referenced wasn't present in the legacy
/// archive when this shipped, so confirm/replace it. Version + build read live
/// from the bundle (MARKETING_VERSION / CURRENT_PROJECT_VERSION).
/// Pure formatting for the About window (#2557), factored out of the view so it
/// is unit-testable without a bundle.
enum AboutInfo {
    private static func displayValue(_ value: String?) -> String {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty else {
            return "—"
        }
        return trimmed
    }

    /// The "Version X (build)" line from the bundle's short version + build
    /// number, with an em-dash fallback for a missing/absent key.
    static func versionLine(shortVersion: String?, build: String?) -> String {
        "Version \(displayValue(shortVersion)) (\(displayValue(build)))"
    }

    static func engineVersionLine(_ version: String?) -> String {
        "Engine \(displayValue(version))"
    }

    static func copyrightLine(bundleValue: String?, fallback: String) -> String {
        displayValue(bundleValue) == "—" ? fallback : displayValue(bundleValue)
    }
}

struct AboutView: View {
    @Environment(AppState.self) private var appState

    private let appName = "Fichero"
    private let tagline = "A document workbench for researchers — read, organize, "
        + "search, and make things from your sources."
    private let credit = "Created by Daniel Tubb"
    private let fallbackCopyright = "© 2025 Daniel Tubb · MIT License"

    private var versionLine: String {
        AboutInfo.versionLine(
            shortVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String,
            build: Bundle.main.infoDictionary?["CFBundleVersion"] as? String
        )
    }

    private var engineVersionLine: String {
        AboutInfo.engineVersionLine(appState.backendVersion)
    }

    private var copyrightLine: String {
        AboutInfo.copyrightLine(
            bundleValue: Bundle.main.infoDictionary?["NSHumanReadableCopyright"] as? String,
            fallback: fallbackCopyright
        )
    }

    var body: some View {
        VStack(spacing: 12) {
            appIcon
                .frame(width: 96, height: 96)
                .accessibilityHidden(true)

            Text(appName)
                .font(.title.weight(.semibold))

            Text(versionLine)
                .font(.callout)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)

            Text(engineVersionLine)
                .font(.callout)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)

            Text(tagline)
                .font(.body)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Divider()
                .padding(.horizontal, 40)

            VStack(spacing: 4) {
                Text(credit)
                    .font(.callout)
                Text(copyrightLine)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .textSelection(.enabled)
        }
        .padding(28)
        .frame(width: 360)
        .frame(minHeight: 360)
    }

    @ViewBuilder
    private var appIcon: some View {
        #if os(macOS)
        // The real app icon, straight from the running app — no asset-name coupling.
        Image(nsImage: NSApp.applicationIconImage)
            .resizable()
            .aspectRatio(contentMode: .fit)
        #else
        // The real bundled app icon (#3236): the highest-resolution
        // CFBundleIconFiles entry. Falls back to a symbol only if resolution fails.
        if let name = Self.appIconAssetName(from: Bundle.main.infoDictionary),
           let uiImage = UIImage(named: name) {
            Image(uiImage: uiImage)
                .resizable()
                .aspectRatio(contentMode: .fit)
        } else {
            Image(systemName: "books.vertical.fill")
                .resizable()
                .aspectRatio(contentMode: .fit)
                .foregroundStyle(.tint)
        }
        #endif
    }

    /// The largest bundled app-icon asset name from an Info.plist `CFBundleIcons`
    /// dictionary — the last `CFBundleIconFiles` entry is the highest resolution
    /// (#3236). Pure + static so it is testable without a live bundle.
    static func appIconAssetName(from infoDictionary: [String: Any]?) -> String? {
        guard let icons = infoDictionary?["CFBundleIcons"] as? [String: Any],
              let primary = icons["CFBundlePrimaryIcon"] as? [String: Any],
              let files = primary["CFBundleIconFiles"] as? [String],
              let name = files.last, !name.isEmpty else {
            return nil
        }
        return name
    }
}

#if os(macOS)
/// Menu button that opens the About window (#2557). A small View so it can own
/// its own `openWindow` environment inside the app's `.commands`.
struct AboutWindowMenuButton: View {
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Button("About Fichero") {
            openWindow(id: "about")
        }
    }
}
#endif

#Preview {
    AboutView()
        .environment(AppState())
}
