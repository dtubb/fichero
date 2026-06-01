// swiftlint:disable file_length
import FicheroAPIClient
import OSLog
import SwiftUI

private let relatedClaimsLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "RelatedClaimsPanel"
)

/// Info tab content for DocumentInspector
struct DocumentInspectorInfoTab: View {
    let document: Document

    var body: some View {
        VStack(alignment: .center, spacing: 0) {
            headerSection
                .padding(.bottom, 8)

            Form {
                Section("Status") {
                    LabeledContent("State") {
                        HStack(spacing: 6) {
                            StatusBadge(status: document.status)
                            if document.status == .processing {
                                ProgressView().scaleEffect(0.7)
                            }
                        }
                    }
                    LabeledContent("Created") {
                        Text(document.createdAt, style: .date)
                    }
                    LabeledContent("Modified") {
                        Text(document.updatedAt, style: .relative)
                    }
                }

                Section("Class") {
                    DocumentPrototypePicker(
                        documentId: document.id,
                        initialKey: document.prototypeKey
                    )
                }

                Section("File") {
                    LabeledContent("Kind") {
                        Text(document.docType.rawValue.capitalized)
                    }
                    if let fileType = document.fileType {
                        LabeledContent("Type") {
                            Text(fileType.rawValue.capitalized)
                        }
                    }
                    if let fileSize = document.metadata["File_Size"]?.value as? Int {
                        LabeledContent("Size") {
                            Text(ByteCountFormatter.string(fromByteCount: Int64(fileSize), countStyle: .file))
                        }
                    }
                }

                Section("Related Claims") {
                    RelatedClaimsPanel(documentId: document.id)
                }

                Section("Citations") {
                    CitationGraphPanel(documentId: document.id)
                }

                Section("Bibliography") {
                    DocumentBibliographyPanel(documentId: document.id)
                }

                Section("Workflow History") {
                    WorkflowProvenancePanel(documentId: document.id)
                }
            }
            .formStyle(.grouped)
        }
    }

    // MARK: - Header Section

    private var headerSection: some View {
        VStack(alignment: .center, spacing: 10) {
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(.windowBackgroundColor))
                    .frame(width: 80, height: 100)

                LibraryImageView(documentId: document.id, imageType: .thumbnail)
                    .aspectRatio(contentMode: .fill)
                    .frame(width: 80, height: 100)
                    .clipped()
            }
            .frame(width: 80, height: 100)
            .clipShape(RoundedRectangle(cornerRadius: 12))

            Text(document.name)
                .font(.headline)
                .multilineTextAlignment(.center)
                .lineLimit(3)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 8)
    }
}

// MARK: - RelatedClaimsPanel (#959 KG-RAG)

/// Inspector panel that surfaces claims from across the library
/// semantically similar to claims extracted from the current document.
/// Uses `EntityServiceGenerated.findSimilarClaims` per doc-claim, dedups
/// by claim id, ranks by similarity, caps at 10.
///
/// Empty state means either (a) the doc has no extracted claims yet, or
/// (b) claims haven't been embedded — run "Embed claims" from the
/// Ontology Browser Tools menu.
struct RelatedClaimsPanel: View {
    let documentId: String

