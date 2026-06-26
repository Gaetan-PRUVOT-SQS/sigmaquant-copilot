import SwiftUI

/// Identité visuelle SigmaQuant — noir + bordeaux/crimson (portée 1:1 depuis le front web).
enum Theme {
    static let bg          = Color(hex: 0x0B0B0D)
    static let panel       = Color(hex: 0x16161A)
    static let panel2      = Color(hex: 0x1C1C21)
    static let bubble      = Color(hex: 0x1C1C21)
    static let input       = Color(hex: 0x16161A)

    static let text        = Color(hex: 0xF4F4F6)
    static let muted       = Color(hex: 0x9A9AA4)
    static let faint       = Color(hex: 0x6E6E78)

    static let crimson     = Color(hex: 0xD12B2B)
    static let crimsonHi   = Color(hex: 0xF0392C)
    static let accent      = Color(hex: 0xE0563F)

    static let success     = Color(hex: 0x34C759)
    static let warn        = Color(hex: 0xF3C173)
    static let danger      = Color(hex: 0xFF453A)

    static let border      = Color.white.opacity(0.07)
    static let borderStrong = Color.white.opacity(0.12)

    // Dégradé de la sidebar (bordeaux profond -> presque noir).
    static let sidebar = LinearGradient(
        colors: [Color(hex: 0x4A0F17), Color(hex: 0x2C0A0F), Color(hex: 0x1A0608)],
        startPoint: .top, endPoint: .bottom)

    // Halo crimson en haut de la zone principale.
    static let mainGlow = RadialGradient(
        colors: [Color(hex: 0xD12B2B).opacity(0.10), .clear],
        center: .init(x: 0.72, y: -0.05), startRadius: 0, endRadius: 520)
}

/// Marque losange/aigle stylisée (équivalent du brand-mark CSS).
struct DiamondMark: View {
    var size: CGFloat = 26
    var body: some View {
        RoundedRectangle(cornerRadius: size * 0.27, style: .continuous)
            .fill(AngularGradient(colors: [Theme.crimsonHi, Color(hex: 0x7A0C12), Theme.crimsonHi],
                                  center: .center, angle: .degrees(210)))
            .frame(width: size, height: size)
            .overlay(RoundedRectangle(cornerRadius: size * 0.27, style: .continuous)
                .stroke(Color.white.opacity(0.15), lineWidth: 1))
            .shadow(color: Theme.crimsonHi.opacity(0.35), radius: size * 0.25)
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255,
                  opacity: 1)
    }
}

// Polices système (natives, aucune dépendance) — SF Pro + SF Mono.
extension Font {
    static func sq(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font { .system(size: size, weight: weight) }
    static func sqMono(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font { .system(size: size, weight: weight, design: .monospaced) }
}
