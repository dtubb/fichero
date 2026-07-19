import SwiftUI

// MARK: - Previews
//
// Mock data + standalone surfaces so the inspector can iterate in Xcode
// Previews without a running backend. Pure layout work (filter Menu,
// kind ordering, keyword chip row, dedupe rendering, content lineLimits)
// loops in seconds here instead of through a 60s rebuild cycle.

enum PreviewMocks {
    static let people: [GroupedItem] = [
        GroupedItem(
            claimId: "p1",
            displayName: "Federico W. Leighton",
            context: "is named as engineer of the dredge",
            aliases: ["F. W. Leighton", "Leighton"]
        ),
        GroupedItem(
            claimId: "p2",
            displayName: "Don Mateo Restrepo",
            context: "appears as the lender in the deed",
            aliases: ["Don Mateo", "D. Mateo"]
        ),
        GroupedItem(
            claimId: "p3",
            displayName: "Fenwic P. Caddy",
            context: "is reported to have resigned as captain",
            aliases: []
        )
    ]
    static let places: [GroupedItem] = [
        GroupedItem(
            claimId: "l1",
            displayName: "Río Condoto",
            context: "is named as the site of the dredge sinking",
            aliases: ["Río Conduto"]
        ),
        GroupedItem(
            claimId: "l2",
            displayName: "Bazán",
            context: "is described as the point where the dredge worked",
            aliases: ["Basán"]
        )
    ]
    static let organizations: [GroupedItem] = [
        GroupedItem(
            claimId: "o1",
            displayName: "Compañía Minera Chocó Pacífico",
            context: "is named as operator of the dredge",
            aliases: ["Cía. Minera Chocó Pacífico", "Choco Pacifico"]
        ),
        GroupedItem(
            claimId: "o2",
            displayName: "British Platinum & Gold Corporation Limited",
            context: "is described as the dredge's owner",
            aliases: []
        )
    ]
    static let events: [GroupedItem] = [
        GroupedItem(
            claimId: "e1",
            displayName: "Naufragio de la draga No. 1",
            context: "the file alleges the dredge sank in March 1925",
            aliases: ["sinking of dredge"]
        ),
        GroupedItem(
            claimId: "e2",
            displayName: "Renuncia del capitán",
            context: "Caddy is reported to have resigned",
            aliases: []
        )
    ]
    static let dates: [GroupedItem] = [
        GroupedItem(
            claimId: "d1",
            displayName: "1922-08-24: el naufragio de la draga",
            context: "1922-08-24",
            aliases: []
        ),
        GroupedItem(
            claimId: "d2",
            displayName: "1925-03-15: investigación judicial",
            context: "1925-03-15",
            aliases: []
        )
    ]
    static let keywords: [GroupedItem] = [
        GroupedItem(claimId: "k1", displayName: "minería", context: "", aliases: []),
        GroupedItem(claimId: "k2", displayName: "draga", context: "", aliases: []),
        GroupedItem(claimId: "k3", displayName: "Chocó", context: "", aliases: []),
        GroupedItem(claimId: "k4", displayName: "Condoto", context: "", aliases: []),
        GroupedItem(claimId: "k5", displayName: "naufragio", context: "", aliases: []),
        GroupedItem(claimId: "k6", displayName: "sumario", context: "", aliases: []),
        GroupedItem(claimId: "k7", displayName: "platino", context: "", aliases: []),
        GroupedItem(claimId: "k8", displayName: "British Platinum", context: "", aliases: [])
    ]

    static let allGroups: [(EntityKind, [GroupedItem])] = [
        (.concept, keywords),
        (.person, people),
        (.location, places),
        (.organization, organizations),
        (.event, events),
        (.date, dates)
    ]
}

/// Preview-only surface for the KG section. Takes pre-baked groups so
/// previews can render every entity kind without a running backend.
struct KnowledgeGraphPreviewSurface: View {
    let groups: [(EntityKind, [GroupedItem])]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "circle.hexagongrid")
                Text("Knowledge Graph")
                    .font(.headline)
                Spacer()
                Image(systemName: "line.3.horizontal.decrease.circle")
                    .foregroundStyle(.secondary)
                Image(systemName: "arrow.clockwise")
                    .foregroundStyle(.secondary)
            }
            .foregroundStyle(.primary)

            ForEach(groups, id: \.0) { kind, items in
                EntityKindBlock(kind: kind, items: items)
            }
        }
        .padding()
        .frame(width: 320)
        .environment(ClaimFocusState.shared)
        .environment(KGFocusState.shared)
    }
}

#Preview("KG — full") {
    ScrollView {
        KnowledgeGraphPreviewSurface(groups: PreviewMocks.allGroups)
    }
    .frame(height: 700)
}

#Preview("KG — keywords only (inline row)") {
    KnowledgeGraphPreviewSurface(groups: [(.concept, PreviewMocks.keywords)])
}

#Preview("KG — people row") {
    KnowledgeGraphPreviewSurface(groups: [(.person, PreviewMocks.people)])
}

#Preview("KG — dates (no duplicate context)") {
    KnowledgeGraphPreviewSurface(groups: [(.date, PreviewMocks.dates)])
}

#Preview("KG — empty") {
    VStack(alignment: .leading, spacing: 12) {
        HStack {
            Image(systemName: "circle.hexagongrid")
            Text("Knowledge Graph").font(.headline)
            Spacer()
        }
        Text("No knowledge-graph entries for this document yet.")
            .font(.caption)
            .foregroundStyle(.secondary)
    }
    .padding()
    .frame(width: 320, height: 200)
}
