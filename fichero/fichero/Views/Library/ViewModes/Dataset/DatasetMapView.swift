import MapKit
import SwiftUI

// MARK: - Map renderer (datasets Stage 2)

/// Rows with a geo-role attribute ("lat,lon") pinned on a map. Rows without
/// a parseable coordinate are counted honestly beneath, never dropped
/// silently.
struct DatasetMapView: View {
    let store: DatasetModeStore
    var onOpen: (DatasetPage.Row) -> Void = { _ in }

    private struct Pin: Identifiable {
        let row: DatasetPage.Row
        let coordinate: CLLocationCoordinate2D
        var id: String { row.id }
    }

    private var pins: [Pin] {
        (store.page?.rows ?? []).compactMap { row in
            store.coordinate(of: row).map {
                Pin(
                    row: row,
                    coordinate: CLLocationCoordinate2D(latitude: $0.lat, longitude: $0.lon)
                )
            }
        }
    }

    var body: some View {
        if store.attributeForRole["geo"] == nil {
            DatasetMissingRoleView(role: "geo", renderer: "map")
        } else {
            let located = pins
            let unlocated = (store.page?.rows.count ?? 0) - located.count
            VStack(spacing: 0) {
                Map {
                    ForEach(located) { pin in
                        Annotation(pin.row.name, coordinate: pin.coordinate) {
                            Image(systemName: "mappin.circle.fill")
                                .font(.title3)
                                .foregroundStyle(.red)
                                .onTapGesture(count: 2) { onOpen(pin.row) }
                                // Touch parity: iPad has no double-click.
                                .contextMenu { Button("Open") { onOpen(pin.row) } }
                        }
                    }
                }
                if unlocated > 0 {
                    Divider()
                    Text(
                        "\(unlocated) item\(unlocated == 1 ? "" : "s") without a "
                            + "readable “lat,lon” coordinate not shown"
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 6)
                }
            }
        }
    }
}

#Preview("Map — diary") {
    DatasetMapView(store: .previewDiary())
        .frame(width: 720, height: 560)
}
