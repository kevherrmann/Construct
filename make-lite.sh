#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
#  CONSTRUCT Lite herausgeben
#
#    ./make-lite.sh ~/construct-lite "Name"
#
#  Baut aus diesem Ordner eine weitergebbare Kopie: alles wie hier, aber
#  ohne Skills/MCP/E-Mail — und vor allem OHNE Daten.
#
#  Der Empfaenger braucht ein eigenes Anthropic-Konto und Claude Code; die
#  Kopie bringt keine Anmeldung mit (.oauth-token wird nicht kopiert).
#
#  Kopiert wird eine ausdrückliche LISTE von Dateien, keine Ausschluss-Regel.
#  Das ist Absicht: bei "alles außer X" landet jede neue Datei automatisch in
#  der Kopie, und irgendwann ist das eine mit Sitzungen, Keys oder Postfach.
#  Hier muss man das Weitergeben jeder Datei einmal hinschreiben.
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"
SRC="$PWD"

ZIEL="${1:-}"
NAME="${2:-}"
if [ -z "$ZIEL" ]; then
  echo "Aufruf:  ./make-lite.sh <zielordner> [Name des Nutzers]"
  echo "Beispiel: ./make-lite.sh ~/construct-lite \"Marco\""
  exit 1
fi

mkdir -p "$ZIEL"
ZIEL="$(cd "$ZIEL" && pwd)"
[ "$ZIEL" != "$SRC" ] || { echo "!! Ziel ist der Quellordner selbst."; exit 1; }
if [ -n "$(ls -A "$ZIEL" 2>/dev/null)" ]; then
  echo "!! $ZIEL ist nicht leer."
  read -r -p "   Dateien darin überschreiben? [j/N] " a
  [ "$a" = "j" ] || [ "$a" = "J" ] || exit 1
fi

# ---- Programmcode ----
# mail.py fehlt mit Absicht: app.py importiert es in Lite nicht.
CODE=(app.py llm.py cal.py config.py desktop.py
      start.sh start.bat start-mac.command check-desktop.sh install-desktop.sh
      requirements.txt requirements-desktop.txt)
for f in "${CODE[@]}"; do
  [ -f "$f" ] && cp -p "$f" "$ZIEL/" || echo "   (übersprungen: $f fehlt)"
done

# ---- Oberfläche ----
# kevin.jpg ist ein Foto und bleibt hier; in Lite zeigt der Chat stattdessen
# den Anfangsbuchstaben (siehe .av-kevin in der lite-CSS).
mkdir -p "$ZIEL/static"
cp -p static/index.html "$ZIEL/static/"
[ -f static/icon-256.png ] && cp -p static/icon-256.png "$ZIEL/static/"
[ -f static/cody.png ] && cp -p static/cody.png "$ZIEL/static/"

# ---- Schalter: DIESE Datei macht die Kopie zur Lite-Version ----
printf '%s\n' "$NAME" > "$ZIEL/.lite"

# ---- Persona ----
# Wird bei jeder Anfrage frisch gelesen und dem Modell vorangestellt (app.py:
# load_persona). Bewusst kurz — der Nutzer soll es selbst umschreiben können.
ANREDE="${NAME:-dem Nutzer}"
DU="${NAME:-du}"
cat > "$ZIEL/SOUL.md" <<EOF
# SOUL.md — Wer ich bin

Mein Name ist **Cody**. Ich bin ${ANREDE}s persönlicher KI-Assistent.
Die Oberfläche, in der wir uns treffen, heißt **CONSTRUCT** — Cody bin ich, nicht die App.

## Charakter
- **Direkt & ehrlich.** Ich sage klar, was Sache ist — auch wenn's mal „das geht nicht" heißt.
- **Locker, mit etwas Humor**, aber nie albern, wenn echte Arbeit ansteht.
- **Ich denke mit.** Sehe ich ein Problem oder eine bessere Idee, spreche ich es an.
- **Pragmatisch.** Lieber eine klare Empfehlung als eine Liste von zehn Optionen.
- Ich rede **Deutsch**, locker und per „du".

## Was ich kann — und was nicht
Das hängt am gewählten Modell, und ich behaupte nie mehr, als gerade stimmt.
Läuft das Gespräch über einen externen Anbieter (ChatGPT, Gemini …), bin
ich ein **reines Chat-Modell**: keine Dateien, kein Terminal, keine Programme.
Läuft es über Claude Code, habe ich Zugriff auf Dateien und Terminal im
gewählten Arbeitsordner. Was ich nicht kann, sage ich, statt es zu erfinden.

Termine stehen unter **📅 Kalender** — die trägt ${DU} selbst ein; ich sehe die
anstehenden und erinnere von mir aus daran, wenn es passt.
EOF

cat > "$ZIEL/USER.md" <<EOF
# USER.md — Über ${NAME:-den Nutzer}

Hier steht Dauerhaftes${NAME:+ über $NAME}: Vorlieben, Projekte, Menschen.
Cody liest die Datei bei jeder Nachricht mit.

## Basis
${NAME:+- Name: **$NAME**
}- Sprache: Deutsch, locker, per „du"

<!-- Einfach ergänzen — die Datei ist normaler Text. -->
EOF

# ---- Anleitung ----
cat > "$ZIEL/README.md" <<'EOF'
# CONSTRUCT

Eine Oberfläche im Matrix-Look für **Claude Code** — Chat, Dateien, Terminal
und Kalender in einem Fenster.

