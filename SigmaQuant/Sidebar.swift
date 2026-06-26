import SwiftUI

struct Sidebar: View {
    @EnvironmentObject var vm: ChatViewModel
    @FocusState private var searchFocused: Bool
    @State private var renamingId: String?
    @State private var renameText = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            brand
            newButton
            searchField
            list
            Spacer(minLength: 0)
            footer
        }
        .padding(.horizontal, 14).padding(.top, 38).padding(.bottom, 12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Theme.sidebar)
        .alert("Renommer la conversation", isPresented: Binding(
            get: { renamingId != nil }, set: { if !$0 { renamingId = nil } })) {
            TextField("Titre", text: $renameText)
            Button("Renommer") { if let id = renamingId { vm.rename(id, to: renameText) }; renamingId = nil }
            Button("Annuler", role: .cancel) { renamingId = nil }
        }
        // raccourcis invisibles
        .background(Button("") { vm.newConversation() }.keyboardShortcut("n").hidden())
        .background(Button("") { searchFocused = true }.keyboardShortcut("k").hidden())
    }

    private var brand: some View {
        HStack(spacing: 10) {
            DiamondMark(size: 26)
            VStack(alignment: .leading, spacing: 1) {
                Text("SigmaQuant").font(.sq(15, .bold)).foregroundColor(.white)
                Text("SYSTEMS").font(.sq(10, .medium)).tracking(3).foregroundColor(.white.opacity(0.55))
            }
        }
        .padding(.horizontal, 4).padding(.bottom, 2)
    }

    private var newButton: some View {
        Button { vm.newConversation() } label: {
            HStack {
                Text("Nouvelle discussion").font(.sq(13, .medium))
                Spacer()
                Text("⌘N").font(.sqMono(11)).foregroundColor(.white.opacity(0.55))
            }
            .foregroundColor(.white)
            .padding(.horizontal, 12).padding(.vertical, 10)
            .background(Theme.crimsonHi.opacity(0.18))
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(Theme.crimsonHi.opacity(0.5), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").font(.system(size: 12)).foregroundColor(.white.opacity(0.5))
            TextField("Rechercher", text: $vm.search)
                .textFieldStyle(.plain).font(.sq(13)).foregroundColor(Theme.text)
                .focused($searchFocused)
            Text("⌘K").font(.sqMono(10)).foregroundColor(.white.opacity(0.45))
        }
        .padding(.horizontal, 11).padding(.vertical, 8)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(Color.white.opacity(0.12), lineWidth: 1))
    }

    private var list: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 4) {
                if vm.grouped.isEmpty {
                    Text(vm.search.isEmpty ? "Aucune conversation" : "Aucun résultat")
                        .font(.sq(12)).foregroundColor(.white.opacity(0.45)).padding(8)
                }
                ForEach(vm.grouped, id: \.0) { (label, items) in
                    Text(label.uppercased()).font(.sq(10, .semibold)).tracking(1.4)
                        .foregroundColor(.white.opacity(0.45)).padding(.horizontal, 8).padding(.top, 10).padding(.bottom, 2)
                    ForEach(items) { conv in row(conv) }
                }
            }
        }
    }

    private func row(_ conv: Conversation) -> some View {
        let selected = conv.id == vm.currentId
        return HStack(spacing: 6) {
            Text(conv.title).font(.sq(13, selected ? .semibold : .regular))
                .foregroundColor(selected ? .white : .white.opacity(0.82))
                .lineLimit(1)
            Spacer(minLength: 0)
            Button { vm.delete(conv.id) } label: {
                Image(systemName: "xmark").font(.system(size: 10)).foregroundColor(.white.opacity(0.55))
            }
            .buttonStyle(.plain).opacity(selected ? 0.8 : 0)
        }
        .padding(.horizontal, 10).padding(.vertical, 8)
        .background(selected ? Theme.crimsonHi.opacity(0.18) : .clear)
        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        .contentShape(Rectangle())
        .onTapGesture { vm.open(conv.id) }
        .contextMenu {
            Button("Renommer") { renameText = conv.title; renamingId = conv.id }
            Button("Supprimer", role: .destructive) { vm.delete(conv.id) }
        }
    }

    private var footer: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("SigmaQuantSystemsLab 2.0").font(.sq(12, .semibold)).foregroundColor(.white)
            Text("Moteur déterministe · local").font(.sq(11)).foregroundColor(.white.opacity(0.5))
        }
        .padding(.horizontal, 8).padding(.top, 10)
        .overlay(Rectangle().frame(height: 1).foregroundColor(.white.opacity(0.1)), alignment: .top)
    }
}
