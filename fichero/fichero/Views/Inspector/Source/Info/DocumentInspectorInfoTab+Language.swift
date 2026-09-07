import OSLog
import SwiftUI

// MARK: - Document language display + editor (#2092)

/// Resolves a document's language into the one honest string the Info row
/// shows, keeping the three-way distinction the backend is careful to record
/// (`llm/language_policy.py`) rather than collapsing it into a null that reads
/// as English:
///
///   - `languageMeta == nil`                 → nothing ever determined it
///   - `languageMeta["status"] == "unknown"` → examined and cannot be told
///   - `languageMeta["status"] == "known"`   → `language` holds the answer
///
/// Modelled on `DocumentDateDisplay.resolve` — the absence of metadata is an
/// answer, not a value to default away.
enum DocumentLanguageDisplay {
    static let statusKnown = "known"
    static let statusUnknown = "unknown"
    static let sourceUser = "user"

    /// The status string the engine recorded, or nil when nothing has run.
    static func status(for document: Document) -> String? {
        document.languageMeta?["status"]?.value as? String
    }

    /// The provenance of the recorded language: user | detected | metadata.
    static func source(for document: Document) -> String? {
        document.languageMeta?["source"]?.value as? String
    }

    /// True when a human set this language — a persistent curation rule that
    /// survives re-extraction (mirrors `dateMeta["source"] == "user"`).
    static func isUserSet(_ document: Document) -> Bool {
        source(for: document) == sourceUser
    }

    /// The trailing summary the collapsed row shows.
    static func summary(for document: Document) -> String {
        // No metadata at all: detection never ran. Not "English".
        guard let status = status(for: document) else { return "Not determined" }
        if status == statusUnknown { return "Unknown" }
        // status == known (or any other recorded status): the name is the answer.
        if let language = document.language, !language.isEmpty { return language }
        return "Not determined"
    }
}

/// The expanded editor for a document's language (#2092) — the detail revealed
/// when the Language row is tapped, mirroring `DocumentPrototypePicker` in the
/// Class row.
///
/// Every write goes through the SAME audited/undoable action the rest of the
/// app uses (`document.set_language`), never a bespoke request:
///
///   - picking a name        → `language: <name>` (persists `source: user`)
///   - "Mark undeterminable" → `undeterminable: true` (status becomes unknown)
///   - "Clear (re-detect)"   → language and undeterminable both omitted
///     (back to never-determined so detection may run again)
struct DocumentLanguagePicker: View {
    let documentId: String
    let language: String?
    let languageMeta: [String: AnyCodable]?
    /// The action service of the library that owns `documentId`, handed down by
    /// the inspector (like `DocumentPrototypePicker`'s `entityService`). Nil
    /// when no library resolves — the editor then disables itself rather than
    /// quietly writing nowhere.
    let actionsService: ActionsService?

    /// Common languages offered for one-tap assignment; a free-text field
    /// covers everything else (the engine accepts any canonical name).
    private static let commonLanguages = [
        "English", "Spanish", "French", "German", "Italian", "Portuguese",
        "Latin", "Dutch", "Greek", "Russian", "Arabic", "Chinese", "Japanese"
    ]

    /// Optimistic local mirror so the row reflects a write before the change
    /// stream round-trips (the same pattern `DocumentPrototypePicker` uses for
    /// `selectedKey`). Seeded from the passed-in document values.
    @State private var currentLanguage: String?
    @State private var currentStatus: String?
    @State private var currentSource: String?
    @State private var draft = ""
    @State private var isSaving = false

    private let logger = Logger(subsystem: "app.fichero", category: "LanguagePicker")

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            provenanceCaption

            HStack(spacing: 6) {
                languageMenu

                TextField("Language name", text: $draft)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { Task { await setLanguage(draft) } }
                Button("Set") { Task { await setLanguage(draft) } }
                    .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
            }

