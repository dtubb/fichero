import SwiftUI

/// Standard About window (#2557): app icon, name, version + build, a tagline,
/// and credits / license. All copy lives in one place at the top so it's easy to
/// refine without touching layout.
///
/// NOTE (#2557): the tagline below is CONSTITUTION-derived — the exact
/// "literary-carpentry" wording Daniel referenced wasn't present in the legacy
/// archive when this shipped, so confirm/replace it. Version + build read live
/// from the bundle (MARKETING_VERSION / CURRENT_PROJECT_VERSION).
struct AboutView: View {
    private let appName = "Fichero"
    private let tagline = "A document workbench for researchers — read, organize, "
        + "search, and make things from your sources."
    private let credit = "Created by Daniel Tubb"
    private let copyright = "© 2025 Daniel Tubb · MIT License"

    private var version: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "—"
    }
    private var build: String {
        Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "—"
    }

    var body: some View {
        VStack(spacing: 12) {
            appIcon
                .frame(width: 96, height: 96)
                .accessibilityHidden(true)

            Text(appName)
                .font(.title.weight(.semibold))

            Text("Version \(version) (\(build))")
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
                Text(copyright)
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
        // ponytail: iOS reads its icon from the bundle differently; an SF Symbol
        // placeholder is fine until an iOS About surface (Settings) is wired.
        Image(systemName: "books.vertical.fill")
            .resizable()
            .aspectRatio(contentMode: .fit)
            .foregroundStyle(.tint)
        #endif
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
}
