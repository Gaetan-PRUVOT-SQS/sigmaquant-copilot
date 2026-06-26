import SwiftUI

struct ChatView: View {
    @EnvironmentObject var vm: ChatViewModel

    private let suggestions: [(String, String)] = [
        ("Fondations", "Valorise un call européen — spot 120, strike 110, 1 an, r 4 %, vol 25 %."),
        ("Crédit", "Spread CDS au pair sur 5 ans, hasard 2 %, recouvrement 40 %."),
        ("Portefeuille", "Ratio de Sharpe : rendement 12 %, taux sans risque 3 %, volatilité 18 %."),
        ("Avancé", "Densité de Breeden-Litzenberger, strikes 80 90 100 110 120."),
    ]

    var body: some View {
        VStack(spacing: 0) {
            topbar
            Divider().overlay(Theme.border)
            if vm.messages.isEmpty { welcome } else { thread }
            composer
        }
    }

    // MARK: - top bar
    private var topbar: some View {
        HStack {
            Text(vm.current?.title ?? "Nouvelle discussion")
                .font(.sq(13)).foregroundColor(Theme.muted).lineLimit(1)
                .padding(.leading, 72)
            Spacer()
            statusPill
        }
        .frame(height: 52).padding(.horizontal, 22)
    }

    private var statusPill: some View {
        HStack(spacing: 7) {
            Circle().fill(pillColor).frame(width: 7, height: 7)
                .shadow(color: pillColor, radius: 4)
            Text(pillText).font(.sq(12)).foregroundColor(vm.startupError != nil && !vm.ready ? Theme.danger : Theme.muted)
        }
    }
    private var pillColor: Color { vm.ready ? Theme.success : (vm.startupError != nil ? Theme.danger : Theme.warn) }
    private var pillText: String {
        if vm.ready { return "Moteur local prêt · 100 % offline" }
        if let e = vm.startupError { return e }
        return "Démarrage du moteur local…"
    }

    // MARK: - accueil
    private var welcome: some View {
        ScrollView {
            VStack(spacing: 12) {
                Spacer().frame(height: 56)
                Text("COPILOTE QUANTITATIF").font(.sq(11, .semibold)).tracking(2.2).foregroundColor(Theme.accent)
                Text("Bonjour. Posez votre question quantitative.")
                    .font(.sq(28, .semibold)).foregroundColor(Theme.text).multilineTextAlignment(.center)
                Text("Je pose les hypothèses et la méthode, puis délègue chaque nombre au moteur déterministe — exact et auditable.")
                    .font(.sq(15)).foregroundColor(Theme.muted).multilineTextAlignment(.center).frame(maxWidth: 560)
                    .padding(.bottom, 8)
                LazyVGrid(columns: [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)], spacing: 12) {
                    ForEach(suggestions, id: \.0) { tag, q in card(tag, q) }
                }
                .frame(maxWidth: 720)
                Spacer()
            }
            .frame(maxWidth: .infinity).padding(.horizontal, 28)
        }
    }

    private func card(_ tag: String, _ q: String) -> some View {
        Button { vm.send(q) } label: {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 4) { Text(tag); Text("↗").opacity(0.8) }
                    .font(.sq(12, .semibold)).foregroundColor(Theme.accent)
                Text(q).font(.sq(13.5)).foregroundColor(Theme.muted).multilineTextAlignment(.leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(16)
            .background(LinearGradient(colors: [Theme.panel2, Theme.panel], startPoint: .top, endPoint: .bottom))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Theme.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    // MARK: - fil
    private var thread: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 22) {
                    ForEach(vm.messages) { m in
                        MessageRow(message: m, isLast: m.id == vm.messages.last?.id).id(m.id)
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .frame(maxWidth: 820).frame(maxWidth: .infinity).padding(.horizontal, 28).padding(.vertical, 20)
            }
            .onChange(of: vm.messages.count) { _ in withAnimation(.easeOut(duration: 0.18)) { proxy.scrollTo("bottom") } }
            .onChange(of: vm.messages.last?.text) { _ in proxy.scrollTo("bottom") }
        }
    }

    // MARK: - saisie
    private var composer: some View {
        VStack(spacing: 10) {
            HStack(alignment: .bottom, spacing: 0) {
                TextField("Écris au copilote — calcul, CDO, perpétuité, grecques…", text: $vm.draft, axis: .vertical)
                    .textFieldStyle(.plain).font(.sq(14.5)).foregroundColor(Theme.text)
                    .lineLimit(1...6).padding(.horizontal, 16).padding(.vertical, 13)
                    .onSubmit { vm.send() }
                Button { vm.send() } label: {
                    Image(systemName: "arrow.up").font(.system(size: 15, weight: .bold)).foregroundColor(.white)
                        .frame(width: 34, height: 34)
                        .background(vm.canSend ? Theme.crimson : Theme.panel2)
                        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
                .buttonStyle(.plain).disabled(!vm.canSend).keyboardShortcut(.return, modifiers: .command)
                .padding(6)
            }
            .background(Theme.panel)
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Theme.borderStrong, lineWidth: 1))
            .frame(maxWidth: 820)

            HStack(spacing: 8) {
                ForEach(["routage auto · 01–05", "100 % local", "Moteur exact"], id: \.self) { chip($0) }
            }
            Text("SigmaQuantSystemsLab peut se tromper · chaque nombre provient du moteur déterministe · ne constitue pas un conseil en investissement.")
                .font(.sq(11)).foregroundColor(Theme.faint).multilineTextAlignment(.center)
        }
        .padding(.horizontal, 28).padding(.top, 8).padding(.bottom, 16)
    }

    private func chip(_ t: String) -> some View {
        Text(t).font(.sq(11)).foregroundColor(Theme.muted)
            .padding(.horizontal, 10).padding(.vertical, 4)
            .background(Color.white.opacity(0.03))
            .clipShape(Capsule())
            .overlay(Capsule().stroke(Theme.border, lineWidth: 1))
    }
}
