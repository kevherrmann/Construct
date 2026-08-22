# CONSTRUCT — eigene Weboberfläche für Claude Code

**Namen:** Die Oberfläche heißt **CONSTRUCT** (der Ort), der Assistent darin heißt
**Cody** (die Person). Vorher hieß beides „Cody" — das las sich, als wäre die App
der Assistent. Der Ordner heißt aus historischen Gründen weiter `matrix-chat`.

Eine hübsche Matrix-Chat-Oberfläche, die im Hintergrund **Claude Code** (`claude -p`)
ansteuert. Läuft auf deiner **Subscription** (OAuth), **kein API-Key** nötig.

## Was es kann (v1)
- 🟢 Matrix-Design (Code-Regen, grün/schwarz, Scanlines)
- 💬 Streaming-Chat mit Claude (Token für Token)
- 🖼️ Bilder hochladen (einfügen / Drag&Drop / Button) — Claude liest sie
- 🗂️ Alte Claude-Code-Sessions sehen **und darin weiterchatten** (`--resume`)
- 📝 Markdown, Code-Highlighting, klickbare Links
- 🧠 **Weitere Modelle** neben Claude (v3.4): ChatGPT, Gemini, DeepSeek, lokale
  Ollama-Modelle (Gemma & Co.) und jede OpenAI-kompatible API — Einrichtung über
  🧠 → „⚙ KI-Anbieter" (Keys landen in `.llm-config.json`, chmod 600; Logik in
  `llm.py`, Gespräche in `llm_sessions/`). Externe Modelle sind **reine
  Chat-Modelle** (keine Tools/Dateien); beim Modellwechsel mitten im Gespräch
  wird der Verlauf automatisch übernommen — in beide Richtungen.
- 🦙 **Ollama-Verwaltung** direkt im ⚙-Dialog: installierte Modelle mit Größe
  ansehen & löschen, kuratierter Katalog beliebter Modelle zum Direkt-Download
  mit Fortschrittsbalken (läuft server-seitig weiter, auch bei geschlossenem
  Dialog), Freitext-Pull für alles von ollama.com/library. Läuft Ollama gar
  nicht, installiert Cody es per Klick selbst (offizielles Linux-Paket nach
  `/workspace/.ollama`, `ollama serve` als Hintergrundprozess, Auto-Start beim
  App-Start — braucht `zstandard` aus requirements.txt).

- ⚙ **Einstellungen** (v3.8): eine eigene Kachel, in der man einstellt, **welche
  Kacheln man überhaupt sieht** (Chats bleibt fest — eine Oberfläche ohne ihren
  Hauptzweck wäre eine Sackgasse), wie der **Hintergrund** aussieht
  (Matrix-Regen, eigenes Bild oder schlicht dunkel) und wo die **Modelle**
  herkommen. Letzteres bewusst in drei getrennten Blöcken, weil die
  Verwechslung teuer ist: *Claude Code* (Anthropic-Konto, echter Datei- und
  Terminal-Zugriff) — *Chat-Anbieter* (ChatGPT, Gemini, DeepSeek, Ollama; reine
  Gesprächspartner) — *Hermes* (Werkzeuge mit fremden Modellen, vorgeprüft,
  noch nicht angebunden). Gespeichert in `settings.json` (nicht im Git, gehört
  zur Installation) und synchron in die Seite eingesetzt, damit beim Laden
  keine abgeschaltete Kachel aufblitzt.

## Start (Desktop, empfohlen)
```bash
cd matrix-chat
./start.sh                # eigenes Fenster — kein Browser-Tab, kein Docker
./start.sh --web          # nur Server auf http://127.0.0.1:8765
./start.sh --update       # Abhängigkeiten neu installieren
```
Unter **Windows**: Doppelklick auf `start.bat` (gleiche Schalter, `--web` /
`--update`). Gebraucht wird Python von python.org mit „Add Python to PATH".

`start.sh` legt beim ersten Start selbst ein venv an — **pro Plattform und
Python-Version ein eigenes** (`.venv-Linux-x86_64-py3.14`, `.venv-Darwin-arm64-py3.13`),
damit derselbe Ordner von Linux *und* Mac aus laufen kann (USB-Stick). Die
Python-Version gehört in den Namen, weil zwei Rechner mit unterschiedlichem
`python3` sonst denselben Ordner benutzen und ihre Pakete nicht mehr finden.
Läuft auf Port 8765 schon eine Instanz, wird kein zweiter Server gestartet; das
Fenster hängt sich an die laufende.

**In die Taskleiste eintragen (Linux, einmalig):**
```bash
./install-desktop.sh      # ...--remove entfernt es wieder
```

