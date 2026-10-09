import Foundation

// Setup's saved answers and the five ways in, the value types `RecipeSetupStore` reads and saves; moved out
// of RecipeSetupStore.swift unchanged so it stays under the file-length limit (#5618).

/// The five ways material comes in, as setup offers them (`source.onboard.five-ways-in`): the
/// import's four modes, and Keep arranged, which imports as Index and also keeps the folder
/// arranged (#5480). Saved in `answers.ingest_mode` by the engine's lowercase name.
enum SetupWayIn: String, CaseIterable, Identifiable {
    case link, copy, move, index
    case keepArranged = "keep-arranged"

    var id: String { rawValue }

    init(_ mode: IngestMode) {
        switch mode {
        case .link: self = .link
        case .copy: self = .copy
        case .move: self = .move
        case .index: self = .index
        }
    }

    /// A saved `ingest_mode` ("link", "index", "keep-arranged", any case); nil for one Fichero
    /// does not know (never a silent fallback to link).
    init?(savedName: String) {
        self.init(rawValue: savedName.lowercased())
    }

    var savedName: String { rawValue }

    /// The import's own mode: Keep arranged imports as Index.
    var ingestMode: IngestMode {
        switch self {
        case .link: .link
        case .copy: .copy
        case .move: .move
        case .index, .keepArranged: .index
        }
    }

    var title: String {
        switch self {
        case .link: "Link"
        case .copy: "Copy"
        case .move: "Move"
        case .index: "Index"
        case .keepArranged: "Keep arranged"
        }
    }

    /// One sentence: what this way does to the originals.
    var sentence: String {
        switch self {
        case .link: "Fichero reads the files where they are and never changes the originals."
        case .copy: "Fichero makes its own copy in the project; the originals are never touched."
        case .move: "The files move into the project, stored in the app; the originals are removed from where they were."
        case .index: "Fichero works on the folder in place and writes its changes back into the original files, "
            + "keeping that folder up to date. For folders; single files are linked."
        case .keepArranged: "As Index, and Fichero also moves files inside the folder to follow the project's folders; "
            + "you see what would move before anything does."
        }
    }
}

/// The answers as saved: the engine's own field names.
struct RecipeSetupAnswers: Codable, Equatable {
    var purposes: [String]?
    /// Read only: a project saved before 2026-10-05 (a list of one).
    var purpose: String?
    var jobs: [String]?
    /// Steps (by job) taken out of the plan on Ready (#5627, `answers.removed_jobs`).
    var removedJobs: [String]?
    var languages: [String]?
    var scripts: [String]?
    var directions: [String: String]?
    var materials: [String]?
    /// Read only, as `purpose`.
    var material: String?
    var pages: Int?
    var cloudAllowed: Bool?
    var ingestMode: String?
    var layers: [String]?
    var automatic: Automatic?
    var jobAnswers: JobAnswers?

    /// What runs by itself after Start (`answers.automatic`).
    struct Automatic: Codable, Equatable {
        /// False is "Nothing runs automatically": an import after Start runs nothing.
        var runs: Bool
        /// The recipe steps (by job) an import runs over the pages it brought.
        var steps: [String]
    }

    /// The questions a ticked purpose opens under it on What you want to do (`answers.job_answers`).
    struct JobAnswers: Codable, Equatable {
        /// Entities (`find-names-tag-words`): the kinds to find.
        var entityKinds: [String] = ["people", "places"]
        /// Translate or normalise: how far (as-written, expanded, normalised).
        var normaliseHowFar: String = "expanded"
        /// Map places (`place-in-a-gazetteer`): which gazetteer.
        var gazetteer: String = "geonames"

        enum CodingKeys: String, CodingKey {
            case entityKinds = "entity_kinds"
            case normaliseHowFar = "normalise_how_far"
            case gazetteer
        }

        init() {}

        /// A field not saved yet keeps its default.
        init(from decoder: Decoder) throws {
            let values = try decoder.container(keyedBy: CodingKeys.self)
            entityKinds = try values.decodeIfPresent([String].self, forKey: .entityKinds) ?? entityKinds
            normaliseHowFar = try values.decodeIfPresent(String.self, forKey: .normaliseHowFar) ?? normaliseHowFar
            gazetteer = try values.decodeIfPresent(String.self, forKey: .gazetteer) ?? gazetteer
        }
    }

    init(purposes: [String]? = nil, jobs: [String]? = nil, languages: [String]? = nil,
         scripts: [String]? = nil, directions: [String: String]? = nil, materials: [String]? = nil,
         pages: Int? = nil, cloudAllowed: Bool? = nil, ingestMode: String? = nil, layers: [String]? = nil,
         automatic: Automatic? = nil, jobAnswers: JobAnswers? = nil, removedJobs: [String]? = nil) {
        self.purposes = purposes
        self.jobs = jobs
        self.removedJobs = removedJobs
        self.languages = languages
        self.scripts = scripts
        self.directions = directions
        self.materials = materials
        self.pages = pages
        self.cloudAllowed = cloudAllowed
        self.ingestMode = ingestMode
        self.layers = layers
        self.automatic = automatic
        self.jobAnswers = jobAnswers
    }

    enum CodingKeys: String, CodingKey {
        case purposes, purpose, jobs, languages, scripts, directions, materials, material, pages, layers, automatic
        case cloudAllowed = "cloud_allowed"
        case ingestMode = "ingest_mode"
        case jobAnswers = "job_answers"
        case removedJobs = "removed_jobs"
    }
}
