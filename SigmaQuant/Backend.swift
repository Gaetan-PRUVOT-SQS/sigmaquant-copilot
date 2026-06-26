import Foundation

/// Gère le back-end local : lance le serveur Python (qui démarre lui-même llama-server sur le
/// modèle GGUF) et l'interroge en HTTP. Même chaîne que la version Tauri — UI native, back-end
/// prouvé. À l'arrêt, on SIGTERM le process Python (qui tue son llama-server enfant).
final class Backend {
    static let port = 8765
    private var process: Process?

    private let repoRoot = "/Users/gaetan/Desktop/sigmaquant-copilot-main"   // repli dev

    // MARK: - cycle de vie
    func start() {
        let p = Process()
        var env = ProcessInfo.processInfo.environment
        env["SQSL_BACKEND_PORT"] = String(Self.port)

        let res = Bundle.main.resourceURL
        let frozen = res?.appendingPathComponent("sqsl-backend/sqsl-backend")

        if let frozen, FileManager.default.fileExists(atPath: frozen.path) {
            // .app empaquetée : tout depuis Contents/Resources
            let r = res!
            p.executableURL = frozen
            env["SQSL_MODEL"] = r.appendingPathComponent("models/sqsl-2.0-Q4_K_M.gguf").path
            env["SQSL_SYSTEM_PROMPT"] = r.appendingPathComponent("prompts/system_fr.txt").path
            env["SQSL_LLAMA_BIN"] = r.appendingPathComponent("llama/llama-server").path
            env["SQSL_LLAMA_LIBDIR"] = r.appendingPathComponent("llama").path
        } else {
            // dev : arbre source + python/llama système
            p.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
            p.arguments = ["\(repoRoot)/backend/server.py"]
            env["SQSL_ROOT"] = repoRoot
            env["SQSL_MODEL"] = "\(repoRoot)/models/sqsl-2.0-Q4_K_M.gguf"
            env["SQSL_SYSTEM_PROMPT"] = "\(repoRoot)/prompts/system_fr.txt"
            env["SQSL_LLAMA_BIN"] = FileManager.default.fileExists(atPath: "/opt/homebrew/bin/llama-server")
                ? "/opt/homebrew/bin/llama-server" : "/usr/local/bin/llama-server"
        }
        p.environment = env
        do { try p.run(); process = p } catch { NSLog("Backend start failed: \(error)") }
    }

    func stop() {
        process?.terminate()        // SIGTERM -> le back-end tue son llama-server
        process = nil
    }

    // MARK: - HTTP
    private func url(_ path: String) -> URL { URL(string: "http://127.0.0.1:\(Self.port)\(path)")! }

    /// (ready, error)
    func health() async -> (Bool, String?) {
        var req = URLRequest(url: url("/health")); req.timeoutInterval = 5
        guard let (data, _) = try? await URLSession.shared.data(for: req),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            // injoignable : le process est-il mort ?
            if let p = process, !p.isRunning {
                return (false, "Le back-end local n'a pas pu démarrer.")
            }
            return (false, nil)
        }
        return (obj["ready"] as? Bool ?? false, obj["error"] as? String)
    }

    struct Answer { var final: String; var engine: [EngineField]?; var error: String? }

    func ask(_ question: String) async throws -> Answer {
        var req = URLRequest(url: url("/ask"))
        req.httpMethod = "POST"
        req.timeoutInterval = 330
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: ["question": question])
        let (data, _) = try await URLSession.shared.data(for: req)
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw NSError(domain: "sqsl", code: 1, userInfo: [NSLocalizedDescriptionKey: "réponse illisible"])
        }
        return Answer(final: obj["final"] as? String ?? "",
                      engine: engineFields(obj["engine"]),
                      error: obj["error"] as? String)
    }

    private func engineFields(_ raw: Any?) -> [EngineField]? {
        guard let dict = raw as? [String: Any] else { return nil }
        // Préserve un ordre stable et lisible.
        let order = ["call", "put", "forward", "pv", "sharpe", "expected_return", "expected_return_pct",
                     "delta_call", "delta_put", "par_spread_annual", "par_spread_bps", "survival",
                     "default_prob", "monthly_payment", "total_paid", "q_up", "q_down", "d1", "d2",
                     "risk_neutral_density", "expected_tranche_loss", "zcb_price", "rmse"]
        let keys = dict.keys.sorted { (a, b) in
            let ia = order.firstIndex(of: a) ?? 999, ib = order.firstIndex(of: b) ?? 999
            return ia != ib ? ia < ib : a < b
        }
        var fields: [EngineField] = []
        for k in keys {
            if let n = dict[k] as? NSNumber {
                if CFGetTypeID(n) == CFBooleanGetTypeID() { continue }   // ignore les booléens
                fields.append(EngineField(key: k, value: fmt(n.doubleValue)))
            } else if let s = dict[k] as? String, s.count <= 24 {
                fields.append(EngineField(key: k, value: s))
            }
        }
        return fields.isEmpty ? nil : fields
    }

    private func fmt(_ v: Double) -> String {
        if v == v.rounded() && abs(v) < 1e12 { return String(Int(v)) }
        var s = String(format: "%.6f", v)          // précision pleine (le back-end arrondit déjà à 6)
        while s.hasSuffix("0") { s.removeLast() }
        if s.hasSuffix(".") { s.removeLast() }
        return s
    }
}
