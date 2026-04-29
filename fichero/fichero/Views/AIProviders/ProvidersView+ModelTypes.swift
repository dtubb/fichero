import Foundation

enum ModelSortOrder: String, CaseIterable {
    case recommended = "Recommended"
    case name = "Name"
    case cheapest = "Cheapest"
    case context = "Context Size"
}

struct ModelFilters {
    var visionOnly = false
    var reasoningOnly = false
    var toolsOnly = false
    var audioOnly = false
    var pdfOnly = false
    var webSearchOnly = false
    var batchApiOnly = false
    var embeddingsOnly = false
    var imageGenOnly = false
    var speechOnly = false
}
