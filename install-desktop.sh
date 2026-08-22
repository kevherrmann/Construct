#!/usr/bin/env bash
# Trägt CONSTRUCT ins Anwendungsmenü / die Taskleiste ein (Linux).
# Einmal ausführen — danach ist Cody im Menü suchbar und anpinnbar.
#
#   ./install-desktop.sh            eintragen
#   ./install-desktop.sh --remove   wieder entfernen
set -euo pipefail
cd "$(dirname "$0")"

DIR=$(pwd)
APPS="$HOME/.local/share/applications"
FILE="$APPS/cody.desktop"

if [ "${1:-}" = "--remove" ]; then
  rm -f "$FILE"
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" || true
  echo "» Eintrag entfernt."
  exit 0
fi

mkdir -p "$APPS"
chmod +x start.sh desktop.py 2>/dev/null || true

cat > "$FILE" <<EOF
[Desktop Entry]
Type=Application
Name=CONSTRUCT
GenericName=Cody
Comment=Cody — Kevins KI-Assistent
Exec=$DIR/start.sh
Path=$DIR
Icon=$DIR/static/icon-256.png
Terminal=false
Categories=Development;Utility;
Keywords=cody;claude;chat;ki;construct;
StartupNotify=true
StartupWMClass=cody
EOF

chmod +x "$FILE"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" || true

echo "» Eingetragen: $FILE"
echo "  CONSTRUCT ist jetzt im Anwendungsmenü — von dort aus anpinnen."
