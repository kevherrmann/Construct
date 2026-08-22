# CONSTRUCT auf dem Mac

## 1. Voraussetzungen prüfen

Im Terminal:

    python3 --version     # muss 3.9+ sein
    claude --version      # das Claude-Code-CLI

Fehlt `python3`, kommt es mit den Xcode-Kommandozeilentools:

    xcode-select --install

Fehlt `claude`:

    curl -fsSL https://claude.ai/install.sh | bash

**Wichtig:** CONSTRUCT hat keinen eigenen Login. Es benutzt die Anmeldung des
`claude`-CLI auf DIESEM Mac (`~/.claude`). Läuft `claude` im Terminal, läuft
auch CONSTRUCT. Es liegen KEINE Zugangsdaten in diesem Ordner.

## 2. Quarantäne entfernen

macOS markiert alles, was aus einem Download oder Messenger kommt, und
verweigert dann die Ausführung ("kann nicht geöffnet werden"). Einmal im
entpackten Ordner ausführen:

    xattr -dr com.apple.quarantine .
    chmod +x start.sh start-mac.command check-desktop.sh

## 3. Starten

    ./start.sh

oder im Finder doppelt auf **start-mac.command** klicken.

Beim ersten Start wird eine Python-Umgebung angelegt und pywebview
installiert — das dauert ein bis zwei Minuten und braucht einmalig Internet.
Danach läuft es offline.

## Was dich auf dem Mac erwartet

- Das Fenster nutzt WKWebView (systemeigen), keine Extra-Pakete nötig.
- Der Matrix-Regen läuft in voller Optik: die Sparmodus-Erkennung greift nur
  bei Wayland+NVIDIA unter Linux.
- Die Chats sind NICHT dieselben wie zu Hause. Sessions liegen pro Rechner in
  `~/.claude/projects`.

## Wenn etwas klemmt

    ./start.sh --web      # nur Server, ohne Fenster -> http://127.0.0.1:8765
    CODY_DEBUG=1 ./start.sh   # Fenster mit Web-Inspector (Rechtsklick)

Läuft Port 8765 schon: `MATRIX_PORT=8766 ./start.sh`

## Was NICHT im Paket ist (mit Absicht)

Zugangsdaten und persönliche Daten sind bewusst draußen: E-Mail-Konten,
API-Schlüssel, Kalender, Teile-Datenbank, Uploads und die Chatverläufe.
E-Mail und die externen KI-Anbieter musst du auf dem Mac neu einrichten,
falls du sie dort brauchst.
