import Foundation

/// Message du fil. Pour l'assistant, `text` contient la réponse brute du back-end (`final`,
/// déjà naturalisée) ; on la nettoie à l'affichage. `engine` = champs scalaires du résultat moteur.
struct ChatMessage: Identifiable, Codable, Equatable {
    var id: UUID = UUID()
    var role: String                 // "user" | "assistant"
    var text: String
    var engine: [EngineField]?       // résultat moteur (ordre préservé)
    var error: String?
    var createdAt: Double = Date().timeIntervalSince1970
    var pending: Bool = false

    var timeString: String {
        let f = DateFormatter(); f.dateFormat = "HH:mm"
        return f.string(from: Date(timeIntervalSince1970: createdAt))
    }
}

/// Une paire clé/valeur scalaire du résultat moteur (ordre conservé pour l'affichage).
struct EngineField: Codable, Equatable, Identifiable {
    var id: String { key }
    let key: String
    let value: String          // déjà formaté (nombre ou court texte)
}

struct Conversation: Identifiable, Codable, Equatable {
    var id: String
    var title: String
    var messages: [ChatMessage]
    var updatedAt: Double
}

func newId() -> String {
    String(UInt64(Date().timeIntervalSince1970 * 1000)) + "-" + String(Int.random(in: 1000...9999))
}
