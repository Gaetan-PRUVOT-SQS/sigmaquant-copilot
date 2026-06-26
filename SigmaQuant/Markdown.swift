import SwiftUI
import AppKit

/// Retire le bloc ```engine``` (requête du modèle) et la queue « Engine result/error »
/// (déjà fournie en structuré par le back-end).
func cleanProse(_ final: String) -> String {
    var t = final.replacingOccurrences(
        of: "```engine[\\s\\S]*?```", with: "", options: .regularExpression)
    for marker in ["**Engine result", "**Engine error", "**Engine:"] {
        if let r = t.range(of: marker) { t = String(t[..<r.lowerBound]) }
    }
    t = t.replacingOccurrences(of: "\n{3,}", with: "\n\n", options: .regularExpression)
    return t.trimmingCharacters(in: .whitespacesAndNewlines)
}

/// Petit rendu markdown en SwiftUI : paragraphes, listes à puces, blocs de code.
struct MarkdownText: View {
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            ForEach(Array(blocks().enumerated()), id: \.offset) { _, block in
                switch block {
                case .paragraph(let s): inline(s)
                case .bullets(let items):
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(items.enumerated()), id: \.offset) { _, it in
                            HStack(alignment: .top, spacing: 8) {
                                Text("•").foregroundColor(Theme.muted)
                                inline(it)
                            }
                        }
                    }
                case .code(let lang, let code): CodeBlock(lang: lang, code: code)
                }
            }
        }
    }

    private func inline(_ s: String) -> Text {
        if let attr = try? AttributedString(
            markdown: s, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
            return Text(attr).foregroundColor(Theme.text)
        }
        return Text(s).foregroundColor(Theme.text)
    }

    private enum Block { case paragraph(String); case bullets([String]); case code(String, String) }

    private func blocks() -> [Block] {
        let lines = text.components(separatedBy: "\n")
        var out: [Block] = []; var i = 0
        var para: [String] = []; var bullets: [String] = []
        func flushPara() { if !para.isEmpty { out.append(.paragraph(para.joined(separator: "\n"))); para = [] } }
        func flushBul() { if !bullets.isEmpty { out.append(.bullets(bullets)); bullets = [] } }
        while i < lines.count {
            let line = lines[i]
            if let m = line.range(of: "^```(\\w*)\\s*$", options: .regularExpression) {
                flushPara(); flushBul()
                let lang = String(line[m]).replacingOccurrences(of: "`", with: "").trimmingCharacters(in: .whitespaces)
                i += 1; var code: [String] = []
                while i < lines.count, lines[i].range(of: "^```\\s*$", options: .regularExpression) == nil { code.append(lines[i]); i += 1 }
                i += 1
                out.append(.code(lang.isEmpty ? "code" : lang, code.joined(separator: "\n")))
                continue
            }
            if let m = line.range(of: "^\\s*[-*]\\s+", options: .regularExpression) {
                flushPara(); bullets.append(String(line[m.upperBound...])); i += 1; continue
            }
            if line.trimmingCharacters(in: .whitespaces).isEmpty { flushPara(); flushBul(); i += 1; continue }
            flushBul(); para.append(line); i += 1
        }
        flushPara(); flushBul()
        return out
    }
}

struct CodeBlock: View {
    let lang: String; let code: String
    @State private var copied = false
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(lang).font(.sq(11)).foregroundColor(Theme.muted)
                Spacer()
                Button {
                    NSPasteboard.general.clearContents(); NSPasteboard.general.setString(code, forType: .string)
                    copied = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) { copied = false }
                } label: { Text(copied ? "✓ Copié" : "Copier").font(.sq(11)).foregroundColor(Theme.muted) }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(Color.white.opacity(0.03))
            Divider().overlay(Theme.border)
            ScrollView(.horizontal, showsIndicators: false) {
                Text(code).font(.sqMono(12)).foregroundColor(Color(hex: 0xD7D7DF))
                    .padding(12).textSelection(.enabled)
            }
        }
        .background(Color(hex: 0x0E0E11))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(Theme.border, lineWidth: 1))
    }
}
