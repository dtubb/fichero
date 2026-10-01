import SwiftUI

/// The window's line, above the content like `EngineVersionMismatchNotice`: a progress bar while
/// a library's older results are brought into the page model, then one line with Show Report
/// until the report has been seen (#5222 part 3). Closing the report marks the run seen, which is
/// what releases the snapshot the engine took first.
struct ConversionNotice: View {
    let store: ConversionStatusStore
    @State private var showingReport = false

    var body: some View {
        Group {
            if !store.hiddenForSession {
                ConversionNoticeBar(
                    status: store.status,
                    onShowReport: { showingReport = true },
                    onClose: { store.hiddenForSession = true }
                )
            }
        }
        // Read now, and every few seconds while a conversion runs. The window's lifetime bounds it.
        .task {
            repeat {
                await store.refresh()
                guard store.status.running else { return }
                try? await Task.sleep(for: .seconds(3))
            } while !Task.isCancelled
        }
        .sheet(isPresented: $showingReport, onDismiss: { Task { await store.markSeen() } }) {
            ConversionReportSheet(status: store.status) { showingReport = false }
        }
    }
}

/// The line itself, from a status alone: nothing when there is nothing to say.
struct ConversionNoticeBar: View {
    let status: ConversionSnapshot
    var onShowReport: () -> Void = {}
    var onClose: () -> Void = {}

    var body: some View {
        if let line = ConversionNoticeText.line(status) {
            HStack(alignment: .center, spacing: 10) {
                if let progress = ConversionNoticeText.progress(status) {
                    ProgressView(value: progress)
                        .frame(width: 80)
                } else {
                    Image(systemName: status.verdict == "completed" ? "checkmark.circle" : "exclamationmark.triangle.fill")
                        .foregroundStyle(status.verdict == "completed" ? Color.secondary : Color.orange)
                        .accessibilityHidden(true)
                }
                Text(line)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                if !status.running {
                    Button("Show Report", action: onShowReport)
                        .controlSize(.small)
                        .accessibilityIdentifier("conversionNotice.showReport")
                    Button(action: onClose) {
                        Image(systemName: "xmark").imageScale(.small)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                    .help("Hide until the next launch; the report stays unread")
                    .accessibilityLabel("Close")
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .accessibilityIdentifier("conversionNotice")
        }
    }
}

/// The report: what converted, what could not and why, what was left as it was, where the
/// snapshot is, how long it took.
struct ConversionReportSheet: View {
    let status: ConversionSnapshot
    let onDone: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Older Results in the Page Model")
                .font(.headline)
            ScrollView {
                Text(ConversionNoticeText.report(status))
                    .font(.body)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack {
                Spacer()
                Button("Done", action: onDone)
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding()
        .frame(minWidth: 420, minHeight: 260)
    }
}

#Preview("Converting") {
    ConversionNoticeBar(status: ConversionSnapshot(running: true, runId: "r1", pagesConverted: 33, pagesRemaining: 67))
        .frame(width: 640)
}

#Preview("Done, one page could not be") {
    ConversionNoticeBar(status: ConversionSnapshot(
        runId: "r1", verdict: "completed", pagesConverted: 93,
        pagesNotConverted: [.init(documentId: "doc-7", reason: "a box lies outside its page")]
    ))
    .frame(width: 640)
}

#Preview("Report") {
    ConversionReportSheet(status: ConversionSnapshot(
        runId: "r1", verdict: "completed", seconds: 52, pagesConverted: 93,
        pagesNotConverted: [.init(documentId: "doc-7", reason: "a box lies outside its page")],
        snapshotPath: "/Library/Snapshots/s1",
        leftAsTheyWere: [.init(artifactType: "segmentation", count: 4, reason: "No engine producer wrote it.")]
    ), onDone: {})
}
