#!/usr/bin/env bash
# Rend le .app SwiftUI AUTONOME : injecte le modèle, le back-end figé (PyInstaller),
# le llama-server embarqué + ses dylibs et le prompt dans Contents/Resources, puis signe ad-hoc.
# Le Backend Swift résout Bundle.main.resourceURL (= Contents/Resources) en mode release.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"               # racine du dépôt (= projet de l'app)
APP="$ROOT/build/Build/Products/Release/SigmaQuant Copilot.app"
RES="$APP/Contents/Resources"

[ -d "$APP" ] || { echo "❌ .app introuvable : $APP (build d'abord)"; exit 1; }

LLAMA_SRC="$ROOT/resources/llama"
BACKEND_SRC="$ROOT/backend/dist/sqsl-backend"
MODEL_SRC="$ROOT/models/sqsl-2.0-Q4_K_M.gguf"
PROMPT_SRC="$ROOT/prompts/system_fr.txt"

for p in "$LLAMA_SRC/llama-server" "$BACKEND_SRC/sqsl-backend" "$MODEL_SRC" "$PROMPT_SRC"; do
  [ -e "$p" ] || { echo "❌ ressource manquante : $p"; exit 1; }
done

echo "▶ vérification fermeture de dylibs"
miss=0
for f in "$LLAMA_SRC"/*; do
  while read -r dep; do
    case "$dep" in
      /usr/lib/*|/System/*|"") ;;
      *) leaf="$(basename "$dep")"; [ -f "$LLAMA_SRC/$leaf" ] || { echo "  ❌ manque $leaf"; miss=1; } ;;
    esac
  done < <(otool -L "$f" 2>/dev/null | tail -n +2 | awk '{print $1}')
done
[ "$miss" -eq 0 ] || { echo "❌ fermeture incomplète"; exit 1; }
echo "  ✓ complète"

echo "▶ injection des ressources"
mkdir -p "$RES"
rm -rf "$RES/llama" "$RES/sqsl-backend" "$RES/models" "$RES/prompts"
cp -R "$LLAMA_SRC"   "$RES/llama"
cp -R "$BACKEND_SRC" "$RES/sqsl-backend"
mkdir -p "$RES/models" "$RES/prompts"
cp "$MODEL_SRC" "$RES/models/"
cp "$PROMPT_SRC" "$RES/prompts/"
chmod +x "$RES/llama/llama-server" "$RES/sqsl-backend/sqsl-backend"

echo "▶ signature ad-hoc (deep, sans hardened runtime)"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP" || { echo "❌ vérif signature KO"; exit 1; }
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true

echo "✅ .app natif autonome ($(du -sh "$APP" | cut -f1)) : $APP"
