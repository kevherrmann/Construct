#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
#  CONSTRUCT installieren — Linux und macOS
#
#  Zwei Wege, beide gültig:
#
#    1) Repository schon geklont:   ./install.sh
#    2) Nur dieses Skript:          bash install.sh            (klont selbst)
#
#  Was es tut: Python prüfen, ggf. das Repository holen, die Python-Umgebung
#  bauen, einen Starter ins Menü legen und sagen, was als Nächstes zu tun ist.
#
#  Absichtlich ohne sudo. Alles landet im Benutzerkonto; ein Installer, der
#  nach dem Root-Passwort fragt, um einen Chat aufzusetzen, hat sich verlaufen.
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_SSH="git@github.com:kevherrmann/Construct.git"
REPO_HTTPS="https://github.com/kevherrmann/Construct.git"
TARGET_DEFAULT="$HOME/construct"

g(){ printf '\033[0;32m%s\033[0m\n' "$*"; }
y(){ printf '\033[0;33m%s\033[0m\n' "$*"; }
r(){ printf '\033[0;31m%s\033[0m\n' "$*"; }
step(){ printf '\033[0;36m» %s\033[0m\n' "$*"; }

cat <<'BANNER'
 ┌──────────────────────────────────────────────┐
 │   ◢◤  C O N S T R U C T   —  Installation    │
 └──────────────────────────────────────────────┘
BANNER

OS=$(uname -s)
case "$OS" in
  Linux)  PRETTY="Linux" ;;
  Darwin) PRETTY="macOS" ;;
  *)      r "!! $OS wird nicht unterstützt (Linux und macOS)."; exit 1 ;;
esac
g "System: $PRETTY ($(uname -m))"

# ---- 1) Python ----
# Version explizit prüfen: app.py nutzt Syntax, die vor 3.10 nicht existiert
# (X | Y in Typannotationen). Ohne Prüfung scheitert es erst beim Start mit
# einem SyntaxError, der wie ein kaputter Download aussieht.
step "Python prüfen"
PY=""
for c in python3 python; do
  command -v "$c" >/dev/null 2>&1 || continue
  if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  r "!! Kein Python 3.10 oder neuer gefunden."
  case "$OS" in
    Linux)  y "   Fedora/Nobara:  sudo dnf install python3"
            y "   Debian/Ubuntu:  sudo apt install python3 python3-venv" ;;
    Darwin) y "   brew install python     (oder von python.org laden)" ;;
  esac
  exit 1
fi
g "   $($PY --version) — $(command -v $PY)"

# ---- 2) Quellcode ----
# Erkennung am Vorhandensein von app.py UND start.sh: ein einzelnes install.sh
# im Downloads-Ordner ist kein Projektverzeichnis.
if [ -f "app.py" ] && [ -f "start.sh" ]; then
  DIR="$PWD"
  step "Projekt gefunden: $DIR"
  if [ -d .git ] && command -v git >/dev/null 2>&1; then
    git pull --ff-only >/dev/null 2>&1 && g "   auf aktuellen Stand gebracht" \
      || y "   (nicht aktualisiert — lokale Änderungen oder kein Zugriff)"
  fi
else
  command -v git >/dev/null 2>&1 || { r "!! git wird gebraucht, um CONSTRUCT zu holen."; exit 1; }
  printf 'Wohin installieren? [%s] ' "$TARGET_DEFAULT"
  read -r DIR </dev/tty || DIR=""
  DIR="${DIR:-$TARGET_DEFAULT}"
  DIR="${DIR/#\~/$HOME}"
  if [ -d "$DIR/.git" ]; then
    step "Vorhandene Installation aktualisieren"
    git -C "$DIR" pull --ff-only || y "   (nicht aktualisiert)"
  else
    step "CONSTRUCT holen nach $DIR"
    # SSH zuerst: das Repository ist privat, und wer Zugriff hat, hat meist
    # einen Schlüssel hinterlegt. HTTPS als Rückfall fragt nach Zugangsdaten.
    git clone "$REPO_SSH" "$DIR" 2>/dev/null || git clone "$REPO_HTTPS" "$DIR" || {
      r "!! Klonen fehlgeschlagen."
      y "   Das Repository ist privat — du brauchst Zugriff darauf."
      y "   SSH-Schlüssel prüfen mit:  ssh -T git@github.com"
      exit 1; }
  fi
  cd "$DIR"
fi
cd "$DIR"

# ---- 3) Umgebung bauen ----
# start.sh legt das venv selbst an und kennt die Namensregeln (Plattform +
# Python-Version). Das hier nachzubauen hiesse, zwei Wahrheiten zu pflegen.
step "Python-Umgebung und Abhängigkeiten"
chmod +x start.sh 2>/dev/null || true
if ! ./start.sh --update --setup-only 2>/dev/null; then
  PYVER=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  VENV=".venv-$OS-$(uname -m)-py$PYVER"
  [ -d "$VENV" ] || {
    if [ "$OS" = "Linux" ]; then "$PY" -m venv --system-site-packages "$VENV"
    else "$PY" -m venv "$VENV"; fi
  }
  "$VENV/bin/python" -m pip install -q --upgrade pip
  "$VENV/bin/python" -m pip install -q -r requirements.txt
  "$VENV/bin/python" -m pip install -q -r requirements-desktop.txt 2>/dev/null \
    || y "   (pywebview nicht installierbar — es öffnet sich dann der Browser)"
fi
g "   fertig"

# ---- 4) Starter ins Menü ----
step "Starter anlegen"
if [ "$OS" = "Linux" ] && [ -f install-desktop.sh ]; then
  chmod +x install-desktop.sh
  ./install-desktop.sh >/dev/null 2>&1 && g "   Eintrag im Anwendungsmenü angelegt" \
    || y "   (Menüeintrag übersprungen)"
else
  chmod +x start-mac.command 2>/dev/null || true
  if [ "$OS" = "Darwin" ] && [ -f start-mac.command ] && [ -d "$HOME/Desktop" ]; then
    ln -sf "$DIR/start-mac.command" "$HOME/Desktop/CONSTRUCT.command" 2>/dev/null \
      && g "   Verknüpfung auf dem Schreibtisch" || true
  fi
fi

# ---- 5) Fenster-Modus: nur melden, nicht heimlich nachinstallieren ----
if [ "$OS" = "Linux" ]; then
  VP=$(ls -d .venv-*/bin/python 2>/dev/null | head -1)
  if [ -n "$VP" ] && ! "$VP" -c "import gi; gi.require_version('WebKit2','4.1')" >/dev/null 2>&1; then
    echo
    y "Hinweis: Für ein eigenes Fenster fehlt WebKitGTK (sonst öffnet sich der Browser):"
    y "   Fedora/Nobara:   sudo dnf install python3-gobject webkit2gtk4.1"
    y "   Debian/Ubuntu:   sudo apt install python3-gi gir1.2-webkit2-4.1"
  fi
fi

cat <<FERTIG

$(g "✓ CONSTRUCT ist installiert in $DIR")

  Starten:      cd "$DIR" && ./start.sh
  Nur Server:   ./start.sh --web      → http://127.0.0.1:8765

  Danach in der Oberfläche unter ⚙ Einstellungen:
    · Kacheln aussuchen, Farbwelt und Hintergrund wählen
    · unter "Modelle & Anbieter" festlegen, womit du redest

  Ohne weitere Einrichtung kann CONSTRUCT noch nichts — es braucht
  entweder Claude Code (Anthropic-Konto, voller Zugriff) oder den
  API-Schlüssel eines Chat-Anbieters. Beides steht dort erklärt.
FERTIG
