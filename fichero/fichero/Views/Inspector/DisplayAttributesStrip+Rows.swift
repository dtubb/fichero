import SwiftUI

extension DisplayAttributesStrip {
    // MARK: - Persistence helpers

    func csvSet(_ raw: String) -> Set<String> {
        Set(raw.split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty })
    }

    func csvString(_ values: Set<String>) -> String {
        values
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .sorted()
            .joined(separator: ",")
    }

    // MARK: - Row rendering

    @ViewBuilder
    func rowView(for item: StripRow) -> some View {
        switch item {
        case .attribute(let attr):
            attributeRow(attr)
        case .knowledge(let kgItem):
            kgRow(kgItem)
        case .artifact(let type):
            row(displayName(for: type), value: artifactValue(for: type))
        case .metadata(let key):
            row(metadataLabel(for: key), value: metadataValue(for: key))
        }
    }

    /// A KG summary row. The count is the meaningful bit, so it's emphasised
    /// (primary, semibold) rather than rendered as flat secondary text — the
    /// "intelligently highlighted" treatment the maintainer asked for (#1246).
    func kgRow(_ item: KGItem) -> some View {
        let count: Int? = (item == .entities) ? entityCount : claimCount
        return row(item.label, value: count.map(String.init) ?? "—", emphasis: true)
    }

    @ViewBuilder
    func attributeRow(_ attr: DisplayAttribute) -> some View {
        switch attr {
        case .status: row(attr.label, value: statusValue, color: statusColor)
        case .kind: row(attr.label, value: kindValue)
        case .ingest: row(attr.label, value: ingestValue)
        case .path: row(attr.label, value: document.path ?? "", monospaced: true)
        case .created: row(attr.label, value: relativeDateString(document.createdAt))
        case .modified: row(attr.label, value: relativeDateString(document.updatedAt))
        }
    }

    // MARK: - Row helpers

    @ViewBuilder
    func row(
        _ label: String,
        value: String,
        color: Color = .primary,
        monospaced: Bool = false,
        emphasis: Bool = false
    ) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .frame(width: 64, alignment: .leading)
            Text(value)
                .font(monospaced ? .caption.monospaced() : .caption)
                // Emphasised rows (e.g. KG counts) get semibold weight so the
                // meaningful value stands out from the flat secondary label.
                .fontWeight(emphasis ? .semibold : .regular)
                .foregroundStyle(color)
                .lineLimit(1)
                .truncationMode(.middle)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 3)
    }
}
