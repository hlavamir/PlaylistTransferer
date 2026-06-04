import Foundation

enum Screen {
    case main
    case importing(message: String)
    case results(ImportResult)
}

struct ImportResult {
    let playlistName: String
    let total: Int
    let matched: Int
    let added: Int
    let notFound: [NotFoundItem]
    let lowConfidence: [LowConfidenceItem]

    init(from dict: [String: Any]) {
        playlistName = dict["playlist_name"] as? String ?? ""
        total        = dict["total"]   as? Int ?? 0
        matched      = dict["matched"] as? Int ?? 0
        added        = dict["added"]   as? Int ?? 0

        notFound = (dict["not_found"] as? [[Any]] ?? []).compactMap { arr in
            guard let name  = arr[safe: 0] as? String,
                  let score = (arr[safe: 1] as? NSNumber)?.doubleValue else { return nil }
            return NotFoundItem(name: name, score: score)
        }

        lowConfidence = (dict["low_confidence"] as? [[Any]] ?? []).compactMap { arr in
            guard let spotify = arr[safe: 0] as? String,
                  let local   = arr[safe: 1] as? String,
                  let score   = (arr[safe: 2] as? NSNumber)?.doubleValue else { return nil }
            return LowConfidenceItem(spotify: spotify, local: local, score: score)
        }
    }
}

struct NotFoundItem: Identifiable {
    let id = UUID()
    let name: String
    let score: Double
}

struct LowConfidenceItem: Identifiable {
    let id = UUID()
    let spotify: String
    let local: String
    let score: Double
}

extension Array {
    subscript(safe index: Int) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}
