import SwiftUI

@MainActor
final class ChatViewModel: ObservableObject {
    @Published var conversations: [Conversation] = []
    @Published var currentId: String?
    @Published var draft = ""
    @Published var search = ""
    @Published var ready = false
    @Published var busy = false
    @Published var startupError: String?

    private let backend = Backend()

    init() {
        conversations = ConversationStore.load()
        currentId = conversations.sorted { $0.updatedAt > $1.updatedAt }.first?.id
        backend.start()
        poll()
    }

    func shutdown() { backend.stop() }

    // MARK: - dérivés
    var current: Conversation? { conversations.first { $0.id == currentId } }
    var messages: [ChatMessage] { current?.messages ?? [] }
    var canSend: Bool { ready && !busy && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    /// Conversations filtrées par recherche, groupées par date (ordre fixe).
    var grouped: [(String, [Conversation])] {
        let q = search.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let list = conversations
            .filter { q.isEmpty || $0.title.lowercased().contains(q)
                      || $0.messages.contains { $0.text.lowercased().contains(q) } }
            .sorted { $0.updatedAt > $1.updatedAt }
        let order = ["Aujourd'hui", "7 derniers jours", "30 derniers jours", "Plus ancien"]
        var buckets: [String: [Conversation]] = [:]
        for c in list { buckets[label(c.updatedAt), default: []].append(c) }
        return order.compactMap { key in
            guard let items = buckets[key], !items.isEmpty else { return nil }
            return (key, items)
        }
    }

    private func label(_ ts: Double) -> String {
        let now = Date().timeIntervalSince1970
        let startToday = Calendar.current.startOfDay(for: Date()).timeIntervalSince1970
        if ts >= startToday { return "Aujourd'hui" }
        if ts >= now - 7 * 86400 { return "7 derniers jours" }
        if ts >= now - 30 * 86400 { return "30 derniers jours" }
        return "Plus ancien"
    }

    // MARK: - santé
    private func poll() {
        Task {
            let (r, err) = await backend.health()
            ready = r
            if !ready { startupError = err }
            if !r {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                poll()
            }
        }
    }

    // MARK: - actions
    func newConversation() { currentId = nil; draft = "" }
    func open(_ id: String) { currentId = id }

    func rename(_ id: String, to title: String) {
        guard let i = conversations.firstIndex(where: { $0.id == id }) else { return }
        let t = title.trimmingCharacters(in: .whitespacesAndNewlines)
        if !t.isEmpty { conversations[i].title = String(t.prefix(80)); persist() }
    }

    func delete(_ id: String) {
        conversations.removeAll { $0.id == id }
        if currentId == id { currentId = nil }
        persist()
    }

    func regenerate() {
        guard !busy, let i = currentIndex() else { return }
        if conversations[i].messages.last?.role == "assistant" { conversations[i].messages.removeLast() }
        guard let lastUser = conversations[i].messages.last(where: { $0.role == "user" })?.text else { return }
        persist()
        send(lastUser, regen: true)
    }

    func send(_ qIn: String? = nil, regen: Bool = false) {
        let q = (qIn ?? draft).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty, !busy, ready else { return }
        busy = true
        if !regen { draft = "" }

        var idx: Int
        if let i = currentIndex() { idx = i }
        else {
            let c = Conversation(id: newId(), title: String(q.prefix(46)) + (q.count > 46 ? "…" : ""),
                                 messages: [], updatedAt: Date().timeIntervalSince1970)
            conversations.append(c); currentId = c.id; idx = conversations.count - 1
        }
        if !regen { conversations[idx].messages.append(ChatMessage(role: "user", text: q)) }
        conversations[idx].messages.append(ChatMessage(role: "assistant", text: "", pending: true))
        conversations[idx].updatedAt = Date().timeIntervalSince1970
        let convId = conversations[idx].id
        persist()

        Task {
            var final = "", err: String? = nil; var engine: [EngineField]? = nil
            do {
                let a = try await backend.ask(q)
                final = a.final; engine = a.engine; err = a.error
            } catch { err = error.localizedDescription }
            if let i = conversations.firstIndex(where: { $0.id == convId }),
               let mi = conversations[i].messages.lastIndex(where: { $0.role == "assistant" }) {
                conversations[i].messages[mi].text = final
                conversations[i].messages[mi].engine = engine
                conversations[i].messages[mi].error = err
                conversations[i].messages[mi].pending = false
                conversations[i].messages[mi].createdAt = Date().timeIntervalSince1970
                conversations[i].updatedAt = Date().timeIntervalSince1970
            }
            busy = false
            persist()
        }
    }

    private func currentIndex() -> Int? { conversations.firstIndex { $0.id == currentId } }
    private func persist() { ConversationStore.save(conversations) }
}