### Fenster-Modus
Das native Fenster macht `pywebview` (`desktop.py`) — WebKitGTK auf Linux,
WKWebView auf dem Mac. Auf **Linux** braucht das einmalig System-Pakete:
```bash
sudo dnf install python3-gobject webkit2gtk4.1     # Fedora / Nobara
sudo apt install python3-gi gir1.2-webkit2-4.1     # Debian / Ubuntu
```
Fehlen sie, öffnet `start.sh` stattdessen den Browser — der Chat funktioniert
davon unabhängig. Auf **macOS** ist nichts extra nötig.

Das Fenster läuft als **eigener Prozess**. GDK beendet den Prozess bei einem
Wayland-Protokollfehler („Error 71") hart von innen — das ist keine Exception
und nur als Kindprozess überhaupt bemerkbar. Stürzt es ab, wird automatisch das
nächste Backend probiert, zuletzt der Browser. Unter Wayland läuft es deshalb
standardmäßig über XWayland.

| Umgebungsvariable | Wirkung |
|---|---|
| `CODY_WAYLAND=1` | natives Wayland zuerst (schärfer bei HiDPI, aber anfälliger) |
| `CODY_GPU=1` | DMA-BUF-Renderer zulassen — flüssiger, kann je nach Treiber schwarz bleiben |
| `CODY_DEBUG=1` | Web-Inspector (Rechtsklick → Element untersuchen) |
| `CODY_GUI=qt` | anderes pywebview-Backend erzwingen |
| `GDK_BACKEND=x11` | überschreibt die Automatik komplett |

Was auf deinem System fehlt oder klemmt, sagt `./check-desktop.sh`.

### Ohne start.sh (Server, Hostinger)
```bash
python3 -m pip install -r requirements.txt        # einmalig
python3 -m uvicorn app:app --host 127.0.0.1 --port 8765
```

Host/Port per Env: `MATRIX_HOST=0.0.0.0 MATRIX_PORT=8765 python3 app.py`

`CODY_WORKSPACE` setzt den Projektordner für die Ordner-Auswahl im Chat. Ohne die
Variable: `/workspace` (Container), sonst `~/projects` bzw. `~/Projekte`, sonst `$HOME`.

## Wenn Claude Code in Docker läuft
Die App läuft **im selben Container** wie `claude` (sie braucht die CLI + `~/.claude`).
Damit du sie vom Browser erreichst, muss der Port aus dem Container gemappt sein:
```bash
docker run ... -p 127.0.0.1:8765:8765 ...   # Host-Port → Container-Port
```
und die App im Container auf `0.0.0.0` binden:
```bash
MATRIX_HOST=0.0.0.0 python3 app.py
```

## Eine abgespeckte Kopie weitergeben
```bash
./make-lite.sh ~/construct-lite "Marco"
tar czf construct-lite.tar.gz -C ~ construct-lite
```
Kopiert wird eine ausdrückliche **Liste** von Dateien, nicht „alles außer X" —
sonst landet jede künftig hinzugefügte Datei automatisch in der Weitergabe, und
irgendwann ist das die mit den Sessions oder Keys. Nicht mitkopiert: alte
Sessions, `.llm-config.json`, `.oauth-token`, `events.json`, Mail-Konten,
`parts.db`, Uploads, Telegram, `mail.py`/`parts.py` und `static/kevin.jpg`.
Das Skript legt eine eigene, neutrale `SOUL.md`/`USER.md` an und schreibt den
Namen des Nutzers in `.lite` — daher heißt er im Chat richtig, ohne dass etwas
umkonfiguriert wird.

Die alten Sessions bleiben übrigens nicht deshalb draußen, weil Lite
`~/.claude/projects` sperren würde — der Ordner gehört auf dem Zielrechner
seinem Besitzer. Sie bleiben draußen, weil sie schlicht nicht mitkopiert werden.

Testen, ohne eine Kopie zu bauen: `CONSTRUCT_LITE=1 ./start.sh --web`.

## ⚠️ Sicherheit
- Gilt für die **Vollversion**; die Lite-Version startet `claude` gar nicht.
- Startet `claude` mit `--permission-mode bypassPermissions` → Claude darf Tools/Befehle
  **ohne Rückfrage** ausführen (volle Power, wie im Terminal). Das ist gewollt für „Jarvis",
  heißt aber: **nur lokal/hinter Login betreiben**, niemals offen ins Internet.
- Für späteres Hostinger-Deployment brauchen wir davor einen **Login** (kommt in einem nächsten Schritt).

## Architektur
```
Browser (Matrix-UI)  ──SSE──►  FastAPI (app.py)  ──►  claude -p  ──►  Subscription
                                       │
                                       └─ liest ~/.claude/projects/*.jsonl (alte Sessions)
```

## Nächste Ausbaustufen (Ideen)
- Chanti als zweites Backend (Umschalter)
- Sessions umbenennen / löschen / suchen
- Login + Hostinger-Deployment
- Eigene Slash-Befehle, Datei-Anhänge (nicht nur Bilder)
