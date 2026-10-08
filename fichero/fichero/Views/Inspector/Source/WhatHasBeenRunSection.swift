import SwiftUI

/// The document Inspector's "What has been run" section (#5434,
/// `activity.document.what-has-been-run`): every step that has touched this document, newest first,
/// each with what it was, the model, when, the outcome and the cost when priced, as the engine
/// recorded it when it ran. Read from the project's `RunHistoryStore`.
struct WhatHasBeenRunInspectorSection: View {
    let document: Document

    @Environment(LibraryManager.self) private var libraryManager: LibraryManager?
    @Environment(DocumentStore.self) private var documentStore: DocumentStore?

    private var store: RunHistoryStore? {
        documentStore.flatMap { libraryManager?.library(owningService: $0)?.runHistoryStore }
    }

    var body: some View {
        if let store {
            WhatHasBeenRunSection(
                entries: store.history(documentId: document.id),
                failure: store.failures[document.id]
            )
            .task(id: document.id) { await store.load(documentIds: [document.id]) }
        }
    }
}

/// The section's body, given what the store holds: `nil` entries while the first read is out.
struct WhatHasBeenRunSection: View {
    let entries: [RunHistoryStore.Entry]?
    let failure: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("What has been run").font(.headline)
            if let entries {
                if entries.isEmpty {
                    Text("Nothing has been run on this document yet.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                ForEach(entries) { entry in
                    WhatHasBeenRunRow(entry: entry)
                }
            } else if failure == nil {
                ProgressView().controlSize(.small)
            }
            if let failure {
                Text(failure).font(.caption).foregroundStyle(.secondary)
            }
        }
        .accessibilityIdentifier("inspector.whatHasBeenRun")
    }
}

private struct WhatHasBeenRunRow: View {
    let entry: RunHistoryStore.Entry

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline) {
                Text(entry.name).font(.body).textSelection(.enabled)
                Spacer(minLength: 8)
                Text(entry.outcomeText)
                    .font(.caption)
                    .foregroundStyle(entry.isFailed ? AnyShapeStyle(.red) : AnyShapeStyle(.secondary))
            }
            Text(detail).font(.caption).foregroundStyle(.secondary)
            if let reason = entry.reason, !reason.isEmpty {
                Text(reason).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            }
        }
        .accessibilityElement(children: .combine)
    }

    /// "gpt-5 · openai · Today 09:14 · $0.02": the model, when, and the cost when priced.
    private var detail: String {
        [entry.modelText, ActivityTimeText.absolute(entry.when), entry.costText]
            .compactMap { $0 }
            .joined(separator: " · ")
    }
}

#Preview("What has been run") {
    WhatHasBeenRunSection(
        entries: [
            .init(id: "j3", name: "Read the page", kind: "read-a-page", state: "failed",
                  reason: "the provider refused this letter", model: "gpt-5", provider: "openai",
                  when: Date().addingTimeInterval(-600)),
            .init(id: "w2", name: "Transcribe", kind: "workflow", state: "done",
                  model: "claude-sonnet", provider: "anthropic", cost: 0.0225,
                  when: Date().addingTimeInterval(-3_600)),
            .init(id: "j1", name: "Find the lines", kind: "find-lines", state: "done",
                  model: "kraken blla", when: Date().addingTimeInterval(-86_400))
        ],
        failure: nil
    )
    .padding()
    .frame(width: 320)
}

#Preview("Nothing run yet") {
    WhatHasBeenRunSection(entries: [], failure: nil)
        .padding()
        .frame(width: 320)
}
