import SwiftUI
import AppKit

struct MessageRow: View {
    @EnvironmentObject var vm: ChatViewModel
    let message: ChatMessage
    var isLast: Bool

    var body: some View {
        if message.role == "user" { userRow } else { assistantRow }
    }

    private var userRow: some View {
        HStack {
            Spacer(minLength: 60)
            VStack(alignment: .trailing, spacing: 6) {
                Text(message.text).font(.sq(14.5)).foregroundColor(Theme.text).textSelection(.enabled)
                    .padding(.horizontal, 15).padding(.vertical, 11)
                    .background(Theme.bubble)
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Theme.border, lineWidth: 1))
                Text(message.timeString).font(.sq(11)).foregroundColor(Theme.faint)
            }
        }
    }

    private var assistantRow: some View {
        HStack(alignment: .top, spacing: 12) {
            DiamondMark(size: 26)
            VStack(alignment: .leading, spacing: 8) {
                if message.pending {
                    TypingDots()
                } else {
                    let prose = cleanProse(message.text)
                    if !prose.isEmpty { MarkdownText(text: prose) }
                    if let engine = message.engine { EngineCard(fields: engine) }
                    if let err = message.error, message.engine == nil { noteCard(err) }
                    actions
                }
            }
            Spacer(minLength: 40)
        }
    }

    private func noteCard(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("MOTEUR — NOTE").font(.sq(11, .bold)).tracking(1.4).foregroundColor(Theme.accent)
            Text(text).font(.sq(13)).foregroundColor(Theme.muted)
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.accent.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(Theme.accent.opacity(0.4), lineWidth: 1))
    }

    private var actions: some View {
        HStack(spacing: 16) {
            actionButton("Copier") {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(cleanProse(message.text), forType: .string)
            }
            if isLast && !vm.busy {
                actionButton("Régénérer") { vm.regenerate() }
            }
            Spacer()
            Text(message.timeString).font(.sq(11)).foregroundColor(Theme.faint)
        }
        .padding(.top, 2)
    }

    private func actionButton(_ label: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) { Text(label).font(.sq(12)).foregroundColor(Theme.muted) }
            .buttonStyle(.plain)
    }
}

struct EngineCard: View {
    let fields: [EngineField]
    private let cols = [GridItem(.adaptive(minimum: 150), spacing: 18)]
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("RÉSULTAT DU MOTEUR · EXACT").font(.sq(11, .bold)).tracking(1.4).foregroundColor(Theme.accent)
                .padding(.top, 4)
            LazyVGrid(columns: cols, alignment: .leading, spacing: 6) {
                ForEach(fields) { f in
                    HStack {
                        Text(f.key).font(.sq(13)).foregroundColor(Theme.muted)
                        Spacer(minLength: 10)
                        Text(f.value).font(.sqMono(13, .semibold)).foregroundColor(.white)
                    }
                    .padding(.vertical, 5)
                    .overlay(Rectangle().frame(height: 1).foregroundColor(.white.opacity(0.06)), alignment: .top)
                }
            }
        }
        .padding(.horizontal, 14).padding(.bottom, 12).padding(.top, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.accent.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(Theme.accent.opacity(0.4), lineWidth: 1))
    }
}

struct TypingDots: View {
    @State private var phase = 0.0
    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<3) { i in
                Circle().fill(Theme.faint).frame(width: 6, height: 6)
                    .opacity(0.3 + 0.7 * abs(sin(phase + Double(i) * 0.6)))
            }
        }
        .onAppear {
            withAnimation(.easeInOut(duration: 1.1).repeatForever(autoreverses: false)) { phase = .pi * 2 }
        }
    }
}