**Was du brauchst:** ein **Anthropic-Konto** (Abo oder API-Guthaben) und
**Claude Code**. Ohne das kann CONSTRUCT nur reden, nicht arbeiten — und zum
reinen Reden braucht es keine App, das geht im Browser genauso. Die Einrichtung
steht unten unter „Claude Code einrichten".

Andere Anbieter (ChatGPT, Gemini, DeepSeek, jede OpenAI-kompatible API, lokal
Ollama) lassen sich zusätzlich hinterlegen, aber die sind **reine Chat-Modelle**
ohne Zugriff auf Dateien oder Terminal. Solange Claude Code fehlt, sind die
Knöpfe 📂 Ordner und 🛡 Modus ausgegraut: sie sind da, wirken aber auf nichts.

## Was drin ist
- 💬 **Chat** mit Streaming, Markdown, Code-Highlighting, Bild-Upload
- 📅 **Kalender** — Termine eintragen, ansehen, löschen
- 🧠 **Modellwechsel mitten im Gespräch** — der Verlauf wandert mit
- 📂 **Arbeitsordner** und 🛡 **Berechtigungs-Modus** — für den Claude-Betrieb

## Start — Windows
Doppelklick auf **`start.bat`**. Beim ersten Mal legt es eine Python-Umgebung
an (dauert ein, zwei Minuten). Gebraucht wird nur Python von **python.org** —
beim Installieren *„Add Python to PATH"* ankreuzen, sonst findet `start.bat`
es nicht.

Nur den Server, ohne eigenes Fenster: `start.bat --web`

## Start — Linux / Mac
```bash
./start.sh          # eigenes Fenster
./start.sh --web    # nur Server auf http://127.0.0.1:8765
```
Auf **Linux** braucht das eigene Fenster einmalig Systempakete — sonst öffnet
sich einfach der Browser, der Chat funktioniert genauso:
```bash
sudo dnf install python3-gobject webkit2gtk4.1     # Fedora / Nobara
sudo apt install python3-gi gir1.2-webkit2-4.1     # Debian / Ubuntu
```
In die Taskleiste eintragen: `./install-desktop.sh`

## Claude Code einrichten (einmalig)
Das ist der Schritt, der die App erst nützlich macht.

1. **Node.js** installieren (nodejs.org).
2. Terminal öffnen (Windows: PowerShell) und eingeben:
   `npm install -g @anthropic-ai/claude-code`
3. **Anmelden:** im Terminal `claude` eingeben und dem Login folgen. Das
   braucht ein Anthropic-Konto (Abo oder API-Guthaben).
   Unter Windows geht das *nur* so — der Login-Knopf in der Oberfläche braucht
   ein Pseudo-Terminal, das es dort nicht gibt. Unter Linux/Mac kann man
   stattdessen den 🔑-Chip oben rechts anklicken.
4. CONSTRUCT starten. Der 🔑-Chip zeigt jetzt **OK**, im 🧠-Menü stehen die
   Claude-Modelle, und 📂 Ordner sowie 🛡 Modus greifen.

## Andere Anbieter (optional, nur Chat)
Unter **🧠 → „⚙ KI-Anbieter"** lässt sich ein API-Key für ChatGPT, Gemini,
DeepSeek oder eine beliebige OpenAI-kompatible API hinterlegen; lokale Modelle
über Ollama gehen ohne Key. Keys liegen nur lokal in `.llm-config.json` (nur
für dich lesbar) und tauchen nie im Browser auf.

## Wer ist „Cody"?
Die Persona des Assistenten steht in `SOUL.md`, was er über dich weiß in
`USER.md`. Beides sind normale Textdateien — umschreiben, umbenennen, ergänzen:
was drinsteht, liest er bei jeder Nachricht mit.

## Gut zu wissen
Die externen Modelle sind **reine Chat-Modelle**. Sie können keine Dateien
lesen, keine Programme starten und nichts im Kalender eintragen — Termine
trägst du selbst unter 📅 ein. Wenn ein Modell etwas anderes behauptet, irrt es
sich. Nur über Claude Code gibt es echten Datei- und Terminal-Zugriff.

Der 🔑-Chip oben rechts zeigt „OHNE CLAUDE", solange Claude Code nicht
installiert ist. Das ist kein Fehler, nur ein Hinweis — ein Klick darauf zeigt
die Anleitung.

## Ins Internet stellen?
Nur mit Passwort davor:
```bash
MATRIX_USER=name MATRIX_PASS=geheim ./start.sh --web
```
EOF

# Termine der Kopie: leer starten (kein Kalender-Import aus dem Quellordner)
echo "[]" > "$ZIEL/events.json"
chmod +x "$ZIEL"/*.sh "$ZIEL/start-mac.command" 2>/dev/null || true
# start.bat mit CRLF: cmd.exe verschluckt bei reinen LF je nach Windows-Version
# Labels und goto-Sprünge. Beim Kopieren über Linux geht das sonst verloren.
[ -f "$ZIEL/start.bat" ] && python3 -c "
import sys,pathlib
p=pathlib.Path(sys.argv[1]); b=p.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
p.write_bytes(b)" "$ZIEL/start.bat"

echo
echo "✅ CONSTRUCT (abgespeckt) liegt in: $ZIEL"
echo "   Nutzer: ${NAME:-(kein Name gesetzt — steht in .lite)}"
echo
echo "   Nicht mitkopiert: Sessions, API-Keys, Termine, E-Mail-Konten,"
echo "   Uploads, Telegram, mail.py, kevin.jpg,"
echo "   .oauth-token (die Claude-Anmeldung)."
echo
echo "   Weitergeben:  tar czf construct-lite.tar.gz -C $(dirname "$ZIEL") $(basename "$ZIEL")"
