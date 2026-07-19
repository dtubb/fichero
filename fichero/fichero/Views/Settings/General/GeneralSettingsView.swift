import SwiftUI

// MARK: - General Settings

/// General application settings
struct GeneralSettingsView: View {
    @AppStorage("thumbnailSize") private var thumbnailSize: Double = 120
    @AppStorage("defaultImportMode") private var defaultImportMode: String = IngestMode.link.rawValue
    @AppStorage("autoExtractText") private var autoExtractText: Bool = true
    @AppStorage("autoCreateEmbeddings") private var autoCreateEmbeddings: Bool = true
    // #1869 — single on/off; key shared with WorkflowCompletionNotifier. Default ON.
    @AppStorage(WorkflowCompletionNotifier.enabledDefaultsKey) private var notificationsEnabled: Bool = true

    // Typography settings
    @AppStorage("editor.fontName") private var fontName: String = "System"
    @AppStorage("editor.fontSize") private var fontSize: Double = 14
    @AppStorage("editor.lineSpacing") private var lineSpacing: Double = 4
    @AppStorage("editor.marginHorizontal") private var marginH: Double = 16
    @AppStorage("editor.marginVertical") private var marginV: Double = 12

    private static let defaultFontName = "System"
    private static let defaultFontSize: Double = 14
    private static let defaultLineSpacing: Double = 4
    private static let defaultMarginH: Double = 16
    private static let defaultMarginV: Double = 12
    private static let defaultThumbnailSize: Double = 120

    var body: some View {
        Form {
            Section("Display") {
                Slider(value: $thumbnailSize, in: 80...200) {
                    Text("Thumbnail Size")
                }
            }

            Section("Typography") {
                fontPicker

                HStack {
                    Text("Font Size")
                    Spacer()
                    TextField("", value: $fontSize, format: .number)
                        .frame(width: 50)
                        .textFieldStyle(.roundedBorder)
                    Stepper("", value: $fontSize, in: 9...36, step: 1)
                        .labelsHidden()
                }

                Slider(value: $lineSpacing, in: 0...20, step: 1) {
                    Text("Line Spacing")
                }
            }

            Section("Margins") {
                Slider(value: $marginH, in: 0...80, step: 4) {
                    Text("Horizontal")
                }
                Slider(value: $marginV, in: 0...80, step: 4) {
                    Text("Vertical")
                }
            }

            Section("Import") {
                Picker("When adding files", selection: $defaultImportMode) {
                    Text(IngestMode.link.displayName).tag(IngestMode.link.rawValue)
                    Text(IngestMode.copy.displayName).tag(IngestMode.copy.rawValue)
                    Text(IngestMode.move.displayName).tag(IngestMode.move.rawValue)
                }
                Text(
                    (IngestMode(rawValue: defaultImportMode) ?? .link).description
                )
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            Section("Ingestion") {
                Toggle("Auto-extract text from documents", isOn: $autoExtractText)
                Toggle("Auto-create search embeddings", isOn: $autoCreateEmbeddings)
            }

            Section("Notifications") {
                Toggle("Notify when a workflow finishes", isOn: $notificationsEnabled)
                Text("Shows a system notification when a workflow run completes or fails.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section {
                Button("Reset to Defaults") {
                    fontName = Self.defaultFontName
                    fontSize = Self.defaultFontSize
                    lineSpacing = Self.defaultLineSpacing
                    marginH = Self.defaultMarginH
                    marginV = Self.defaultMarginV
                    thumbnailSize = Self.defaultThumbnailSize
                    autoExtractText = true
                    autoCreateEmbeddings = true
                }
            }
        }
        // `.formStyle(.grouped)` is the macOS idiomatic Settings-panel style —
        // gives labels a proper leading column, section headers styled as
        // grouped-form titles, and native insets. Without it, the default
        // `.automatic` style on macOS 14+ renders labels right-aligned against
        // an invisible column that pushes all content to the right half of
        // the window (#556). `.padding()` intentionally dropped — .grouped
        // provides its own insets.
        .formStyle(.grouped)
    }

    @ViewBuilder
    private var fontPicker: some View {
        Picker("Font", selection: $fontName) {
            Text("System Default").tag("System")
            Divider()
            ForEach(availableFonts, id: \.self) { name in
                Text(name).tag(name)
            }
        }
    }

    private var availableFonts: [String] {
        #if canImport(AppKit)
        let families = NSFontManager.shared.availableFontFamilies
        #elseif canImport(UIKit)
        let families = UIFont.familyNames
        #else
        let families: [String] = []
        #endif
        return families.sorted()
    }
}

#Preview("General Settings") {
    // Frame matches the runtime SettingsView window (680x520) so the
    // preview renders layout the way users actually see it.
    GeneralSettingsView()
        .frame(width: 680, height: 520)
}