            HStack(spacing: 12) {
                Button("Mark undeterminable") { Task { await markUndeterminable() } }
                Button("Clear (re-detect)") { Task { await clear() } }
                if isSaving {
                    ProgressView().controlSize(.mini)
                }
            }
            .font(.caption)
            .buttonStyle(.plain)
            .foregroundStyle(.tint)
        }
        .disabled(actionsService == nil || isSaving)
        .onAppear {
            currentLanguage = language
            currentStatus = languageMeta?["status"]?.value as? String
            currentSource = languageMeta?["source"]?.value as? String
        }
    }

    /// A quiet line naming the current state and where it came from — honest,
    /// not loud (Daniel's ask): "Set by you", "Detected", or "Not determined".
    @ViewBuilder
    private var provenanceCaption: some View {
        let text: String = {
            guard let status = currentStatus else { return "Not determined" }
            if status == DocumentLanguageDisplay.statusUnknown {
                return currentSource == DocumentLanguageDisplay.sourceUser
                    ? "Marked undeterminable by you"
                    : "Examined — could not be determined"
            }
            let name = currentLanguage ?? "Not determined"
            switch currentSource {
            case DocumentLanguageDisplay.sourceUser: return "\(name) · set by you"
            case "detected": return "\(name) · detected"
            case "metadata": return "\(name) · from metadata"
            default: return name
            }
        }()
        Text(text)
            .font(.caption)
            .foregroundStyle(.secondary)
    }

    private var languageMenu: some View {
        Menu {
            ForEach(Self.commonLanguages, id: \.self) { name in
                Button(name) { Task { await setLanguage(name) } }
            }
        } label: {
            HStack(spacing: 4) {
                Text("Choose…")
                Image(systemName: "chevron.up.chevron.down")
                    .font(.caption2)
            }
            .font(.caption)
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
    }

    // MARK: - Actions (all via the audited `document.set_language` action)

    private func setLanguage(_ name: String) async {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        await invoke(SetLanguageParams(docId: documentId, language: trimmed)) {
            currentLanguage = trimmed
            currentStatus = DocumentLanguageDisplay.statusKnown
            currentSource = DocumentLanguageDisplay.sourceUser
            draft = ""
        }
    }

    private func markUndeterminable() async {
        await invoke(SetLanguageParams(docId: documentId, undeterminable: true)) {
            currentLanguage = nil
            currentStatus = DocumentLanguageDisplay.statusUnknown
            currentSource = DocumentLanguageDisplay.sourceUser
        }
    }

    private func clear() async {
        // Both fields omitted: clears the assertion back to never-determined so
        // detection is free to run again.
        await invoke(SetLanguageParams(docId: documentId)) {
            currentLanguage = nil
            currentStatus = nil
            currentSource = nil
        }
    }

    private func invoke(_ params: SetLanguageParams, onSuccess: () -> Void) async {
        guard let service = actionsService else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            try await service.invokeAction(name: "document.set_language", params: params)
            onSuccess()
        } catch {
            // Keep the UI honest: local state only moves when the engine
            // accepted the write (mirrors the prototype picker).
            logger.error("set_language failed: \(error.localizedDescription)")
        }
    }
}

/// Typed params for `document.set_language` — the wire shape of
/// `DocumentSetLanguageParams` (documents.py). Reuses the action layer's typed
/// bridge like `AclSetParams`, never `additionalProperties`.
private struct SetLanguageParams: Encodable {
    let docId: String
    let language: String?
    let undeterminable: Bool?

    init(docId: String, language: String? = nil, undeterminable: Bool? = nil) {
        self.docId = docId
        self.language = language
        self.undeterminable = undeterminable
    }

    enum CodingKeys: String, CodingKey {
        case docId = "doc_id"
        case language
        case undeterminable
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(docId, forKey: .docId)
        try container.encodeIfPresent(language, forKey: .language)
        try container.encodeIfPresent(undeterminable, forKey: .undeterminable)
    }
}
