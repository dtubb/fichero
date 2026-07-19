import SwiftUI

// MARK: - Per-view settings panes (#3680)

/// Library View settings — the app-wide default library layout. Reuses the
/// existing `ViewSettings.libraryLayout`; nothing new stored.
struct LibraryViewSettingsPane: View {
    @Environment(ViewSettings.self) private var viewSettings

    var body: some View {
        @Bindable var settings = viewSettings
        Form {
            Section("Layout") {
                Picker("Default layout", selection: $settings.libraryLayout) {
                    ForEach(LibraryLayout.allCases, id: \.self) { layout in
                        Label(layout.rawValue, systemImage: layout.icon).tag(layout)
                    }
                }
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Library")
    }
}

/// Preview View settings — where the document preview sits (the Mail-vocabulary
/// `PreviewLayout` facade over `ViewSettings.previewMode`). A distinct surface
/// from the Reader (kept separate per the reader-IA decision).
struct PreviewViewSettingsPane: View {
    @Environment(ViewSettings.self) private var viewSettings

    var body: some View {
        @Bindable var settings = viewSettings
        Form {
            Section("Layout") {
                Picker("Preview position", selection: Binding(
                    get: { settings.previewMode.layout },
                    set: { settings.previewMode = $0.previewMode }
                )) {
                    Text("Side").tag(PreviewLayout.side)
                    Text("Bottom").tag(PreviewLayout.bottom)
                    Text("Hidden").tag(PreviewLayout.hidden)
                }
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Preview")
    }
}

/// Reader View settings — the Reader text font-size override (#3681). A stepper
/// over the semantic base size, clamped `0.8…2.0` (the maintainer). The consumer wiring
/// (WebKit CSS injection + native reader text) lands with #3681; this is the
/// control + storage. Reader theme follows the app's semantic light/dark only —
/// Sepia/Paper is deferred.
struct ReaderViewSettingsPane: View {
    @AppStorage(ViewSettings.FontScale.readerKey)
    private var readerScale = ViewSettings.FontScale.defaultValue
    @AppStorage(ReaderTextWrap.storageKey)
    private var textWrap = ReaderTextWrap.tidy
    @AppStorage(TranscriptLayout.storageKey)
    private var transcriptLayout = TranscriptLayout.defaultValue

    var body: some View {
        Form {
            Section("Transcript") {
                Picker("Layout", selection: $transcriptLayout) {
                    ForEach(TranscriptLayout.allCases) { layout in
                        Text(layout.label).tag(layout)
                    }
                }
                Text("Diplomatic keeps the manuscript's original line breaks — that "
                     + "line structure is real data. Reading reflows the text to fit "
                     + "the window: easier to read, but the manuscript lines are lost. "
                     + "Diplomatic is the default; Reading is opt-in.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Text") {
                Stepper(
                    value: $readerScale,
                    in: ViewSettings.FontScale.range,
                    step: ViewSettings.FontScale.step
                ) {
                    LabeledContent("Font size", value: ViewSettings.FontScale.percentLabel(readerScale))
                }
                Text("Scales the Reader text relative to the system default. The Editor is set separately.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Paragraphs") {
                Picker("Wrapping", selection: $textWrap) {
                    ForEach(ReaderTextWrap.allCases) { mode in
                        Text(mode.label).tag(mode)
                    }
                }
                Text("“Tidy” avoids a single word stranded on a paragraph's last line.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Reader")
    }
}

/// Inspector settings — the Editor text font-size override (#3682), SEPARATE
/// from the Reader (the maintainer). Stepper over the semantic base, clamped `0.8…2.0`.
/// The consumer wiring (Inspector editable text surfaces) lands with #3682.
struct InspectorViewSettingsPane: View {
    @AppStorage(ViewSettings.FontScale.editorKey)
    private var editorScale = ViewSettings.FontScale.defaultValue

    var body: some View {
        Form {
            Section("Editor Text") {
                Stepper(
                    value: $editorScale,
                    in: ViewSettings.FontScale.range,
                    step: ViewSettings.FontScale.step
                ) {
                    LabeledContent("Font size", value: ViewSettings.FontScale.percentLabel(editorScale))
                }
                Text("Scales the Inspector's editable text relative to the system default — separate from the Reader.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Inspector")
    }
}

// MARK: - Integrations (placeholder)

struct IntegrationsSettingsView: View {
    let showAutomationRules: Bool

    var body: some View {
        Form {
            Section {
                IntegrationsPlaceholderContent(
                    title: "Folder Watchers",
                    description: "Automatically process files when added to watched folders.",
                    icon: "folder.badge.gearshape"
                )
            }

            Section {
                IntegrationsPlaceholderContent(
                    title: "App Observers",
                    description: "Trigger workflows based on app events, like files saved from specific apps.",
                    icon: "app.badge"
                )
            }

            if showAutomationRules {
                Section {
                    IntegrationsPlaceholderContent(
                        title: "Automation Rules",
                        description: "Create rules to automatically organize and process documents.",
                        icon: "gearshape.2"
                    )
                }
            }
        }
        .formStyle(.grouped)
    }
}
