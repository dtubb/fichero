import Foundation

struct FirstRunCardConfig {
    let icon: String
    let title: String
    let body: String
    let primaryTitle: String
    let primaryIcon: String
    let primaryAction: () -> Void
}

enum FirstRunStep: Int, CaseIterable, Identifiable {
    case welcome
    case library
    case permissions
    case cloud

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .welcome: return "Welcome"
        case .library: return "Library"
        case .permissions: return "Permissions"
        case .cloud: return "AI"
        }
    }

    var icon: String {
        switch self {
        case .welcome: return "sparkles"
        case .library: return "folder"
        case .permissions: return "lock.shield"
        case .cloud: return "brain"
        }
    }

    var next: FirstRunStep {
        FirstRunStep(rawValue: min(rawValue + 1, Self.cloud.rawValue)) ?? .cloud
    }

    var previous: FirstRunStep {
        FirstRunStep(rawValue: max(rawValue - 1, Self.welcome.rawValue)) ?? .welcome
    }
}
