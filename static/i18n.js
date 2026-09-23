/* ──────────────────────────────────────────────────────────────
   CONSTRUCT — Zweisprachigkeit (Deutsch / Englisch)

   Deutsch ist der Quelltext: index.html und das Backend schreiben ihre Texte
   weiter auf Deutsch. Steht die Sprache auf "en", tauscht dieses Script sie
   beim Zeichnen aus — per MutationObserver, also auch alles, was später per
   innerHTML/textContent entsteht. Das erspart es, 3000 Zeilen Oberfläche mit
   T()-Aufrufen zu durchziehen.

   Drei Stufen, in dieser Reihenfolge:
     EN    exakte Texte (Textknoten, title/placeholder, alert/confirm)
     HTML  ganze Absätze mit <b>/<code> darin — Schlüssel ist der Klartext
           des Elements, Wert das englische HTML (Satzbau passt nicht Stück
           für Stück)
     RX    Texte mit eingesetzten Werten ("zuletzt vor 5 min geprüft")
   Was dann noch übrig ist, wird bruchstückweise ersetzt (Satzteile, die per
   '+' zusammengesetzt wurden — nur mehrwortige Schlüssel, damit einzelne
   Wörter in Nutzerinhalten nicht umgeschrieben werden).

   Nie angefasst: Chat-Inhalte, Code, Eingabefelder, Mail-Inhalte — siehe SKIP.

   Neuer Text in der Oberfläche? Deutsch schreiben wie gewohnt, hier den
   englischen Eintrag ergänzen. Fehlt er, bleibt der Text einfach deutsch.
   ────────────────────────────────────────────────────────────── */