    @State private var related: [EntityServiceGenerated.SimilarClaim] = []
    @State private var sourceDocNames: [String: String] = [:]
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if isLoading && related.isEmpty {
                HStack(spacing: 6) {
                    ProgressView().scaleEffect(0.6)
                    Text("Searching…").font(.caption).foregroundStyle(.secondary)
                }
            } else if related.isEmpty {
                Text("No related claims")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                LazyVStack(alignment: .leading, spacing: 6) {
                    ForEach(related) { row(for: $0) }
                }
            }
        }
        .task(id: documentId) { await load() }
    }

    @ViewBuilder
    private func row(for claim: EntityServiceGenerated.SimilarClaim) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(claim.text)
                .font(.caption)
                .foregroundStyle(.primary)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 6) {
                if let docId = claim.sourceDocumentId,
                   let name = sourceDocNames[docId], !name.isEmpty {
                    Text(name)
                        .font(.caption2)
                        .italic()
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                Spacer(minLength: 4)
                Text(String(format: "%.2f", max(0, min(1, claim.similarityScore))))
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 2)
    }

    @MainActor
    private func load() async {
        guard let library = LibraryManager.shared.globalLibrary else {
            related = []
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            // 1) Fetch this doc's own claims.
            let myClaims = try await library.entityService.listClaims(
                sourceDocumentId: documentId,
                limit: 100
            )
            guard !myClaims.isEmpty else {
                related = []
                return
            }

            // 2) For each (up to 20), fetch top-3 similar; dedup by claim id;
            // keep the highest similarity per id; exclude self-doc; top 10.
            var aggregated: [String: EntityServiceGenerated.SimilarClaim] = [:]
            for claim in myClaims.prefix(20) {
                guard let cid = claim.id else { continue }
                let similar = try await library.entityService.findSimilarClaims(
                    claimId: cid,
                    limit: 3
                )
                for sim in similar where sim.sourceDocumentId != documentId {
                    if let existing = aggregated[sim.id] {
                        if sim.similarityScore > existing.similarityScore {
                            aggregated[sim.id] = sim
                        }
                    } else {
                        aggregated[sim.id] = sim
                    }
                }
            }
            let top = aggregated.values
                .sorted { $0.similarityScore > $1.similarityScore }
                .prefix(10)
            let result = Array(top)
            resolveSourceDocNames(for: Set(result.compactMap { $0.sourceDocumentId }))
            related = result
        } catch {
            relatedClaimsLogger.error("Related claims fetch failed: \(error.localizedDescription)")
            errorMessage = "Couldn't load related claims."
            related = []
        }
    }

    private func resolveSourceDocNames(for ids: Set<String>) {
        guard let library = LibraryManager.shared.globalLibrary,
              !ids.isEmpty
        else { return }
        var resolved: [String: String] = [:]
        for id in ids {
            if let doc = library.documentStore.currentDocuments.first(where: { $0.id == id }) {
                resolved[id] = doc.name
            }
        }
        sourceDocNames = resolved
    }
}

// MARK: - CitationGraphPanel (#974 prep)

/// Inspector panel that surfaces citations to/from this document, backed
/// by `/api/citations/graph/document/{id}/{inbound,outbound}`.
/// "Inbound" = docs that cite this one; "Outbound" = docs this one cites.
/// Rows render the citation text + page label (when present) + a small
/// italic resolved doc name for outbound, source-doc name for inbound.
struct CitationGraphPanel: View {
    let documentId: String

    @State private var inbound: [Components.Schemas.DocumentCitation] = []
    @State private var outbound: [Components.Schemas.DocumentCitation] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if isLoading && inbound.isEmpty && outbound.isEmpty {
                HStack(spacing: 6) {
                    ProgressView().scaleEffect(0.6)
                    Text("Loading…").font(.caption).foregroundStyle(.secondary)
                }
            } else if inbound.isEmpty && outbound.isEmpty {
                Text("No citations recorded")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                if !outbound.isEmpty {
                    citationGroup(
                        title: "Cites \(outbound.count)",
                        items: outbound,
                        nameFor: { $0.targetDocumentId }
                    )
                }
                if !inbound.isEmpty {
                    citationGroup(
                        title: "Cited by \(inbound.count)",
                        items: inbound,
                        nameFor: { _ in nil }
                    )
                }
            }
        }
        .task(id: documentId) { await load() }
    }

    @ViewBuilder
    private func citationGroup(
        title: String,
        items: [Components.Schemas.DocumentCitation],
        nameFor: (Components.Schemas.DocumentCitation) -> String?
    ) -> some View {
        Text(title)
            .font(.caption.bold())
            .foregroundStyle(.secondary)
        LazyVStack(alignment: .leading, spacing: 4) {
            ForEach(items, id: \.id) { item in
                citationRow(item)
            }
        }
    }

    @ViewBuilder
    private func citationRow(_ item: Components.Schemas.DocumentCitation) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(item.targetCitationText)
                .font(.caption)
                .foregroundStyle(.primary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 6) {
                if let page = item.pageLabel, !page.isEmpty {
                    Text("p. \(page)")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                if let detector = item.detector, !detector.isEmpty {
                    Text(detector)
                        .font(.caption2)
                        .italic()
                        .foregroundStyle(.tertiary)
                }
                Spacer(minLength: 4)
                if let confidence = item.confidence {
                    Text(String(format: "%.2f", confidence))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.vertical, 2)
    }

    @MainActor
    private func load() async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            async let inboundTask = library.entityService.inboundCitations(forDocumentId: documentId)
            async let outboundTask = library.entityService.outboundCitations(forDocumentId: documentId)
            let (inb, out) = try await (inboundTask, outboundTask)
            inbound = inb
            outbound = out
        } catch {
            relatedClaimsLogger.error("Citations fetch failed: \(error.localizedDescription)")
            errorMessage = "Couldn't load citations."
            inbound = []
            outbound = []
        }
    }
}

// MARK: - DocumentBibliographyPanel (#1434)

