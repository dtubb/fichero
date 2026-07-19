import SwiftUI

// MARK: - Filter Chips

extension EntityDetailView {
    var filterStrips: some View {
        // Show only chips for status / kind values that ACTUALLY appear
        // in this entity's claims. Computed from the unfiltered `claims`
        // (not `filteredClaims`) so hiding the only Confirmed claim
        // still leaves the Confirmed chip visible to un-hide. (#1005)
        let presentEpistemic: Set<String> = Set(claims.map {
            $0.epistemicStatus?.rawValue ?? "tentative"
        })
        let presentKinds: Set<String> = Set(claims.map {
            $0.claimType?.rawValue ?? "fact"
        })
        let statusKeys = ["confirmed", "tentative", "rejected"].filter {
            presentEpistemic.contains($0)
        }
        let kindKeys = ["fact", "analysis", "interpretation", "argument", "historiography", "theory"].filter {
            presentKinds.contains($0)
        }
        return VStack(alignment: .leading, spacing: 4) {
            if !statusKeys.isEmpty {
                HStack(spacing: 4) {
                    Text("Status")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .frame(width: 56, alignment: .leading)
                    ForEach(statusKeys, id: \.self) { key in
                        chip(label: key.capitalized,
                             isHidden: hiddenEpistemic.contains(key),
                             color: epistemicColor(key)) {
                            toggle(key, in: &hiddenEpistemicCSV)
                        }
                    }
                    Spacer(minLength: 0)
                }
            }
            if !kindKeys.isEmpty {
                HStack(spacing: 4) {
                    Text("Kind")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .frame(width: 56, alignment: .leading)
                    ForEach(kindKeys, id: \.self) { key in
                        chip(label: key.capitalized,
                             isHidden: hiddenClaimTypes.contains(key),
                             color: .gray) {
                            toggle(key, in: &hiddenClaimTypesCSV)
                        }
                    }
                    Spacer(minLength: 0)
                }
            }
        }
    }

    func chip(label: String, isHidden: Bool, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.caption2)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background((isHidden ? Color.gray : color).opacity(isHidden ? 0.1 : 0.25))
                .foregroundStyle(isHidden ? .secondary : .primary)
                .clipShape(RoundedRectangle(cornerRadius: 3))
        }
        .buttonStyle(.plain)
    }

    func epistemicColor(_ raw: String) -> Color {
        switch raw {
        case "confirmed": return .green
        case "rejected": return .red
        case "tentative": return .orange
        default: return .gray
        }
    }

    func toggle(_ key: String, in csv: inout String) {
        var set = Self.parseCSV(csv)
        if set.contains(key) { set.remove(key) } else { set.insert(key) }
        csv = set.sorted().joined(separator: ",")
    }

    /// Hide visually-degraded OCR strings that are mostly replacement
    /// glyphs; keeps the detail panel readable when extraction quality
    /// is poor on a page.
    func cleanedDisplayText(_ value: String?) -> String? {
        guard let raw = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !raw.isEmpty else { return nil }
        let replacementGlyphs = raw.filter { $0 == "\u{FFFD}" || $0 == "□" || $0 == "�" }
        if !raw.isEmpty {
            let ratio = Double(replacementGlyphs.count) / Double(raw.count)
            if ratio > 0.08 { return nil }
        }
        return raw
    }
}
