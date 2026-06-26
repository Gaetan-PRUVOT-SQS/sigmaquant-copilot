import SwiftUI

struct RootView: View {
    var body: some View {
        HStack(spacing: 0) {
            Sidebar().frame(width: 270)
            ChatView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(ZStack { Theme.bg; Theme.mainGlow })
        }
        .ignoresSafeArea()
        .background(Theme.bg)
    }
}