/// Extracted bibliography panel — scholarly references extracted from
/// within the document, backed by `GET /api/documents/{id}/citations`.
/// Distinct from CitationGraphPanel (doc-to-doc links in the knowledge
/// graph); this shows the bibliography inside the document itself.
struct DocumentBibliographyPanel: View {
    let documentId: String

    @State private var references: [Components.Schemas.Reference] = []
    @State private var selfRef: Components.Schemas.Reference?
    @State private var isLoading = false
    @State private var copiedAll = false

    private var allBibtex: String {
        let parts = ([selfRef].compactMap { $0 } + references)
            .compactMap { $0.bibtex }
            .filter { !$0.isEmpty }
        return parts.joined(separator: "\n\n")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if isLoading && references.isEmpty {
                HStack(spacing: 6) {
                    ProgressView().scaleEffect(0.6)
                    Text("Loading…").font(.caption).foregroundStyle(.secondary)
                }
            } else if references.isEmpty && selfRef == nil {
                Text("No bibliography extracted yet")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                if !allBibtex.isEmpty {
                    HStack {
                        Spacer()
                        Button {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(allBibtex, forType: .string)
                            copiedAll = true
                        } label: {
                            Label(
                                copiedAll ? "Copied!" : "Copy all BibTeX",
                                systemImage: copiedAll ? "checkmark" : "doc.on.doc"
                            )
                            .font(.caption2)
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(.secondary)
                        .onChange(of: copiedAll) { _, newValue in
                            if newValue {
                                Task {
                                    try? await Task.sleep(for: .seconds(1.5))
                                    copiedAll = false
                                }
                            }
                        }
                    }
                }
                if let selfRef {
                    referenceRow(selfRef, isSelf: true)
                    if !references.isEmpty { Divider() }
                }
                LazyVStack(alignment: .leading, spacing: 6) {
                    ForEach(references, id: \.id) { ref in
                        referenceRow(ref, isSelf: false)
                    }
                }
            }
        }
        .task(id: documentId) { await load() }
    }

    @ViewBuilder
    private func referenceRow(_ ref: Components.Schemas.Reference, isSelf: Bool) -> some View {
        ReferenceRowView(ref: ref, isSelf: isSelf)
    }

    private func load() async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        isLoading = true
        defer { isLoading = false }
        guard let resp = try? await library.entityService.listDocumentCitations(documentId: documentId) else {
            return
        }
        selfRef = resp._self
        references = resp.references
    }
}

private struct ReferenceRowView: View {
    let ref: Components.Schemas.Reference
    let isSelf: Bool

    @State private var isExpanded = false
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                if isSelf {
                    Image(systemName: "doc.text")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Text(refTitle)
                    .font(.caption)
                    .foregroundStyle(.primary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 4)
                if let bibtex = ref.bibtex, !bibtex.isEmpty {
                    Button {
                        if isExpanded {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(bibtex, forType: .string)
                            copied = true
                        } else {
                            isExpanded = true
                        }
                    } label: {
                        Image(systemName: copied ? "checkmark" : (isExpanded ? "doc.on.doc" : "chevron.down"))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help(isExpanded ? "Copy BibTeX" : "Show BibTeX")
                    .onChange(of: copied) { _, newValue in
                        if newValue {
                            Task {
                                try? await Task.sleep(for: .seconds(1.5))
                                copied = false
                            }
                        }
                    }
                }
            }
            HStack(spacing: 6) {
                if let authors = ref.authors, !authors.isEmpty {
                    Text(authors.prefix(2).joined(separator: ", "))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                if let year = ref.year {
                    Text(String(year))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
                if let doi = ref.doi, !doi.isEmpty {
                    Text("DOI")
                        .font(.caption2)
                        .foregroundStyle(Color.accentColor)
                        .help(doi)
                }
                Spacer(minLength: 4)
                if let journal = ref.journalOrBook {
                    Text(journal)
                        .font(.caption2)
                        .italic()
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
            }
            if isExpanded, let bibtex = ref.bibtex, !bibtex.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    Text(bibtex)
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                        .padding(6)
                        .background(Color(.textBackgroundColor).opacity(0.6))
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                }
                .frame(maxHeight: 80)
            }
        }
        .padding(.vertical, 2)
    }

    private var refTitle: String {
        if let title = ref.title, !title.isEmpty { return title }
        if let bib = ref.bibtex, !bib.isEmpty { return String(bib.prefix(60)) + "…" }
        return "Untitled"
    }
}

// MARK: - WorkflowProvenancePanel (#1434)

