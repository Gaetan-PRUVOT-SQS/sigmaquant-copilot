import Foundation

/// Persistance des conversations en un fichier JSON unique sous
/// ~/Library/Application Support/SigmaQuantCopilot/conversations.json
enum ConversationStore {
    private static var fileURL: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("SigmaQuantCopilot", isDirectory: true)
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        return base.appendingPathComponent("conversations.json")
    }

    static func load() -> [Conversation] {
        guard let data = try? Data(contentsOf: fileURL),
              var list = try? JSONDecoder().decode([Conversation].self, from: data) else { return [] }
        // Assainit un message resté en génération (app fermée en plein calcul).
        for i in list.indices {
            list[i].messages.removeAll { $0.role == "assistant" && $0.pending }
        }
        return list.filter { !$0.messages.isEmpty }
    }

    static func save(_ convos: [Conversation]) {
        guard let data = try? JSONEncoder().encode(convos) else { return }
        try? data.write(to: fileURL, options: .atomic)
    }
}
