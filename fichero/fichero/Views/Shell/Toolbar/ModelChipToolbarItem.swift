import OSLog
import SwiftUI

private let logger = Logger(
    subsystem: "app.fichero.fichero",
    category: "ModelChip"
)

/// The model a run would actually use, in the toolbar beside the selection
/// (Daniel, 2026-08-28: the island says what is selected, so the default model
/// belongs to its left).
///
/// Fichero had NO visible statement of which model it was about to call. When
/// the `$vision_small` alias silently resolved to a broken provider prefix
/// (2026-08-27) there was no surface on which that could have been noticed —
/// the run simply produced worse results. This is that surface.
///
/// The chip is CONTEXTUAL, not a single global default: a page selection
/// resolves the vision tier, anything else resolves the text tier, because
/// that is the one a run on this selection would really use. Showing one fixed
/// "default model" would be a different kind of lie.
struct ModelChipToolbarItem: View {
    /// True when the current selection would be handled by a vision model.
    let prefersVision: Bool
    @Environment(AppState.self) private var appState
    /// SwiftUI's own settings action — no AppKit bridge, so this file stays
    /// inside the cross-platform rule (check_appkit_imports).
    @Environment(\.openSettings) private var openSettings
    /// Fetched rather than injected: nothing holds AI defaults in a shared
    /// observable today, so the chip loads its own copy and refreshes when the
    /// menu opens — which is the moment its accuracy matters.
    @State private var defaults = AIDefaults()
    /// True when the last fetch FAILED, as distinct from a genuinely unset
    /// tier — the chip must not report an engine problem as a user one.
    @State private var loadFailed = false

    var body: some View {
        Menu {
            Section("This selection would use") {
                Label(displayModel, systemImage: prefersVision ? "eye" : "text.alignleft")
            }
            Divider()
            Section("Tiers") {
                tierRow("Vision", defaults.visionMediumModel, defaults.visionMediumProvider)
                tierRow("Text", defaults.mediumModel, defaults.mediumProvider)
            }
            Divider()
            Button("AI Settings…") { openSettings() }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "cpu")
                    .font(.caption)
                Text(shortModel)
                    .font(.caption)
                    .lineLimit(1)
            }
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .task { await reload() }
        .onTapGesture { Task { await reload() } }
        .help("\(prefersVision ? "Vision" : "Text") model for this selection: \(displayModel)")
        .accessibilityLabel("Model: \(displayModel)")
    }

    private func reload() async {
        // Retry until it lands. The first attempt fires at window open, which
        // routinely LOSES a race with the engine coming up — and a single
        // silent `try?` then left the chip reading "No model set" forever over
        // a perfectly configured install (Daniel, 2026-08-28). That is the same
        // shape as the Reader's poisoned cache key: a failure that cannot
        // retry itself is indistinguishable from a real absence.
        //
        // Bounded, because "not set" IS a legitimate answer and must not spin.
        for attempt in 0..<6 {
            do {
                defaults = try await appState.fetchAIDefaults()
                loadFailed = false
                return
            } catch {
                loadFailed = true
                logger.warning("AI defaults load attempt \(attempt + 1) failed: \(String(describing: error))")
                try? await Task.sleep(for: .seconds(Double(attempt + 1)))
            }
        }
    }

    @ViewBuilder
    private func tierRow(_ name: String, _ model: String, _ provider: String) -> some View {
        // Stated, never silently blank: an unconfigured tier is exactly the
        // condition that produced a broken run with no visible cause.
        Text(model.isEmpty ? "\(name): not set" : "\(name): \(Self.shorten(model))")
    }

    /// The model the run resolves to, or an honest admission that no tier is set.
    private var displayModel: String {
        let model = prefersVision ? defaults.visionMediumModel : defaults.mediumModel
        if !model.isEmpty { return model }
        // Distinguish "the engine did not answer" from "you have not chosen".
        // Reporting the first as the second sent a user to Settings to fix
        // something that was already configured.
        return loadFailed ? "Model unavailable" : "No model set"
    }

    private var shortModel: String { Self.shorten(displayModel) }

    /// `openrouter/anthropic/claude-sonnet-5` reads as `claude-sonnet-5` — the
    /// provider path is noise in a toolbar and the tooltip carries it in full.
    static func shorten(_ model: String) -> String {
        model.split(separator: "/").last.map(String.init) ?? model
    }
}
