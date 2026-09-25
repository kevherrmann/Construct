#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
#  CONSTRUCT starten — nativ, ohne Docker.
#
#    ./start.sh            eigenes Fenster (Taskleiste)
#    ./start.sh --web      nur Server auf http://127.0.0.1:8765
#    ./start.sh --update   Abhängigkeiten neu installieren
#    ./start.sh --setup-only  nur einrichten, nicht starten
#
#  Legt beim ersten Start ein venv an — pro Plattform ein eigenes
#  (.venv-Linux-x86_64 / .venv-Darwin-arm64), damit derselbe Ordner
#  von Linux UND Mac aus laufen kann (USB-Stick).
# ──────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

OS=$(uname -s)
PY=$(command -v python3 || true)
[ -n "$PY" ] || { echo "!! python3 nicht gefunden. Linux: sudo dnf install python3   Mac: brew install python"; exit 1; }

# Python-Version MUSS in den venv-Namen: sonst greifen zwei Rechner mit
# unterschiedlichem python3 (3.14 hier, 3.11 dort) auf denselben Ordner zu, und
# der Interpreter findet seine Pakete nicht — genau das Szenario beim USB-Stick.
PYVER=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
VENV=".venv-$OS-$(uname -m)-py$PYVER"

UPDATE=0
WEB=0
SETUP_ONLY=0
ARGS=()
for a in "$@"; do
  case "$a" in
    --update) UPDATE=1 ;;
    # Nur einrichten, nicht starten — dafuer ruft install.sh das hier auf.
    # Ohne den Schalter wuerde die Installation am Ende ein Fenster oeffnen.
    --setup-only) SETUP_ONLY=1; UPDATE=1 ;;
    --web) WEB=1; ARGS+=("$a") ;;
    *) ARGS+=("$a") ;;
  esac
done

# ---- CONSTRUCT selbst aktualisieren (git, nur Fast-Forward) ----
# Vor dem venv: bringt das Update eine neue requirements.txt mit, wird sie
# unten gleich installiert. Exit 10 = aktualisiert -> einmal neu starten, weil
# auch dieses Skript zu den neuen Dateien gehören kann.
if [ "$SETUP_ONLY" = "0" ] && [ -z "${CONSTRUCT_UPDATED:-}" ]; then
  RC=0; "$PY" selfupdate.py || RC=$?
  if [ "$RC" = "10" ]; then
    export CONSTRUCT_UPDATED=1
    exec ./start.sh "$@"
  fi
fi

# ---- venv anlegen ----
if [ ! -d "$VENV" ]; then
  echo "» lege Python-Umgebung an ($VENV) …"
  if [ "$OS" = "Linux" ]; then
    # --system-site-packages: das WebKitGTK-Binding (python3-gobject) kommt aus
    # der Distribution und lässt sich nicht sinnvoll ins venv pippen.
    "$PY" -m venv --system-site-packages "$VENV"
  else
    "$PY" -m venv "$VENV"
  fi
  UPDATE=1
fi

VPY="$VENV/bin/python"
[ -x "$VPY" ] || { echo "!! $VENV ist kaputt. Löschen und neu starten:  rm -rf $VENV && ./start.sh"; exit 1; }

# ---- Abhängigkeiten (nur bei Änderung) ----
STAMP="$VENV/.deps-stamp"
NOW=$(cat requirements.txt requirements-desktop.txt 2>/dev/null | cksum | tr -d ' ')
if [ "$UPDATE" = "1" ] || [ "$(cat "$STAMP" 2>/dev/null || true)" != "$NOW" ]; then
  echo "» installiere Abhängigkeiten … (dauert beim ersten Mal ein, zwei Minuten)"
  "$VPY" -m pip install -q --upgrade pip
  "$VPY" -m pip install -q -r requirements.txt
  # Fenster-Modus ist Kür: schlägt das fehl, läuft CONSTRUCT trotzdem im Browser.
  "$VPY" -m pip install -q -r requirements-desktop.txt \
    || echo "   ⚠  pywebview ließ sich nicht installieren — Fenster-Modus fällt auf den Browser zurück."
  echo "$NOW" > "$STAMP"
fi

if [ "$SETUP_ONLY" = "1" ]; then
  echo "» Umgebung steht ($VENV)."
  exit 0
fi

# ---- Vorbedingungen prüfen ----
# Kein harter Fehler: ohne claude-CLI laeuft der Chat ueber die Anbieter aus
# dem Modell-Menue weiter, nur ohne Datei- und Terminal-Zugriff. Die Oberflaeche
# sagt das auch selbst (Schluessel-Chip oben rechts).
command -v claude >/dev/null 2>&1 \
  || echo "ℹ  Das 'claude'-CLI ist nicht im PATH — Dateien und Terminal stehen dann nicht zur Verfügung."

if [ "$OS" = "Linux" ] && [ "$WEB" = "0" ]; then
  # Nicht nur "import gi" prüfen: gi allein ist da, sobald python3-gobject liegt —
  # entscheidend ist das WebKit-Typelib. Fehlt das, fällt pywebview sonst auf Qt
  # zurück und meldet "kein Modul qtpy", was in die falsche Richtung zeigt.
  "$VPY" -c "import gi; gi.require_version('WebKit2','4.1')" >/dev/null 2>&1 || cat <<'EOF'
⚠  Für das eigene Fenster fehlt WebKitGTK:
     Fedora/Nobara:   sudo dnf install python3-gobject webkit2gtk4.1
     Debian/Ubuntu:   sudo apt install python3-gi gir1.2-webkit2-4.1
   Danach reicht ein normales ./start.sh (kein venv-Neubau nötig).
   Details:  ./scripts/linux/check-desktop.sh     — bis dahin öffnet sich der Browser.
EOF
fi

# ${ARGS[@]+...} statt "${ARGS[@]}": macOS liefert bash 3.2, wo ein leeres Array
# unter `set -u` sonst ein leeres Argument durchreicht.
exec "$VPY" desktop.py ${ARGS[@]+"${ARGS[@]}"}
