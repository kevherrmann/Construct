#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
#  Startet Cody-über-Telegram als eigenen Container.
#  Nutzt dasselbe Image + claude-config-Volume wie matrixchat.
#  Installiert faster-whisper (Sprache->Text) beim ersten Start.
# ──────────────────────────────────────────────────────────────
set -e

echo "» räume alten Bot weg …"
docker rm -f cody-telegram >/dev/null 2>&1 || true

TOKEN=$(grep '^TELEGRAM_TOKEN=' /home/z0mb1/projects/CrazyFamily/.env | cut -d= -f2)
if [ -z "$TOKEN" ]; then echo "⚠ Kein TELEGRAM_TOKEN in CrazyFamily/.env gefunden"; exit 1; fi

echo "» starte Cody-Telegram …"
# ACHTUNG: Der Bot läuft normal 24/7 auf Hostinger. Lokal startet er nur mit
# CODY_FORCE_LOCAL_BOT=1 ./telegram.sh — und vorher auf dem Server stoppen:
#   ssh root@76.13.140.227 'systemctl stop cody-telegram'
docker run -d --name cody-telegram \
  -e CODY_BOT_OK="${CODY_FORCE_LOCAL_BOT:-0}" \
  -e TELEGRAM_TOKEN="$TOKEN" \
  -e CODY_CHAT_ID=6515451491 \
  -e CODY_WHISPER_MODEL=small \
  -v /home/z0mb1/projects:/workspace \
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