/// Shows which workflow runs touched this document, backed by
/// `GET /api/documents/{id}/workflow-runs`. Lets the user see
/// which AI pipeline produced the document's entities and artifacts.
struct WorkflowProvenancePanel: View {
    let documentId: String

    @State private var runs: [Components.Schemas.WorkflowRunProvenanceResponse] = []
    @State private var isLoading = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if isLoading && runs.isEmpty {
                HStack(spacing: 6) {
                    ProgressView().scaleEffect(0.6)
                    Text("Loading…").font(.caption).foregroundStyle(.secondary)
                }
            } else if runs.isEmpty {
                Text("No workflow runs recorded")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                LazyVStack(alignment: .leading, spacing: 6) {
                    ForEach(runs.prefix(10), id: \.workflowId) { run in
                        provenanceRow(run)
                    }
                }
            }
        }
        .task(id: documentId) { await load() }
    }

    @ViewBuilder
    private func provenanceRow(_ run: Components.Schemas.WorkflowRunProvenanceResponse) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "gearshape.2")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .frame(width: 14)
            VStack(alignment: .leading, spacing: 2) {
                Text(run.workflowName ?? run.workflowId)
                    .font(.caption)
                    .lineLimit(1)
                    .truncationMode(.middle)
                HStack(spacing: 4) {
                    if let model = run.model, !model.isEmpty {
                        Text(model)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                            .lineLimit(1)
                    }
                    if let started = run.startedAt, !started.isEmpty {
                        Text(relativeDate(started))
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.tertiary)
                    }
                }
            }
        }
        .padding(.vertical, 2)
    }

    private func relativeDate(_ iso: String) -> String {
        let fmt = ISO8601DateFormatter()
        fmt.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = fmt.date(from: iso) else { return iso }
        let rel = RelativeDateTimeFormatter()
        rel.unitsStyle = .abbreviated
        return rel.localizedString(for: date, relativeTo: Date())
    }

    private func load() async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        isLoading = true
        defer { isLoading = false }
        runs = (try? await library.entityService.listDocumentWorkflowRuns(documentId: documentId)) ?? []
    }
}

// MARK: - Document prototype / class picker (#1377)

struct DocumentPrototypePicker: View {
    let documentId: String
    let initialKey: String?

    @State private var selectedKey: String?
    @State private var prototypes: [Components.Schemas.ClassificationValue] = []
    @State private var isAssigning = false

    var body: some View {
        LabeledContent("Prototype") {
            Menu {
                Button("None") {
                    Task { await assign(nil) }
                }
                Divider()
                ForEach(prototypes, id: \.key) { proto in
                    Button {
                        Task { await assign(proto.key) }
                    } label: {
                        Label {
                            Text(proto.label)
                        } icon: {
                            if selectedKey == proto.key {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            } label: {
                HStack(spacing: 4) {
                    if isAssigning {
                        ProgressView().scaleEffect(0.6).frame(width: 12, height: 12)
                    }
                    if let key = selectedKey,
                       let proto = prototypes.first(where: { $0.key == key }) {
                        PrototypeBadge(proto: proto)
                    } else {
                        Text("None")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Image(systemName: "chevron.up.chevron.down")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            .buttonStyle(.plain)
        }
        .task {
            selectedKey = initialKey
            if let svc = LibraryManager.shared.globalLibrary?.entityService {
                prototypes = (try? await svc.listDocumentPrototypes()) ?? []
            }
        }
    }

    private func assign(_ key: String?) async {
        guard let svc = LibraryManager.shared.globalLibrary?.entityService else { return }
        isAssigning = true
        defer { isAssigning = false }
        if let key {
            _ = try? await svc.assignDocumentPrototype(documentId: documentId, prototypeKey: key)
        }
        selectedKey = key
    }
}

private extension Color {
    init?(hex: String) {
        let stripped = hex.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "#", with: "")
        guard stripped.count == 6, let value = UInt64(stripped, radix: 16) else { return nil }
        let red = Double((value >> 16) & 0xFF) / 255
        let green = Double((value >> 8) & 0xFF) / 255
        let blue = Double(value & 0xFF) / 255
        self.init(red: red, green: green, blue: blue)
    }
}

private struct PrototypeBadge: View {
    let proto: Components.Schemas.ClassificationValue

    var body: some View {
        Text(proto.label)
            .font(.caption)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(badgeColor.opacity(0.18))
            .foregroundStyle(badgeColor)
            .clipShape(Capsule())
    }

    private var badgeColor: Color {
        guard let hex = proto.color, !hex.isEmpty else { return .accentColor }
        return Color(hex: hex) ?? .accentColor
    }
}
