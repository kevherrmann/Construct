#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
#  Startet Cody-über-Telegram als eigenen Container.
#  Nutzt dasselbe Image + claude-config-Volume wie matrixchat.
#  Installiert faster-whisper (Sprache->Text) beim ersten Start.
# ──────────────────────────────────────────────────────────────
set -e

echo "» räume alten Bot weg …"
docker rm -f cody-telegram >/dev/null 2>&1 || true

# Bot-Token und eigene Chat-ID: entweder vorher exportieren oder hier aus einer
# .env ziehen. Die Chat-ID verrät dir @userinfobot in Telegram.
#   export TELEGRAM_TOKEN=123456:AA…   export CODY_CHAT_ID=123456789
ENV_FILE="${CODY_ENV_FILE:-$HOME/.cody-env}"
if [ -z "$TELEGRAM_TOKEN" ] && [ -f "$ENV_FILE" ]; then
  TELEGRAM_TOKEN=$(grep -m1 '^TELEGRAM_TOKEN=' "$ENV_FILE" | cut -d= -f2-)
  CODY_CHAT_ID=${CODY_CHAT_ID:-$(grep -m1 '^CODY_CHAT_ID=' "$ENV_FILE" | cut -d= -f2-)}
fi
if [ -z "$TELEGRAM_TOKEN" ]; then echo "⚠ Kein TELEGRAM_TOKEN (Env oder $ENV_FILE)"; exit 1; fi
if [ -z "$CODY_CHAT_ID" ]; then echo "⚠ Keine CODY_CHAT_ID — der Bot würde niemandem antworten"; exit 1; fi

echo "» starte Cody-Telegram …"
# ACHTUNG: Läuft der Bot schon dauerhaft auf einem Server, darf er nicht
# gleichzeitig lokal laufen — zwei Instanzen am selben Token klauen sich die
# Nachrichten. Lokal startet er nur mit CODY_FORCE_LOCAL_BOT=1 ./telegram.sh,
# und den auf dem Server vorher stoppen.
docker run -d --name cody-telegram \
  -e CODY_BOT_OK="${CODY_FORCE_LOCAL_BOT:-0}" \
  -e TELEGRAM_TOKEN="$TELEGRAM_TOKEN" \
  -e CODY_CHAT_ID="$CODY_CHAT_ID" \
  -e CODY_WHISPER_MODEL=small \
  -v "${CODY_WORKSPACE:-$HOME/projects}":/workspace \
  -v claude-config:/home/dev \
  -w /workspace/matrix-chat \
  --entrypoint bash \
  claude-code \
  -lc "(python3 -c 'import faster_whisper' 2>/dev/null || python3 -m pip install --user --break-system-packages -q faster-whisper) & exec python3 telegram_bot.py"

echo "🤖 Cody-Telegram gestartet — Text-Chat geht sofort."
echo "   (faster-whisper für Sprache lädt im Hintergrund nach.)"
echo "   Logs:    docker logs -f cody-telegram"
echo "   Stoppen: docker rm -f cody-telegram"
sleep 3
echo "» Status:"; docker ps --filter name=cody-telegram --format '   {{.Names}}: {{.Status}}'
echo "» erste Log-Zeilen:"; docker logs cody-telegram 2>&1 | tail -8
