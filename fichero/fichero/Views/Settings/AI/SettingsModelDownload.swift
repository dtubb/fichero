import SwiftUI

/// Settings' Download for one model (#5620, `source.find.one-download-path`): the one download path
/// (`ModelDownloads`, the open project's, else the global library's), a job Activity lists. While it runs the
/// button is a spinner; a failure offers Try Again; when it finishes, `onDone` lets the row read itself again.
struct SettingsModelDownloadButton: View {
    let key: ModelDownloads.Key
    let name: String
    var enabled = true
    var help = "Download it to this Mac; Activity shows the download"
    var onDone: () -> Void = {}

    @Environment(LibraryManager.self) private var libraryManager

    var body: some View {
        if let downloads = ModelDownloads.forSettings(libraryManager) {
            Group {
                if downloads.isActive(key) {
                    ProgressView().controlSize(.small)
                } else {
                    Button(ModelFinderCard.failed(downloads.state(key)) ? "Try Again" : "Download") {
                        Task { await downloads.start(key, name: name) }
                    }
                    .buttonStyle(.borderless)
                    .disabled(!enabled)
                    .help(help)
                }
            }
            .onChange(of: downloads.state(key)) { _, state in
                if state == .done { onDone() }
            }
        } else {
            Text("Open a project to download").font(.caption).foregroundStyle(.secondary)
        }
    }
}

/// The line under a Settings model row: what its download's Activity job says, or why it failed.
struct SettingsModelDownloadLine: View {
    let key: ModelDownloads.Key

    @Environment(LibraryManager.self) private var libraryManager

    var body: some View {
        if let downloads = ModelDownloads.forSettings(libraryManager), let line = downloads.line(key) {
            Text(line)
                .font(.caption)
                .foregroundStyle(ModelFinderCard.failed(downloads.state(key)) ? .orange : .secondary)
                .textSelection(.enabled)
        }
    }
}

#Preview("Download a model in Settings") {
    let key = ModelDownloads.Key(runtime: "mlx", model: "Qwen2.5-VL-7B")
    return Form {
        HStack {
            VStack(alignment: .leading) {
                Text("Qwen2.5-VL 7B (OCR)")
                SettingsModelDownloadLine(key: key)
            }
            Spacer()
            SettingsModelDownloadButton(key: key, name: "Qwen2.5-VL 7B")
        }
    }
    .formStyle(.grouped)
    .environment(LibraryManager.shared)
    .frame(width: 420, height: 120)
}
