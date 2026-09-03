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

    static func engineVersionLine(_ version: String?) -> String? {
        guard displayValue(version) != "—" else { return nil }
        return "Server \(dateStyleVersion(displayValue(version)))"
    }

    /// The engine wears PEP 440 ("2026.9.3" — no leading zeros allowed), the
    /// app wears the display form ("2026.09.03"). One About box must not show
    /// the same release as two different-looking versions (Daniel,
    /// 2026-09-02), so the engine's dotted date is re-padded for display.
    /// Non-date-shaped versions pass through untouched.
    static func dateStyleVersion(_ version: String) -> String {
        let core = version.split(separator: "b").first.map(String.init) ?? version
        let parts = core.split(separator: ".").map(String.init)
        guard parts.count >= 3, parts.allSatisfy({ Int($0) != nil }),
              parts[0].count == 4 else { return version }
        let month = parts[1].count == 1 ? "0" + parts[1] : parts[1]
        let day = parts[2].count == 1 ? "0" + parts[2] : parts[2]
        var padded = "\(parts[0]).\(month).\(day)"
        if parts.count > 3 { padded += "." + parts[3...].joined(separator: ".") }
        if version.contains("b"), let beta = version.split(separator: "b").last {
            padded += "-beta\(beta == "1" ? "" : ".\(beta)")"
        }
        return padded
    }

    static func copyrightLine(bundleValue: String?, fallback: String) -> String {
        displayValue(bundleValue) == "—" ? fallback : displayValue(bundleValue)
    }
}

struct Acknowledgement: Identifiable, Hashable {
    let name: String
    let license: String
    let url: URL

    var id: String { name }
}

enum AboutLinks {
    static let repository = URL(string: "https://github.com/dtubb/fichero")!
    static let license = URL(string: "https://github.com/dtubb/fichero/blob/main/LICENSE")!
}

enum AboutAcknowledgements {
    static let entries: [Acknowledgement] = [
        Acknowledgement(name: "DuckDB", license: "MIT License", url: URL(string: "https://duckdb.org")!),
        Acknowledgement(name: "FastAPI", license: "MIT License", url: URL(string: "https://fastapi.tiangolo.com")!),
        Acknowledgement(name: "LanceDB", license: "Apache License 2.0", url: URL(string: "https://lancedb.com")!),
        Acknowledgement(name: "LangChain", license: "MIT License", url: URL(string: "https://www.langchain.com")!),
        Acknowledgement(name: "LangGraph", license: "MIT License", url: URL(string: "https://langchain-ai.github.io/langgraph")!),
        Acknowledgement(name: "Pydantic", license: "MIT License", url: URL(string: "https://docs.pydantic.dev")!),
        Acknowledgement(name: "Sparkle", license: "MIT License", url: URL(string: "https://sparkle-project.org")!)
    ]
}

struct AboutView: View {
    @Environment(AppState.self) private var appState
    @State private var isAcknowledgementsPresented = false

    private let appName = "Fichero"
    // The website's sentence (Daniel, 2026-09-02: the About box should
    // reflect the description on the site).
    private let tagline = "Read, search, and use AI with archives & research "
        + "material — transcribe handwritten documents, organize sources, and "
        + "generate structured data from your collections."
    private let credit = "Creative Direction by Daniel Tubb. Coding by AI."
    // AGPL-3.0, not MIT (2026-09-02 license audit): the repo LICENSE is the
    // GNU AGPL-3.0 and CONTRIBUTING/LICENSING.md say so — the About box was
    // the one place still claiming MIT.
    private let fallbackCopyright = "© 2025–2026 Daniel Tubb · AGPL-3.0"

    private var versionLine: String {
        AboutInfo.versionLine(
            shortVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String,
            build: Bundle.main.infoDictionary?["CFBundleVersion"] as? String
        )
    }

    private var engineVersionLine: String? {
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

            if let engineVersionLine {
                Text(engineVersionLine)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }

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

            HStack(spacing: 12) {
                Link("Fichero on GitHub", destination: AboutLinks.repository)
                Link("MIT License", destination: AboutLinks.license)
                Button("Acknowledgements") {
                    isAcknowledgementsPresented = true
                }
            }
            .font(.caption)
        }
        .padding(28)
        .frame(width: 360)
        .frame(minHeight: 360)
        .sheet(isPresented: $isAcknowledgementsPresented) {
            AcknowledgementsView(entries: AboutAcknowledgements.entries)
        }
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

private struct AcknowledgementsView: View {
    let entries: [Acknowledgement]

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List(entries) { acknowledgement in
                Link(destination: acknowledgement.url) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(acknowledgement.name)
                            .font(.body.weight(.medium))
                        Text(acknowledgement.license)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Acknowledgements")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
        .frame(minWidth: 320, minHeight: 360)
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