(function(){
'use strict';
var C = window.CONSTRUCT || {};
var LANG = C.lang || (C.settings && C.settings.lang) || 'en';
if (LANG !== 'de') LANG = 'en';
document.documentElement.lang = LANG;

var EN = {
  // ---- Grundgerüst / Menü ----
  "Chats": "Chats", "Skills": "Skills", "Kalender": "Calendar", "E-Mails": "E-mails",
  "Einstellungen": "Settings", "Du": "You", "DU": "YOU",
  "＋ NEUE SESSION": "＋ NEW SESSION", "🔎 Sessions durchsuchen…": "🔎 Search sessions…",
  "Skills aus deinen Projekten — anklicken zum Ansehen": "Skills from your projects — click to view",
  "Was du siehst und womit du redest — rechts einstellen": "What you see and who you talk to — configure on the right",
  "Konnektoren / MCP-Server — worauf Cody zugreifen kann": "Connectors / MCP servers — what Cody can access",
  "VERBUNDEN": "CONNECTED", "build ALT/unbekannt": "build OLD/unknown",
  "Modell, mit dem in dieser Session zuletzt wirklich geantwortet wurde": "Model that actually answered last in this session",
  "Auslastung des 5-Stunden-Fensters": "Usage of the 5-hour window",
  "Auslastung der Woche": "Weekly usage", "Claude-Anmeldung": "Claude sign-in",
  "7T …": "7d …", "7T": "7d",
  "📅 Kalender": "📅 Calendar", "📧 E-Mails": "📧 E-mails", "⚡ Skills": "⚡ Skills", "🔌 MCP": "🔌 MCP",
  "Cody stoppen": "Stop Cody", "Bild anhängen": "Attach image", "SENDEN": "SEND",
  "> Nachricht eingeben... (Bilder: einfügen / ziehen / ⧉)": "> Type a message... (images: paste / drop / ⧉)",
  "ENTER = senden · SHIFT+ENTER = neue Zeile · 📂 Ordner · 🛡 Mode · 🧠 Modell ·": "ENTER = send · SHIFT+ENTER = new line · 📂 Folder · 🛡 Mode · 🧠 Model ·",
  "= Befehle": "= commands",
  "Modell": "Model", "Modelle": "Models", "Mode": "Mode",
  "⌬ BILD HIER ABLEGEN ⌬": "⌬ DROP IMAGE HERE ⌬",
  "WERKZEUGE PRÜFEN": "CHECKING TOOLS", "ausblenden": "hide", "schließen": "close",
  "Arbeitsordner": "Working folder", "Berechtigungs-Modus": "Permission mode",
  " — wirkt nur mit Claude Code. Die Chat-Modelle (ChatGPT, Gemini …) haben keinen Zugriff auf Dateien.": " — only works with Claude Code. The chat models (ChatGPT, Gemini …) have no file access.",

  // ---- Login ----
  "🔑 CLAUDE LOGIN": "🔑 CLAUDE LOGIN",
  "Meldet Cody bei deiner Claude-Subscription an — direkt hier, ohne Terminal. Es wird ein langlebiger Token erzeugt, der auch nach Ablauf des normalen Logins weiter funktioniert.": "Signs Cody in to your Claude subscription — right here, no terminal needed. This creates a long-lived token that keeps working after the normal login expires.",
  "LOGIN STARTEN": "START LOGIN",
  "Diesen Link öffnen und mit deinem Claude-Konto anmelden:": "Open this link and sign in with your Claude account:",
  "Den Code, den dir die Seite zeigt, hier einfügen:": "Paste the code the page shows you here:",
  "Code hier einfügen": "Paste code here", "CODE BESTÄTIGEN": "CONFIRM CODE",
  "⟲ starte Login … (kann ein paar Sekunden dauern)": "⟲ starting login … (may take a few seconds)",
  "⟲ prüfe Code …": "⟲ checking code …",
  "✅ Angemeldet! CONSTRUCT läuft jetzt mit einem langlebigen Token — kein Terminal-Login mehr nötig.": "✅ Signed in! CONSTRUCT now runs with a long-lived token — no terminal login needed anymore.",
  "🔑 LOGIN NÖTIG": "🔑 LOGIN NEEDED", "🔑 OHNE CLAUDE": "🔑 NO CLAUDE",
  "Angemeldet": "Signed in",
  "Anmeldung abgelaufen — klicken zum Einloggen": "Sign-in expired — click to log in",
  "— klicken zum Neu-Anmelden": "— click to sign in again",
  "Nicht angemeldet (Passwort?)": "Not signed in (password?)",
  "Claude Code ist nicht installiert — der Chat läuft über den Anbieter aus dem 🧠-Menü. Klicken für die Anleitung.": "Claude Code is not installed — chat runs through the provider from the 🧠 menu. Click for instructions.",
  "Claude Code ist installiert.": "Claude Code is installed.",
  "Anmelden geht danach direkt hier über diesen Knopf.": "After that you can sign in right here with this button.",
  "Dafür braucht es ein Anthropic-Konto (Abo oder API-Guthaben).": "This requires an Anthropic account (subscription or API credit).",
  "Limits nicht abrufbar:": "Limits unavailable:",
  "Nutzungs-Limit erreicht, Reset um": "Usage limit reached, resets at",
  "Reset:": "Reset:", "Uhr": "",
  "keine Daten": "no data",

  // ---- KI-Anbieter-Dialog ----
  "🧠 KI-ANBIETER": "🧠 AI PROVIDERS",
  "⟲ lade Anbieter …": "⟲ loading providers …",
  "Anbieter deaktivieren (Key bleibt gespeichert)": "Disable provider (key stays saved)",
  "(gespeichert — Standard-Modelle aktiv)": "(saved — default models active)",
  "•••••••• (gespeichert — nur zum Ändern neu eingeben)": "•••••••• (saved — only re-enter to change)",
  "✓ gespeichert — jetzt TEST klicken": "✓ saved — now click TEST",
  "✓ gespeichert — gilt ab der nächsten Nachricht": "✓ saved — applies from the next message",
  "(keine Modelle gefunden)": "(no models found)",
  "— nicht eingerichtet": "— not set up", "— noch nicht eingerichtet": "— not set up yet",
  "SPEICHERN": "SAVE", "SPEICHERN & TESTEN": "SAVE & TEST", "TEST": "TEST",
  "⟲ speichere …": "⟲ saving …", "⟲ speichere & teste …": "⟲ saving & testing …",
  "✓ eingerichtet": "✓ set up", "✓ aktiv —": "✓ active —", "✕ AUS": "✕ OFF",
  "AKTIVIEREN": "ENABLE", "✅ funktioniert —": "✅ works —",
  "⚙ Ollama": "⚙ Ollama", "▶ OLLAMA STARTEN": "▶ START OLLAMA",
  "⟲ prüfe Ollama …": "⟲ checking Ollama …",
  "Ollama ist installiert, läuft aber gerade nicht — ein Klick startet es.": "Ollama is installed but not running — one click starts it.",
  "Cody lädt das offizielle Linux-Paket (~1–2 GB), entpackt es nach": "Cody downloads the official Linux package (~1–2 GB), unpacks it to",
  "und startet es — ganz ohne Terminal. Startet nach einem Neustart automatisch mit.": "and starts it — no terminal needed. It starts automatically after a reboot.",
  "Noch keine Modelle installiert — unten eins aussuchen und ⬇ klicken.": "No models installed yet — pick one below and click ⬇.",
  "BELIEBTE MODELLE ZUM LADEN": "POPULAR MODELS TO DOWNLOAD",
  "anderes Modell von ollama.com/library — z.B. qwen3:32b": "another model from ollama.com/library — e.g. qwen3:32b",
  "⬇ LADEN": "⬇ DOWNLOAD", "INSTALLIERT": "INSTALLED", "NICHT INSTALLIERT": "NOT INSTALLED",
  "— NICHT INSTALLIERT": "— NOT INSTALLED",
  "fertig geladen — steht im 🧠-Menü bereit": "download complete — available in the 🧠 menu",
  "Download konnte nicht starten": "Download could not start",
  "Download konnte nicht starten:": "Download could not start:",
  "“ wirklich von der Platte löschen? (Kann jederzeit neu geladen werden.)": "” from disk? (You can download it again at any time.)",
  "Modell „": "Delete model “",
  "⚠ Bonsai-Demo nicht gefunden —": "⚠ Bonsai demo not found —",
  "im Bonsai-Ordner ausführen oder": "in the Bonsai folder, or set",
  "setzen.": ".",
  "⚪ aus — VRAM frei, startet beim ersten Prompt": "⚪ off — VRAM free, starts on the first prompt",
  "⏹ JETZT STOPPEN": "⏹ STOP NOW",
  "Min Leerlauf von selbst)": "min of inactivity)",
  "🟢 läuft — Modell im VRAM (stoppt nach": "🟢 running — model in VRAM (stops by itself after",
  "🔒 Keys liegen nur auf deinem Server in": "🔒 Keys are stored only on your server in",
  "(chmod 600) — sie tauchen nie im Browser auf.": "(chmod 600) — they never reach the browser.",

  // ---- Modell-/Modus-Auswahl ----
  "Konto-Standard von Claude Code": "Claude Code account default",
  "neuestes Opus — stark für Coding und komplexe Aufgaben": "latest Opus — strong for coding and complex tasks",
  "stärkstes Modell — für die härtesten und längsten Aufgaben": "most capable model — for the hardest and longest tasks",
  "Vorgänger von Opus 5.5": "predecessor of Opus 5.5",
  "schnell, schont das Limit": "fast, easy on the limit",
  "am schnellsten — kleine Aufgaben": "fastest — small tasks",
  "nicht mehr in der Auswahl": "no longer in the list",
  "KI-Anbieter einrichten…": "Set up AI providers…",
  "⚙ Anbieter einrichten…": "⚙ Set up providers…",
  "· ÜBER HERMES": "· VIA HERMES", "ÜBER HERMES": "VIA HERMES",
  "· mit Werkzeugen": "· with tools", "· Werkzeuge unbestätigt": "· tools unconfirmed",
  "· nur Chat)": "· chat only)",
  "Standard": "Default", "⚡ Auto": "⚡ Auto", "🛡 Standard": "🛡 Default", "📋 Plan": "📋 Plan",
  "fragt nach (im Web eingeschränkt)": "asks first (limited on the web)",
  "nur lesen / planen, ändert nichts": "read / plan only, changes nothing",
  "volle Rechte — alles läuft automatisch": "full permissions — everything runs automatically",
  "Ordner nicht gefunden:": "Folder not found:",
  "Mode →": "Mode →", "Modell →": "Model →", "Ordner →": "Folder →",

  // ---- Chat ----
  "⌁ Neue Session — Ordner unten wählbar, dann schreib los ⌁": "⌁ New session — pick a folder below, then start typing ⌁",
  "Keine Sessions.": "No sessions.", "Keine aktiven Sessions.": "No active sessions.",
  "(leere Session)": "(empty session)", "Nichts gefunden.": "Nothing found.",
  "Session endgültig löschen? „": "Permanently delete session “",
  "\" Das kann nicht rückgängig gemacht werden.": "”? This cannot be undone.",
  "“ Das kann nicht rückgängig gemacht werden.": "”? This cannot be undone.",
  "Name für diese Session (leer = automatischer Titel):": "Name for this session (empty = automatic title):",
  "⟲ Lade Verlauf …": "⟲ Loading history …",
  "Denke nach": "Thinking", "💭 nachgedacht": "💭 thought",
  "EINGABE": "INPUT", "ERGEBNIS": "RESULT",
  "⧉ Kopieren": "⧉ Copy", "✓ Kopiert": "✓ Copied",
  "Bearbeiten & neu senden": "Edit & resend", "↺ Neu senden": "↺ Resend",
  "⏹ STOP": "⏹ STOP", "⏹ Gestoppt.": "⏹ Stopped.",
  "⚠ mit Fehlern beendet": "⚠ finished with errors",
  "Fehler": "Error", "✗ Fehler": "✗ Error",
  "⚠ Konnte Anfrage nicht starten:": "⚠ Could not start the request:",
  "⚠ Lauf nicht mehr verfügbar (zu alt/aufgeräumt). Schick einfach nochmal.": "⚠ Run no longer available (too old / cleaned up). Just send it again.",
  "… Verbindung verloren – dock wieder an …": "… connection lost – reconnecting …",
  "⏳ läuft noch im Hintergrund:": "⏳ still running in the background:",
  "— ich melde mich, sobald es fertig ist.": "— I'll let you know when it's done.",
  "in Warteschlange — läuft automatisch nach der aktuellen Aufgabe (gleiche Session):": "queued — runs automatically after the current task (same session):",
  "Geht SOFORT an den laufenden Cody (Steering) — er bezieht es in die aktuelle Arbeit ein": "Goes IMMEDIATELY to the running Cody (steering) — he factors it into the current work",
  "Dauer · Output-Tokens dieser Antwort · gelesener Kontext (großteils Cache) · Modell": "Duration · output tokens of this reply · context read (mostly cache) · model",
  "· 📚 Kontext": "· 📚 context", "Tokens": "tokens",
  "Datei ansehen (Rechtsklick → Speichern)": "View file (right-click → Save)",
  "📄 PDF": "📄 PDF", "ist zu groß (max. 25 MB)": "is too large (max. 25 MB)",
  "Upload fehlgeschlagen": "Upload failed",
  "… (gekürzt)": "… (truncated)", "(kein Ergebnis)": "(no result)", "(kein Inhalt)": "(no content)",
  "(leer / nicht lesbar)": "(empty / unreadable)", "← zurück": "← back",
  "⛔ Limit — bis": "⛔ Limit — until",

  // ---- /help ----
  "⌨ Befehle": "⌨ Commands",
  "— neue Session": "— new session", "— Ansicht leeren": "— clear view",
  "— Arbeitsordner wechseln": "— change working folder", "— Modus wechseln": "— change mode",
  "— Modell wechseln (Claude, GPT, Gemini, DeepSeek, Ollama …)": "— change model (Claude, GPT, Gemini, DeepSeek, Ollama …)",
  "— KI-Anbieter einrichten (API-Keys, Ollama-URL)": "— set up AI providers (API keys, Ollama URL)",
  "— bei Claude anmelden (wenn der Token abgelaufen ist)": "— sign in to Claude (when the token has expired)",
  "— Skills-Ansicht": "— skills view", "— diese Liste": "— this list",
  "— ChatGPT, Gemini, DeepSeek, Ollama": "— ChatGPT, Gemini, DeepSeek, Ollama",
  "Hinweis: Claudes eingebaute Slash-Befehle funktionieren im Headless-Modus nicht — das hier sind eigene App-Befehle.": "Note: Claude's built-in slash commands don't work in headless mode — these are the app's own commands.",
  "Unbekannter Befehl": "Unknown command",
  "Unbekannter Mode. Verfügbar:": "Unknown mode. Available:",
  "Unbekanntes Modell. Claude:": "Unknown model. Claude:",
  "Extern:": "External:",
  "Externe Anbieter: erst über": "External providers: set them up first via",
  "einrichten.": ".",

  // ---- Skills / MCP ----
  "keine Skills gefunden": "no skills found", "⟲ lade…": "⟲ loading…", "Skill": "Skill",
  "⟲ prüfe Konnektoren…": "⟲ checking connectors…",
  "keine MCP-Server konfiguriert": "no MCP servers configured",
  "🟢 aktiv · 🔑 braucht Login · 🔴 Problem": "🟢 active · 🔑 needs login · 🔴 problem",
  "Freischalten: im Terminal": "To enable: in the terminal", ", oder auf": ", or at",

  // ---- Kalender ----
  "Keine Termine an diesem Tag.": "No events on this day.",
  "Keine anstehenden Termine.": "No upcoming events.",
  "ANSTEHEND": "UPCOMING", "HEUTE": "TODAY", "＋ TERMIN": "＋ EVENT", "＋ Eintragen": "＋ Add",
  "Termin eintragen (z.B. Zahnarzt)": "Add event (e.g. dentist)",
  "jedes Jahr wiederholen (z.B. Geburtstag)": "repeat every year (e.g. birthday)",
  "🔁 jährlich": "🔁 yearly", "HH:MM": "HH:MM",
  "Vorheriger Monat": "Previous month", "Nächster Monat": "Next month",
  "ganztägig": "all day", "morgen": "tomorrow", "HINZUFÜGEN": "ADD",
  "Am": "On", "(ohne Titel)": "(untitled)",

  // ---- E-Mail ----
  "Posteingang": "Inbox", "← Posteingang": "← Inbox", "Alle Postfächer": "All mailboxes",
  "Mails": "Mails", "Mails im Posteingang": "mails in the inbox",
  "KONTEN": "ACCOUNTS", "KATEGORIEN": "CATEGORIES", "keiner Kategorie": "no category",
  "(Filter aktiv).": "(filter active).", "zeigt alle.": "shows all.",
  "Keine E-Mails": "No e-mails", "(kein Betreff)": "(no subject)",
  "✉ NEUE E-MAIL": "✉ NEW E-MAIL", "NEUE E-MAIL": "NEW E-MAIL", "✉ UNGELESEN": "✉ UNREAD",
  "⟲ AKTUALISIEREN": "⟲ REFRESH", "☑ ALLE MARKIEREN": "☑ SELECT ALL", "☒ KEINE MARKIEREN": "☒ SELECT NONE",
  "🗑 LÖSCHEN": "🗑 DELETE", "🗑 LÖSCHEN (": "🗑 DELETE (", "🗑 LÖSCHE …": "🗑 DELETING …",
  "markieren": "select", "löschen": "delete", "löschen (auch auf dem Server)": "delete (on the server too)",
  "als ungelesen markieren": "mark as unread", "aus Archiv holen": "restore from archive",
  "⟲ Lade E-Mail …": "⟲ Loading e-mail …",
  "⟲ Rufe Postfächer ab … es werden ALLE Mails geladen — bei großen Postfächern kann das eine Minute dauern.": "⟲ Fetching mailboxes … ALL mails are loaded — this can take a minute for large mailboxes.",
  "↩ ANTWORTEN": "↩ REPLY", "↪ WEITERLEITEN": "↪ FORWARD", "📎 ANHANG": "📎 ATTACHMENT",
  "VON": "FROM", "AN": "TO", "CC": "CC", "BETREFF": "SUBJECT", "NACHRICHT": "MESSAGE",
  "Von:": "From:", "An:": "To:", "Betreff:": "Subject:", "> Datum:": "> Date:",
  "· Konto:": "· Account:", "· Cc:": "· Cc:",
  "---------- Weitergeleitete Nachricht ---------- Von:": "---------- Forwarded message ---------- From:",
  "(HTML-Mail — Inhalt bitte manuell übernehmen)": "(HTML mail — please copy the content manually)",
  "➤ SENDEN": "➤ SEND", "➤ EINWERFEN": "➤ SEND", "⟲ sende …": "⟲ sending …", "✅ gesendet!": "✅ sent!",
  "⚠ Empfänger fehlt": "⚠ Recipient missing", "⚠ Adresse fehlt": "⚠ Address missing",
  "⚠ Passwort eingeben": "⚠ Enter password",
  "🏷 KATEGORIE …": "🏷 CATEGORY …", "— Kategorie —": "— Category —",
  "Neue Kategorie anlegen": "Create new category", "Name der neuen Kategorie:": "Name of the new category:",
  "✕ Kategorie entfernen": "✕ Remove category",
  "Kategorisieren fehlgeschlagen:": "Categorizing failed:",
  "🏷 Kategorien existieren nur hier im Chat — auf den Mail-Servern ändert sich dadurch nichts. Gelöschte Mails wandern dagegen echt in den Server-Papierkorb.": "🏷 Categories exist only here — nothing changes on the mail servers. Deleted mails, however, really go to the server's trash.",
  "Kategorie „": "Delete category “",
  "“ löschen? (Die E-Mails bleiben natürlich erhalten.)": "”? (The e-mails are of course kept.)",
  "E-Mail wirklich löschen? „": "Really delete e-mail “",
  "“ Sie wird auch auf dem Mail-Server in den Papierkorb verschoben.": "”? It will also be moved to the trash on the mail server.",
  "E-Mail(s) wirklich löschen? Sie werden auch auf den Mail-Servern in den Papierkorb verschoben.": "e-mail(s) really? They will also be moved to the trash on the mail servers.",
  "Löschen fehlgeschlagen": "Delete failed", "Löschen fehlgeschlagen:": "Delete failed:",
  "Teilweise fehlgeschlagen:": "Partially failed:",
  "⚙ KONTEN VERWALTEN": "⚙ MANAGE ACCOUNTS", ">⚙ Konten verwalten…": ">⚙ Manage accounts…",
  "⚙ Konten verwalten…": "⚙ Manage accounts…", "⚙ E-MAIL-KONTEN": "⚙ E-MAIL ACCOUNTS",
  "＋ Konto hinzufügen": "＋ Add account", "Konto „": "Remove account “",
  "“ aus CONSTRUCT entfernen? (Das Postfach selbst bleibt natürlich bestehen — es wird nur hier nicht mehr abgerufen.)": "” from CONSTRUCT? (The mailbox itself of course stays — it's just no longer fetched here.)",
  "Passwort / App-Passwort": "Password / app password",
  "Passwort (bei Outlook/Hotmail leer lassen)": "Password (leave empty for Outlook/Hotmail)",
  "neue@adresse.de": "new@address.com",
  "⟲ teste Login + Posteingang …": "⟲ testing login + inbox …",
  "✅ verbunden!": "✅ connected!", "✅ verbunden —": "✅ connected —",
  "🔑 MICROSOFT-LOGIN": "🔑 MICROSOFT LOGIN", "⟲ starte Microsoft-Login …": "⟲ starting Microsoft login …",
  "eingeben · ⟲ warte auf Bestätigung …": "· ⟲ waiting for confirmation …",
  "öffnen ·": "and enter the code",
  "🔒 Zugangsdaten liegen nur auf deinem Server in": "🔒 Credentials are stored only on your server in",
  "Fwd:": "Fwd:", "Re:": "Re:",

  // ---- Einstellungen ----
  "Sprache": "Language", "🌐 SPRACHE": "🌐 LANGUAGE",
  "Sprache der Oberfläche und des Assistenten. Die Seite lädt danach neu.": "Language of the interface and the assistant. The page reloads afterwards.",
  "Kacheln": "Tiles", "Modelle & Anbieter": "Models & providers", "Namen": "Names",
  "Charakter": "Character", "Farbwelt": "Color theme", "Hintergrund": "Background",
  "⚙ KACHELN": "⚙ TILES", "🧠 MODELLE & ANBIETER": "🧠 MODELS & PROVIDERS",
  "📧 E-MAIL-KONTEN": "📧 E-MAIL ACCOUNTS", "🔄 AKTUALISIERUNG": "🔄 UPDATES",
  "🙋 NAMEN": "🙋 NAMES", "📜 CHARAKTER": "📜 CHARACTER", "🎨 FARBWELT": "🎨 COLOR THEME",
  "🖼 HINTERGRUND": "🖼 BACKGROUND", "💬 Chats": "💬 Chats", "FEST": "FIXED", "AKTIV": "ACTIVE",
  "Der Hauptzweck der Oberfläche — lässt sich nicht abschalten.": "The main purpose of the interface — can't be turned off.",
  "Termine eintragen und ansehen. Braucht nichts weiter.": "Add and view events. Needs nothing else.",
  "Zeigt die Skills aus deinen Projekten. Nur mit Claude Code sinnvoll.": "Shows the skills from your projects. Only useful with Claude Code.",
  "Postfach über IMAP/SMTP. Zugangsdaten liegen lokal.": "Mailbox via IMAP/SMTP. Credentials stay local.",
  "Zeigt konfigurierte MCP-Server. Nur mit Claude Code sinnvoll.": "Shows configured MCP servers. Only useful with Claude Code.",
  "1 · Claude Code": "1 · Claude Code", "2 · Fremde Anbieter": "2 · Other providers", "3 · Hermes": "3 · Hermes",
  "🔑 Anmeldung": "🔑 Sign-in", "📋 Anleitung": "📋 Instructions", "Installieren": "Install",
  "Kachel E-Mails ist abgeschaltet": "E-mail tile is turned off",
  "Postfächer anlegen, Passwort ändern, Verbindung testen — die Konten werden in der E-Mail-Ansicht verwaltet (dort auch links unten über „Konten verwalten“).": "Add mailboxes, change passwords, test connections — accounts are managed in the e-mail view (also via “Manage accounts” at the bottom left there).",
  "Beim Start nach Updates suchen": "Check for updates at startup",
  "Wie oft höchstens": "At most how often",
  "Verhindert, dass fünf Neustarts an einem Nachmittag fünf Netzrunden auslösen.": "Prevents five restarts in one afternoon from causing five network checks.",
  "bei jedem Start": "on every start", "höchstens alle 6 Stunden": "at most every 6 hours",
  "höchstens einmal am Tag": "at most once a day", "höchstens einmal die Woche": "at most once a week",
  "Jetzt suchen": "Check now", "prüfe …": "checking …", "läuft…": "running…",
  "✓ alles aktuell": "✓ all up to date", "ALLES AKTUELL": "ALL UP TO DATE",
  "AKTUALISIERT": "UPDATED", "UPDATE FEHLGESCHLAGEN": "UPDATE FAILED",
  "✓ aktualisiert": "✓ updated", "✓ fertig": "✓ done", "übersprungen": "skipped",
  "zuletzt gerade eben geprüft": "last checked just now", "zuletzt vor": "last checked",
  "min geprüft": "min ago", "h geprüft": "h ago",
  "nicht installiert": "not installed", "nicht gestartet": "not started",
  "braucht Node.js (nodejs.org)": "requires Node.js (nodejs.org)",
  "nur Linux / macOS": "Linux / macOS only",
  "Wie soll ich dich nennen?": "What should I call you?",
  "Steht im Chat über deinen Nachrichten und wird den Modellen mitgegeben. Leer lassen geht auch — dann bleibt es unpersönlich.": "Shown in the chat above your messages and passed to the models. You can leave it empty — then it stays impersonal.",
  "dein Name": "your name", "Wie heißt der Assistent?": "What is the assistant called?",
  "Bilder": "Pictures",
  "Erscheinen im Chat neben den Nachrichten. Ohne eigenes Bild steht bei dir der Anfangsbuchstabe.": "Shown in the chat next to the messages. Without a picture of your own, your initial is shown.",
  "Deins wählen…": "Choose yours…", "Seins wählen…": "Choose the assistant's…",
  "Namen wirken nach dem Neuladen der Seite.": "Names take effect after reloading the page.",
  "Charakter (SOUL.md)": "Character (SOUL.md)", "Über dich (USER.md)": "About you (USER.md)",
  "Über dich": "About you", "wird geladen…": "loading…", "Speichern": "Save",
  "✓ gespeichert": "✓ saved", "⚠ nicht gespeichert": "⚠ not saved",
  "wirkt ab dem nächsten Chat": "takes effect from the next chat",
  "Matrix": "Matrix", "Bernstein": "Amber", "Eis": "Ice", "Space": "Space", "Asche": "Ash", "Blut": "Blood",
  "Grün auf Schwarz. Der Ursprung.": "Green on black. The original.",
  "Alter Bernstein-Monitor — warm, augenschonend.": "Old amber monitor — warm, easy on the eyes.",
  "Kühles Cyan auf Tiefblau.": "Cool cyan on deep blue.",
  "Violett auf Nachtblau.": "Violet on midnight blue.",
  "Neutrales Grau — zurückhaltend, gut zum Lesen.": "Neutral gray — understated, good for reading.",
  "Rot auf Schwarz. Laut.": "Red on black. Loud.",
  "Matrix-Regen": "Matrix rain", "Die Vorgabe. Kostet etwas Rechenleistung.": "The default. Costs a bit of processing power.",
  "Eigenes Bild": "Custom image",
  "Ersetzt den Regen. Wird abgedunkelt, damit die Schrift lesbar bleibt.": "Replaces the rain. Dimmed so the text stays readable.",
  "Schlicht dunkel": "Plain dark", "Nichts im Hintergrund — am sparsamsten.": "Nothing in the background — the most economical.",
  "🖼 Bild wählen…": "🖼 Choose image…", "✕ Bild entfernen": "✕ Remove image",
  "Abdunkeln:": "Dim:", "VORSCHAU": "PREVIEW", "kein Bild gewählt": "no image selected",
  "Abbrechen": "Cancel",

  // ---- Backend-Meldungen (kommen als Text vom Server) ----
  "✅ Cody ist fertig": "✅ Cody is done",
  "kein Token — bitte einloggen": "no token — please sign in",
  "⛔ Nutzungs-Limit der Subscription erreicht — geht um": "⛔ Subscription usage limit reached — continues at",
  "Uhr weiter. (Oben rechts siehst du die Auslastung.)": ". (Usage is shown at the top right.)",
  "🔑 Anmeldung abgelaufen oder ungültig — oben rechts auf das Schlüssel-Symbol klicken und neu einloggen.": "🔑 Sign-in expired or invalid — click the key icon at the top right and sign in again.",
  "🌊 Anthropic ist gerade überlastet — kurz warten und nochmal senden.": "🌊 Anthropic is overloaded right now — wait a moment and send again.",
  "Es läuft gerade ein Chat — bitte erst abwarten.": "A chat is currently running — please wait for it to finish.",
  "Der Login über die Oberfläche braucht ein Pseudo-Terminal — das gibt es unter Windows nicht. Einmal ein Terminal öffnen, `claude` eingeben und sich dort anmelden; danach findet CONSTRUCT die Anmeldung von selbst.": "Signing in from the interface needs a pseudo-terminal, which Windows doesn't have. Open a terminal once, type `claude` and sign in there; CONSTRUCT will then pick up the sign-in by itself.",
  "Claude Code ist nicht installiert.": "Claude Code is not installed.",
  "Code fehlt": "Code missing", "Kein Login aktiv — bitte neu starten.": "No login in progress — please start again.",
  "Login fehlgeschlagen — Code richtig und vollständig kopiert?": "Login failed — was the code copied correctly and completely?",
  "Einfach nochmal auf LOGIN STARTEN klicken.": "Just click START LOGIN again.",
  "Keine Login-URL bekommen. Ausgabe:": "Didn't get a login URL. Output:",
  "keine Datei": "no file", "Datei zu groß": "File too large", "Datei zu groß (max. 25 MB)": "File too large (max. 25 MB)",
  "date und title sind nötig": "date and title are required",
  "_↪ Modellwechsel: neue Sitzung, bisheriger Verlauf als Kontext übernommen._": "_↪ Model switch: new session, previous history carried over as context._",
  "↪ Modellwechsel: neue Sitzung, bisheriger Verlauf als Kontext übernommen.": "↪ Model switch: new session, previous history carried over as context.",
  "claude-CLI nicht gefunden": "claude CLI not found",
  "npm fehlt — Claude Code wird darüber installiert. Node.js von nodejs.org einrichten und CONSTRUCT neu starten.": "npm is missing — Claude Code is installed through it. Install Node.js from nodejs.org and restart CONSTRUCT.",
  "Installation lief durch, aber 'claude' ist nicht im PATH. Meist hilft ein Neustart von CONSTRUCT.": "Installation finished, but 'claude' is not on the PATH. Restarting CONSTRUCT usually helps.",
  "Für fremde Modelle wird Hermes gebraucht — es ist nicht installiert. Unter ⚙ Einstellungen → „Modelle & Anbieter“ lässt es sich einrichten.": "Other providers' models need Hermes — it isn't installed. You can set it up under ⚙ Settings → “Models & providers”.",
  "npm beendet mit Code": "npm exited with code", "claude beendet mit Code": "claude exited with code",
  "Server-Fehler:": "Server error:", "Unbekannter Fehler": "Unknown error",
  "⏳ Bonsai wird in den VRAM geladen …": "⏳ Loading Bonsai into VRAM …",
  "Ollama ist nicht installiert": "Ollama is not installed",
  "Ollama antwortet nicht nach dem Start.": "Ollama doesn't respond after starting.",
  "keine URL konfiguriert": "no URL configured", "nicht erreichbar": "unreachable", "nicht erreichbar:": "unreachable:",
  "API-Key ungültig oder fehlt": "API key invalid or missing",
  "kein Guthaben mehr auf dem Konto": "no credit left on the account",
  "Modell nicht gefunden — im 🧠-Menü ein anderes wählen": "Model not found — choose another one in the 🧠 menu",
  "Ungültiger Modellname": "Invalid model name",
  "Ungültiger Modellname — z.B. gemma3:4b (siehe ollama.com/library)": "Invalid model name — e.g. gemma3:4b (see ollama.com/library)",
  "— läuft Ollama?": "— is Ollama running?",
  "🦙 Ollama nicht erreichbar — läuft es? (Standard: Port 11434)": "🦙 Ollama unreachable — is it running? (default: port 11434)",
  "läuft": "running", "kein Modell unter": "no model at",
  "Google Gemma 4 (Standard) — Frontier-Klasse für lokale Modelle": "Google Gemma 4 (default) — frontier class for local models",
  "Gemma 3 — leichter Allrounder, läuft ab ~8 GB RAM": "Gemma 3 — light all-rounder, runs from ~8 GB RAM",
  "Gemma 3, winzig — läuft praktisch überall": "Gemma 3, tiny — runs practically anywhere",
  "Qwen 3.5, große Stufe — ab ~32 GB RAM": "Qwen 3.5, large tier — from ~32 GB RAM",
  "Meta Llama 3.1 — bewährter 8B-Standard": "Meta Llama 3.1 — proven 8B standard",
  "Coding-Spezialist — Code schreiben, erklären, vervollständigen": "Coding specialist — write, explain, complete code",
  "Microsoft Phi-4 — stark in Logik & Mathe für seine Größe": "Microsoft Phi-4 — strong at logic & math for its size",
  "Hermes ist nicht installiert. Unter ⚙ Einstellungen → „Modelle & Anbieter“ lässt es sich einrichten.": "Hermes is not installed. You can set it up under ⚙ Settings → “Models & providers”.",
  "Die automatische Installation gibt es nur für Linux und macOS. Unter Windows in PowerShell:  iex (irm https://hermes-agent.nousresearch.com/install.ps1)": "Automatic installation is only available for Linux and macOS. On Windows, in PowerShell:  iex (irm https://hermes-agent.nousresearch.com/install.ps1)",
  "Heruntergeladene Datei sieht nicht wie der Installer aus — abgebrochen.": "The downloaded file doesn't look like the installer — aborted.",
  "Installer lief durch, aber 'hermes' ist nicht im PATH. Meist hilft ein Neustart von CONSTRUCT.": "Installer finished, but 'hermes' is not on the PATH. Restarting CONSTRUCT usually helps.",
  "Hermes hat keine Sitzung geöffnet.": "Hermes didn't open a session.",
  "Installer beendet mit Code": "Installer exited with code",
  "(fertig — Hermes meldet zum letzten Werkzeug eines Laufs keine Ausgabe)": "(done — Hermes reports no output for the last tool of a run)",
  "Hermes antwortet nicht auf": "Hermes doesn't respond to",
  "_↪ Die bisherige Hermes-Sitzung ließ sich nicht fortsetzen — neue Sitzung, bisheriger Verlauf als Kontext übernommen._": "_↪ The previous Hermes session couldn't be resumed — new session, previous history carried over as context._",
  "↪ Die bisherige Hermes-Sitzung ließ sich nicht fortsetzen — neue Sitzung, bisheriger Verlauf als Kontext übernommen.": "↪ The previous Hermes session couldn't be resumed — new session, previous history carried over as context.",
  "Minuten — Lauf abgebrochen (Modell/Anbieter hängt?).": "minutes — run aborted (model/provider stuck?).",
  "!! npm nicht im PATH — Claude Code kann nicht aktualisiert werden.": "!! npm not on PATH — Claude Code can't be updated.",
  ") — es läuft weiter mit": ") — continuing with",
  "✓ Claude Code ist aktuell (": "✓ Claude Code is up to date (",
  "!! Hermes-Prüfung fehlgeschlagen (Code": "!! Hermes check failed (code",
  "✓ Hermes ist aktuell (": "✓ Hermes is up to date (",
  "Zeitüberschreitung nach": "Timed out after", "npm fehlt": "npm missing",
  "Prüfung fehlgeschlagen": "Check failed",
  "GMX-Webmail → Einstellungen → POP3/IMAP → „Zugriff erlauben“ aktivieren. Dann hier das normale GMX-Passwort eintragen.": "GMX webmail → Settings → POP3/IMAP → enable “Allow access”. Then enter your normal GMX password here.",
  "Google-Konto → Sicherheit → 2-Faktor aktivieren → „App-Passwörter“ → neues App-Passwort (16 Zeichen) erzeugen und hier eintragen (NICHT das normale Passwort).": "Google account → Security → enable 2-step verification → “App passwords” → create a new app password (16 characters) and enter it here (NOT your normal password).",
  "Microsoft erlaubt kein Passwort-IMAP mehr — einfach auf MICROSOFT-LOGIN klicken und den angezeigten Code auf der Microsoft-Seite eingeben.": "Microsoft no longer allows password IMAP — just click MICROSOFT LOGIN and enter the displayed code on the Microsoft page.",
  "Nachricht nicht (mehr) gefunden": "Message not found (anymore)",
  "Keine gültige E-Mail-Adresse": "Not a valid e-mail address",
  "Microsoft-Login nötig — unter ⚙ Konten verwalten anmelden.": "Microsoft login needed — sign in under ⚙ Manage accounts.",
  "Anhang nicht gefunden": "Attachment not found", "Kein (gültiger) Empfänger": "No (valid) recipient",
  "Unbekannter Anbieter für": "Unknown provider for",
  "— ich kenne GMX, Gmail und Outlook/Hotmail.": "— I know GMX, Gmail and Outlook/Hotmail.",
  "Microsoft-Token abgelaufen — bitte unter ⚙ Konten neu anmelden.": "Microsoft token expired — please sign in again under ⚙ Accounts.",
  "Konto nicht eingerichtet (⚙ Konten verwalten)": "Account not set up (⚙ Manage accounts)",
  "Konto nicht eingerichtet": "Account not set up", "nicht lesbar": "unreadable", "nicht wählbar": "not selectable",
  "Bonsai nicht gefunden unter": "Bonsai not found at",
  "llama-server ließ sich nicht starten:": "llama-server could not be started:",
  "llama-server ist beim Start abgebrochen (Log:": "llama-server aborted on startup (log:",
  "Nur Bilder und PDFs erlaubt (nicht": "Only images and PDFs allowed (not",
  "Kategorie löschen": "Delete category",
  "Konto aus der Liste entfernen": "Remove account from the list",
  // ---- Telegram ----
  "Telegram": "Telegram", "✈ TELEGRAM": "✈ TELEGRAM",
  "Sprich mit {a} von unterwegs — per Text oder Sprachnachricht. Dazu Erinnerungen an Termine, eine Meldung, wenn ein langer Lauf fertig ist, und geplante Aufgaben aus dem Kalender. Läuft nur, solange CONSTRUCT läuft.": "Talk to {a} on the go — by text or voice message. Plus reminders for events, a message when a long run finishes, and scheduled tasks from the calendar. Only works while CONSTRUCT is running.",
  "Telegram-Bot aktiv": "Telegram bot enabled", "Bot-Token": "Bot token",
  "Deine Chat-ID": "Your chat ID",
  "Nur diese ID darf mit dem Bot reden. Unbekannt? Bot aktivieren und ihm irgendetwas schreiben — dann erscheint sie hier.": "Only this ID may talk to the bot. Don't know it? Enable the bot and send it any message — it will show up here.",
  "Modell und Modus": "Model and mode",
  "Womit der Bot antwortet. „Plan“ liest nur und ändert nichts — die sichere Wahl, wenn das Handy mal in fremde Hände gerät.": "What the bot answers with. “Plan” only reads and changes nothing — the safe choice in case your phone ends up in the wrong hands.",
  "Erinnerungen an Termine": "Event reminders",
  "Morgens eine Übersicht über den Tag, vor terminierten Einträgen ein Ping.": "A daily overview in the morning, and a ping before timed events.",
  "kein Ping vorher": "no ping beforehand", "10 Min vorher": "10 min before", "15 Min vorher": "15 min before",
  "30 Min vorher": "30 min before", "60 Min vorher": "60 min before",
  "Übersicht um {h} Uhr": "Overview at {h}",
  "Melden, wenn ein langer Lauf fertig ist": "Notify when a long run finishes",
  "Nur wenn gerade niemand im Fenster zuschaut.": "Only when nobody is watching the window.",
  "Test-Nachricht": "Test message", "aus": "off", "noch nicht eingerichtet": "not set up yet",
  "startet …": "starting …", "wartet auf deine Chat-ID": "waiting for your chat ID",
  "⚠ Derselbe Bot wird schon woanders abgefragt (anderer Rechner oder Server). Dort stoppen oder einen eigenen Bot anlegen.": "⚠ This bot is already being polled somewhere else (another computer or server). Stop it there or create a separate bot.",
  "Nachricht von {n} ({id})": "Message from {n} ({id})", "Übernehmen": "Use it",
  "aus der Umgebung (TELEGRAM_TOKEN)": "from the environment (TELEGRAM_TOKEN)",
  "Token ungültig:": "Invalid token:",
  "läuft zur Termin-Zeit automatisch, Ergebnis per Telegram": "runs automatically at the event time, result via Telegram",
  "— Aufgabe:": "— Task:",
  "empfaenger@beispiel.de (mehrere mit Komma)": "recipient@example.com (several separated by commas)",
  "CLAUDE · VOLLER ZUGRIFF (TOOLS, DATEIEN)": "CLAUDE · FULL ACCESS (TOOLS, FILES)",
  "CLAUDE · VOLLER ZUGRIFF (TOOLS, DATEIEN) — NICHT INSTALLIERT": "CLAUDE · FULL ACCESS (TOOLS, FILES) — NOT INSTALLED",
  "Nachinstallieren (braucht Node.js):": "Install it (requires Node.js):",
  "Claude Code ist auf diesem Rechner <b>nicht installiert</b>. Ohne das läuft der Chat über den Anbieter aus dem 🧠-Menü (ChatGPT, Gemini …) — das reicht zum Reden, aber nicht für Dateien und Terminal.": "Claude Code is <b>not installed</b> on this computer. Without it, chat runs through the provider from the 🧠 menu (ChatGPT, Gemini …) — enough for talking, but not for files and the terminal.",
  "Anmelden danach <b>einmal im Terminal</b>: <code>claude</code> eingeben und dem Login folgen. CONSTRUCT erkennt die Anmeldung anschließend von selbst — der Login-Dialog in der Oberfläche braucht ein Pseudo-Terminal, das es unter Windows nicht gibt.": "Then sign in <b>once in a terminal</b>: type <code>claude</code> and follow the login. CONSTRUCT picks up the sign-in by itself afterwards — the login dialog in the interface needs a pseudo-terminal, which Windows doesn't have.",
  "⚡ Fremde Modelle laufen über <b>Hermes</b> und können damit Dateien und Terminal. Skills, Kalender und E-Mail bleiben Claude Code vorbehalten. Beim Modellwechsel mitten im Gespräch nimmt {a} den bisherigen Verlauf automatisch mit.": "⚡ Other providers' models run through <b>Hermes</b> and can therefore use files and the terminal. Skills, calendar and e-mail remain reserved for Claude Code. When you switch models mid-conversation, {a} automatically carries the history over.",

  // ---- Anbieter & Modellkatalog (llm.py) ----
  "API-Key von platform.openai.com → API keys": "API key from platform.openai.com → API keys",
  "API-Key von aistudio.google.com/apikey (kostenloses Kontingent vorhanden)": "API key from aistudio.google.com/apikey (free tier available)",
  "API-Key von platform.deepseek.com": "API key from platform.deepseek.com",
  "Lokale Modelle (Gemma & Co.) — Ollama muss laufen (Port 11434)": "Local models (Gemma & co.) — Ollama must be running (port 11434)",
  "Google Gemma 4, effiziente Stufe — Reasoning & multimodal": "Google Gemma 4, efficient tier — reasoning & multimodal",
  "Gemma 4 12B — stark, ab ~16 GB RAM": "Gemma 4 12B — strong, from ~16 GB RAM",
  "Gemma 4 26B (MoE) — Topstufe, ab ~32 GB RAM": "Gemma 4 26B (MoE) — top tier, from ~32 GB RAM",
  "Alibaba Qwen 3.5 — aktuelle Generation, multimodal": "Alibaba Qwen 3.5 — current generation, multimodal",
  "Qwen 3.5, klein & flott": "Qwen 3.5, small & quick",
  "DeepSeek R1 (destilliert) — Reasoning-Modell, denkt sichtbar nach": "DeepSeek R1 (distilled) — reasoning model, thinks visibly",
  "Mistral 7B — schneller Klassiker aus Frankreich": "Mistral 7B — fast classic from France"
};

// Ganze Absätze mit Auszeichnung. Schlüssel = Klartext des Elements
// (Leerraum zusammengefasst), Wert = englisches HTML.
var HTML = {
  "In Telegram bei @BotFather: /newbot → Namen vergeben → Token kopieren.":
    "In Telegram, open <b>@BotFather</b>: <code>/newbot</code> → choose a name → copy the token.",
  "Neben Claude Code kannst du hier weitere Anbieter hinterlegen — ChatGPT, Gemini, DeepSeek, lokale Ollama-Modelle oder jede andere OpenAI-kompatible API. Sie laufen über Hermes und können damit ebenfalls Dateien und Terminal. Auswahl danach unten links über 🧠.":
    "Besides Claude Code you can add more providers here — ChatGPT, Gemini, DeepSeek, local Ollama models or any other OpenAI-compatible API. They run through <b>Hermes</b> and can therefore use files and the terminal too. Pick them afterwards via 🧠 at the bottom left.",
  "Läuft über dein Anthropic-Abo (OAuth) oder einen API-Key. Der einzige Weg mit echtem Zugriff auf Dateien und Terminal — hier greifen 📂 Ordner und 🛡 Modus. Ein Schlüssel von einem anderen Anbieter funktioniert dafür nicht.":
    "Runs on your <b>Anthropic subscription</b> (OAuth) or an API key. The only way with <b>real access</b> to files and the terminal — this is where 📂 Folder and 🛡 Mode apply. A key from another provider won't work for this.",
  "ChatGPT, Gemini, DeepSeek, lokale Ollama-Modelle oder jede OpenAI-kompatible API. Diese Modelle laufen über Hermes (Punkt 3) und können damit ebenfalls Dateien und Terminal. Schlüssel bleiben lokal in .llm-config.json. Angezeigt werden nur Modelle, die Werkzeug-Aufrufe beherrschen — ohne die würde der Agent seine Befehle als Fließtext ausgeben, statt sie auszuführen.":
    "ChatGPT, Gemini, DeepSeek, local Ollama models or any OpenAI-compatible API. These models run through <b>Hermes</b> (item 3) and can therefore use files and the terminal too. Keys stay local in <code>.llm-config.json</code>.<br>Only models that <b>support tool calls</b> are shown — without them the agent would print its commands as plain text instead of running them.",
  "Fährt die Chat-Anbieter von oben mit Werkzeugen — Dateien und Terminal ohne Anthropic-Konto, auch mit lokalen Modellen über Ollama. Ohne Hermes lassen sich fremde Modelle nicht nutzen.":
    "Drives the <b>chat providers above with tools</b> — files and terminal without an Anthropic account, also with local models via Ollama. Without Hermes, other providers' models can't be used.",
  "Holt neue Fassungen von Claude Code und Hermes, sobald CONSTRUCT hochfährt — im Hintergrund, der Chat bleibt bedienbar. Ohne das bleiben beide auf dem Stand von damals: ihre eigene Selbstaktualisierung ist ab Werk abgeschaltet.":
    "Fetches new versions of <b>Claude Code</b> and <b>Hermes</b> when CONSTRUCT starts — in the background, the chat stays usable. Without this, both stay on their old version: their own auto-update is off by default.",
  "CONSTRUCT ist der Ort, er ist die Person darin. Wer ihn umbenennt, sollte auch SOUL.md anpassen — dort steht sein Charakter.":
    "CONSTRUCT is the place, the assistant is the person in it. If you rename them, also adjust <code>SOUL.md</code> — that's where their character is described.",
  "Beides wird bei jeder Nachricht mitgelesen — auch von fremden Modellen. Charakter beschreibt, wer der Assistent ist; Über dich, was er über dich wissen soll. Reiner Text, Markdown erlaubt.":
    "Both are read along with <b>every</b> message — by other providers' models too. <b>Character</b> describes who the assistant is; <b>About you</b>, what they should know about you. Plain text, Markdown allowed.",
  "🟢 aktiv · 🔑 braucht Login · 🔴 Problem Freischalten: im Terminal claudec → /mcp, oder auf claude.ai → Connectors.":
    "🟢 active · 🔑 needs login · 🔴 problem<br><br>To enable: in the terminal <code>claudec</code> → <code>/mcp</code>, or at <b>claude.ai → Connectors</b>."
};

// Texte mit eingesetzten Werten. Geprüft gegen den Klartext eines Knotens.
var RX = [
  [/^zuletzt vor (\d+) min geprüft$/, 'last checked $1 min ago'],
  [/^zuletzt vor (\d+) h geprüft$/, 'last checked $1 h ago'],
  [/^Reset: (.+) Uhr$/, 'Reset: $1'],
  [/^(\d+) E-Mail\(s\) wirklich löschen\? Sie werden auch auf den Mail-Servern in den Papierkorb verschoben\.$/, 'Really delete $1 e-mail(s)? They will also be moved to the trash on the mail servers.'],
  [/^Keine Termine in den nächsten (\d+) Tagen eingetragen\.$/, 'No events in the next $1 days.'],
  [/^✓ aktiv — (\d+) Modelle$/, '✓ active — $1 models'],
  [/^✅ verbunden — (\d+) Modelle$/, '✅ connected — $1 models'],
  [/^INSTALLIERTE MODELLE \((\d+)\)$/, 'INSTALLED MODELS ($1)'],
  [/^PrismML-Bonsai über den llama-server des Bonsai-Demos — startet erst beim ersten Prompt und räumt den VRAM nach (\d+) Min Leerlauf wieder frei$/,
   'PrismML Bonsai via the Bonsai demo\'s llama-server — starts on the first prompt and frees the VRAM after $1 min of inactivity']
];

// Einzelne Wörter, die überall in Beschriftungen stecken (Anbieternamen).
// Läuft zuletzt und nur auf Texten, die ohnehin schon als Oberfläche gelten.
var WORDS = [
  [/\((lokal|LOKAL)\)/g, function(m, w){ return w === 'LOKAL' ? '(LOCAL)' : '(local)'; }]
];

function norm(s){ return String(s).replace(/\s+/g, ' ').trim(); }
function wrap(orig, out){
  var m = /^\s*/.exec(orig)[0], n = /\s*$/.exec(orig)[0];
  return m + out + n;
}

// Bruchstücke: nur Schlüssel mit Leerzeichen (Satzteile), längste zuerst.
// Einzelwörter nur als ganzer Knoten — sonst würde "Kalender" auch im
// Betreff einer Mail umgeschrieben.
var FRAG = null;
function frag(){
  if (FRAG !== null) return FRAG;
  var keys = Object.keys(EN).filter(function(k){ return k.length >= 6 && /\s/.test(k) && EN[k] !== k; })
    .sort(function(a, b){ return b.length - a.length; });
  // Wortgrenze nur prüfen, wo der Schlüssel mit einem Buchstaben anfängt bzw.
  // endet — „“ löschen?“ folgt direkt auf einen Namen und soll trotzdem greifen.
  var esc = keys.map(function(k){
    var e = k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    if (/^[\p{L}\p{N}]/u.test(k)) e = '(?<![\\p{L}\\p{N}])' + e;
    if (/[\p{L}\p{N}]$/u.test(k)) e = e + '(?![\\p{L}\\p{N}])';
    return e;
  });
  try {
    FRAG = new RegExp('(?:' + esc.join('|') + ')', 'gu');
  } catch (e) { FRAG = false; }        // sehr alte WebViews ohne Lookbehind
  return FRAG;
}

function tr(s){
  if (LANG !== 'en' || s == null) return s;
  var n = norm(s);
  if (!n || !/[A-Za-zÄÖÜäöüß]/.test(n)) return s;
  if (Object.prototype.hasOwnProperty.call(EN, n)) return wrap(s, EN[n]);
  for (var i = 0; i < RX.length; i++) if (RX[i][0].test(n)) return wrap(s, n.replace(RX[i][0], RX[i][1]));
  var f = frag(), out = n;
  if (f) out = out.replace(f, function(m){ return EN[m]; });
  for (var w = 0; w < WORDS.length; w++) out = out.replace(WORDS[w][0], WORDS[w][1]);
  return out === n ? s : wrap(s, out);
}

// T(): für Texte, die nicht durch das DOM laufen, und Platzhalter {name}.
function T(s, vars){
  var out = tr(s);
  if (vars) out = String(out).replace(/\{(\w+)\}/g, function(m, k){ return k in vars ? vars[k] : m; });
  return out;
}

window.I18N = { lang: LANG, locale: LANG === 'de' ? 'de-DE' : 'en-GB', tr: tr };
window.T = T;
if (LANG !== 'en') return;

// ---- Automatik fürs DOM ----
// Nutzer- und Modellinhalte bleiben, wie sie sind. ALLOW holt Bedienelemente
// zurück, die innerhalb solcher Bereiche sitzen (Kopier-Knopf im Codeblock).
var SKIP = '.seg,.tc-in,.tc-out,.tc-sum,.msg.user .bubble,pre,code,textarea,script,style,' +
           '[translate="no"],.ml-main,.ml-cat,.mh-line,#mview,.skillbody';
var ALLOW = '.copy-btn,.edit-btn,.tc-lbl';
var ATTRS = ['title', 'placeholder', 'aria-label'];
// Attribute eines Eingabefelds sind Bedienung (Platzhalter), sein Inhalt nicht —
// darum gilt für Attribute eine schmalere Sperrliste ohne textarea.
var SKIP_ATTR = SKIP.replace('textarea,', '');

function skipped(el){
  if (!el || !el.closest) return false;
  return !!el.closest(SKIP) && !el.closest(ALLOW);
}
function doText(t){
  if (skipped(t.parentElement)) return;
  var v = t.nodeValue, o = tr(v);
  if (o !== v) t.nodeValue = o;
}
function doAttrs(el){
  if (el.closest(SKIP_ATTR) && !el.closest(ALLOW)) return;
  for (var i = 0; i < ATTRS.length; i++) {
    var a = ATTRS[i], v = el.getAttribute(a);
    if (v) { var o = tr(v); if (o !== v) el.setAttribute(a, o); }
  }
}
function doEl(el){
  if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') { doAttrs(el); return; }
  if (skipped(el)) {
    // Innerhalb gesperrter Bereiche nur die erlaubten Bedienelemente
    var ok = el.querySelectorAll ? el.querySelectorAll(ALLOW) : [];
    for (var i = 0; i < ok.length; i++) walk(ok[i], true);
    return;
  }
  walk(el, false);
}
// Nur Elemente mit Auszeichnung direkt darin kommen als Absatz in Frage —
// spart das textContent für jeden der tausend übrigen Knoten.
function rich(el){ return !!el.querySelector(':scope > b, :scope > code, :scope > br'); }
function walk(el, forced){
  doAttrs(el);
  if (el.firstElementChild && rich(el)) {
    var k = norm(el.textContent);
    if (k.length < 2000 && Object.prototype.hasOwnProperty.call(HTML, k)) { el.innerHTML = HTML[k]; return; }
  }
  for (var c = el.firstChild; c; c = c.nextSibling) {
    if (c.nodeType === 3) { if (forced || !skipped(el)) { var v = c.nodeValue, o = tr(v); if (o !== v) c.nodeValue = o; } }
    else if (c.nodeType === 1) { if (forced && !c.closest(SKIP)) walk(c, true); else doEl(c); }
  }
}

// Absätze, deren Text über mehrere Knoten verteilt ist, erkennt man erst am
// Elternelement — deshalb bei jeder Änderung auch den Elternteil prüfen.
function checkParent(el){
  for (var p = el, i = 0; p && p.nodeType === 1 && i < 3; p = p.parentElement, i++) {
    if (!p.firstElementChild || !rich(p) || skipped(p)) continue;
    var k = norm(p.textContent);
    if (k.length < 2000 && Object.prototype.hasOwnProperty.call(HTML, k)) { p.innerHTML = HTML[k]; return; }
  }
}

var mo = new MutationObserver(function(list){
  for (var i = 0; i < list.length; i++) {
    var m = list[i];
    if (m.type === 'childList') {
      for (var j = 0; j < m.addedNodes.length; j++) {
        var n = m.addedNodes[j];
        if (n.nodeType === 3) doText(n);
        else if (n.nodeType === 1) doEl(n);
      }
      if (m.addedNodes.length && m.target.nodeType === 1) checkParent(m.target);
    } else if (m.type === 'characterData') {
      doText(m.target);
    } else if (m.type === 'attributes') {
      var el = m.target, v = el.getAttribute(m.attributeName);
      if (v && !(el.closest(SKIP_ATTR) && !el.closest(ALLOW))) { var o = tr(v); if (o !== v) el.setAttribute(m.attributeName, o); }
    }
  }
});
mo.observe(document.documentElement, {
  childList: true, subtree: true, characterData: true,
  attributes: true, attributeFilter: ATTRS
});

// Dialoge laufen nicht durchs DOM
['alert', 'confirm'].forEach(function(f){
  var orig = window[f];
  window[f] = function(msg){ return orig.call(window, tr(String(msg == null ? '' : msg))); };
});
var origPrompt = window.prompt;
window.prompt = function(msg, def){ return origPrompt.call(window, tr(String(msg == null ? '' : msg)), def); };
})();
