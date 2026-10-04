#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
#  CONSTRUCT starten — nativ, ohne Docker.
#
#    ./start.sh            Server + eigenes Fenster (im Browser, Taskleiste)
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
  "$PY" -m venv "$VENV"
  UPDATE=1
fi

VPY="$VENV/bin/python"
[ -x "$VPY" ] || { echo "!! $VENV ist kaputt. Löschen und neu starten:  rm -rf $VENV && ./start.sh"; exit 1; }

# ---- Abhängigkeiten (nur bei Änderung) ----
STAMP="$VENV/.deps-stamp"
NOW=$(cat requirements.txt 2>/dev/null | cksum | tr -d ' ')
if [ "$UPDATE" = "1" ] || [ "$(cat "$STAMP" 2>/dev/null || true)" != "$NOW" ]; then
  echo "» installiere Abhängigkeiten … (dauert beim ersten Mal ein, zwei Minuten)"
  "$VPY" -m pip install -q --upgrade pip
  "$VPY" -m pip install -q -r requirements.txt
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

# ${ARGS[@]+...} statt "${ARGS[@]}": macOS liefert bash 3.2, wo ein leeres Array
# unter `set -u` sonst ein leeres Argument durchreicht.
exec "$VPY" desktop.py ${ARGS[@]+"${ARGS[@]}"}
