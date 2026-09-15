#if DEBUG
import SwiftUI

/// A lightweight, dependency-free rendering of the About window — the design-verification
/// surface for the About spec (`docs/contributor_manual/specs/ui/about.md`). It renders the
/// same composition the shipping `AboutView` draws (icon · name · version · server · tagline ·
/// credit · copyright · links), but from STATIC spec data through the pure `AboutInfo`
/// formatters, with **no `AppState`/backend boot** — so it renders instantly in the Xcode
/// canvas and via `ImageRenderer`, and is the SOURCE of the manuals' screenshots
/// (`docs/assets/about/`).
///
/// The real `AboutView` reads its icon from `NSApp.applicationIconImage` and its
/// version/server strings from the live bundle + health cache; this mirror substitutes an
/// SF Symbol and caller-supplied strings so the layout can be inspected without any of that.
/// `#if DEBUG` — never ships in Release.
struct AboutPreview: View {
    var appName = "Fichero"
    var shortVersion: String? = "2026.09.15"
    var build: String? = "2026091501"
    /// The engine version, in the PEP 440 form the health cache reports. `nil` omits the
    /// Server row — exactly as the shipping view does before the first health response and
    /// while disconnected (`AboutInfo.engineVersionLine`).
    var engineVersion: String? = "2026.9.15"
    var tagline = "Read, search, and use AI with archives & research material — "
        + "transcribe handwritten documents, organize sources, and generate "
        + "structured data from your collections."
    var credit = "Creative Direction by Daniel Tubb. Coding by AI."
    var copyright = "© 2025–2026 Daniel Tubb · AGPL-3.0"

    private var versionLine: String {
        AboutInfo.versionLine(shortVersion: shortVersion, build: build)
    }

    private var engineVersionLine: String? {
        AboutInfo.engineVersionLine(engineVersion)
    }

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "books.vertical.fill")
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 96, height: 96)
                .foregroundStyle(.tint)
                .accessibilityHidden(true)

            Text(appName)
                .font(.title.weight(.semibold))

            Text(versionLine)
                .font(.callout)
                .foregroundStyle(.secondary)

            if let engineVersionLine {
                Text(engineVersionLine)
                    .font(.callout)
                    .foregroundStyle(.secondary)
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
                Text(copyright)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 12) {
                Text("Fichero on GitHub")
                Text("AGPL-3.0 License")
                Text("Acknowledgements")
            }
            .font(.caption)
            .foregroundStyle(.tint)
        }
        .padding(28)
        .frame(width: 360)
        .frame(minHeight: 360)
    }
}

/// The acknowledgements sheet, rendered from the spec's own `AboutAcknowledgements.entries`
/// with a couple of sample live versions — dependency-light (no `AppState`), so the grouped
/// credits list is verifiable and screenshottable on its own.
struct AboutAcknowledgementsPreview: View {
    var body: some View {
        List {
            Section {
                Text("Fichero is built on the work of these open-source projects.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            ForEach(AckLayer.allCases, id: \.self) { layer in
                let layerEntries = AboutAcknowledgements.entries.filter { $0.layer == layer }
                if !layerEntries.isEmpty {
                    Section(layer.rawValue) {
                        ForEach(layerEntries) { entry in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(entry.name).font(.body.weight(.medium))
                                Text(entry.license)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
        .frame(width: 340, height: 520)
    }
}

#Preview("About — card") {
    AboutPreview()
}

#Preview("About — server row omitted") {
    AboutPreview(engineVersion: nil)
}

#Preview("About — acknowledgements") {
    AboutAcknowledgementsPreview()
}
#endif
