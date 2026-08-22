#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
#  Startet ALLES für Cody mit EINEM Befehl:
#   1) die Matrix-Weboberfläche  -> http://127.0.0.1:8765
#   2) den Telegram-Bot (@chantihermes_bot)
#  Killt jeweils alte Container und startet frisch.
# ──────────────────────────────────────────────────────────────
set -e

# Serialisiere parallele Starts (Desktop-Autostart beim Login + udev-Hotplug-Trigger),
# damit sich nicht zwei Läufe beim "docker rm -f / docker run" in die Quere kommen.
exec 9>/tmp/matrixchat.lock 2>/dev/null || true
flock -w 60 9 2>/dev/null || true

PROJECTS=/home/z0mb1/projects

# ---- n8n sicherstellen (eigenes Netz + Container) ----
# n8n läuft dauerhaft mit --restart unless-stopped und startet nach Reboot von
# selbst. Dieser Block garantiert nur: Netz vorhanden + Container läuft, damit
# Cody im matrixchat-Container n8n unter http://n8n:5678 erreicht.
docker network create cody-net >/dev/null 2>&1 || true
if [ -z "$(docker ps -q -f name='^n8n$')" ]; then
  if [ -n "$(docker ps -aq -f name='^n8n$')" ]; then
    echo "» starte vorhandenen n8n-Container …"; docker start n8n >/dev/null 2>&1 || true
  else
    echo "» erstelle n8n-Container …"
    docker volume create n8n-data >/dev/null 2>&1 || true
    docker run -d --name n8n \
      --restart unless-stopped \
      --network cody-net \
      -p 127.0.0.1:5678:5678 \
      -v n8n-data:/home/node/.n8n \
      -e GENERIC_TIMEZONE=Europe/Berlin -e TZ=Europe/Berlin \
      -e N8N_SECURE_COOKIE=false -e N8N_RUNNERS_ENABLED=true \
      docker.n8n.io/n8nio/n8n:latest >/dev/null 2>&1 || true
  fi
fi

echo "» räume alte Container weg …"
docker rm -f matrixchat cody-telegram >/dev/null 2>&1 || true
for c in $(docker ps -q --filter "publish=8765"); do
  echo "  stoppe alten Container $c (Port 8765)"; docker rm -f "$c" >/dev/null 2>&1 || true
done

# ---- Serielle Geräte durchreichen (ESP32 / Arduino / Otto — nur wenn angesteckt) ----
# Reicht ALLE gefundenen seriellen Ports durch (CH340/CP210x = ttyUSB*, echter
# Arduino = ttyACM*), jeweils per --device, plus ihre Gerätegruppe (Schreibrechte)
# per --group-add. Auf diesem System gehört ttyUSB0 z.B. der Gruppe 'nfsnobody',
# nicht 'dialout' – deshalb wird die gid pro Gerät dynamisch aus stat gelesen.
# Zusätzlich landet die Portliste als Env SERIAL_PORTS im Container, damit Cody
# im Chat sofort weiß, welche seriellen Geräte verfügbar sind (z.B. der ESP32).
SERIAL_ARGS=()
SERIAL_PORTS=""
declare -A _seen_gid
for dev in /dev/ttyUSB* /dev/ttyACM*; do
  [ -e "$dev" ] || continue
  SERIAL_ARGS+=(--device="$dev")
  gid=$(stat -c '%g' "$dev" 2>/dev/null || echo 18)
  if [ -z "${_seen_gid[$gid]:-}" ]; then
    SERIAL_ARGS+=(--group-add "$gid")
    _seen_gid[$gid]=1
  fi
  SERIAL_PORTS="${SERIAL_PORTS:+$SERIAL_PORTS,}$dev"
  echo "» 🔌 reiche seriellen Port durch: $dev (gid=$gid)"
done
if [ -n "$SERIAL_PORTS" ]; then
  SERIAL_ARGS+=(-e "SERIAL_PORTS=$SERIAL_PORTS")
  echo "» 🔌 SERIAL_PORTS=$SERIAL_PORTS (im Chat verfügbar)"
else
  echo "» ⚠  kein serieller Port gefunden – ESP32/Otto nicht angesteckt? (starte ohne Device)"
fi

# ---- 1) Web-Oberfläche ----
echo "» starte matrixchat (Web) …"
docker run -d --name matrixchat \
  -p 127.0.0.1:8765:8765 \
  -v "$PROJECTS":/workspace \
  -v claude-config:/home/dev \
  -w /workspace/matrix-chat \
  "${SERIAL_ARGS[@]}" \
  --entrypoint bash \
  claude-code \
  -lc "python3 -c 'import fastapi,uvicorn,multipart' 2>/dev/null || \
       python3 -m pip install --user --break-system-packages -q fastapi 'uvicorn[standard]' python-multipart; \
       python3 -c 'import serial' 2>/dev/null || \
       python3 -m pip install --user --break-system-packages -q pyserial; \
       exec python3 -m uvicorn app:app --host 0.0.0.0 --port 8765"

# matrixchat zusätzlich ans cody-net hängen, damit Cody n8n per Name (http://n8n:5678) erreicht
docker network connect cody-net matrixchat >/dev/null 2>&1 || true

# ---- 2) Telegram-Bot ----
# HINWEIS: Der Telegram-Bot läuft jetzt 24/7 auf Hostinger (systemd: cody-telegram).
# Lokal NICHT mehr starten – sonst kämpfen zwei Instanzen um denselben Bot-Token
# (Telegram-Fehler 409 Conflict). Falls doch mal lokal getestet: vorher den
# Server-Dienst stoppen (ssh root@… 'systemctl stop cody-telegram').
echo "» Telegram-Bot: läuft auf Hostinger (hier lokal bewusst übersprungen)."
docker rm -f cody-telegram >/dev/null 2>&1 || true

# ---- Status ----
echo "» warte auf Web-Start …"
for i in $(seq 1 15); do
  V=$(curl -s --max-time 2 http://127.0.0.1:8765/api/version 2>/dev/null || true)
  if [ -n "$V" ]; then echo "🟢 Web:  http://127.0.0.1:8765   →   $V"; break; fi
  sleep 1
done
sleep 2
echo "🤖 Bot: $(docker ps --filter name=cody-telegram --format '{{.Status}}' || echo 'nicht gestartet')"
echo
echo "Logs:    docker logs -f matrixchat   |   docker logs -f cody-telegram"
echo "Stoppen: docker rm -f matrixchat cody-telegram"
