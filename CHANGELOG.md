# Changelog

All notable changes to CONSTRUCT. Versions follow [semantic versioning](https://semver.org).

## 5.3.1 — 2026-09-25

### Fixed
- When a provider fails via Hermes (quota used up, key rejected, service
  down, unknown model), the chat now shows a short hint in your language
  instead of Hermes' long English message with terminal commands (`/retry`,
  `hermes fallback add`) that do nothing in CONSTRUCT. On the Gemini free tier
  it also explains why tool tasks hit the limit quickly.

## 5.3.0 — 2026-09-25

### Fixed
- **Other providers now get Cody's persona and calendar too.** Until now only
  Claude runs received SOUL.md, USER.md and the upcoming events; with Gemini,
  ChatGPT, Ollama & co. (via Hermes) the assistant had no name, no character
  and knew nothing about the calendar. CONSTRUCT now writes the persona to
  `$HERMES_HOME/SOUL.md` (only if that file is missing, Hermes' default, or
  was written by CONSTRUCT — a SOUL.md you wrote for Hermes yourself is left
  alone) and attaches the calendar to every message; the chat history hides
  it again.

## 5.2.0 — 2026-09-25

### Changed
- **Voice input writes live.** The text now appears in the message field
  while you speak (Gemini 3.5 Transcribe Live over a WebSocket, the key stays
  on the server) instead of only after you stop. Each sentence is cleaned up
  after the pause — filler words disappear. Enter ends dictation, Esc discards
  it and restores the field; up to 9½ minutes per dictation.
- The WebSocket checks password protection and origin itself (HTTP middleware
  does not cover WebSockets).

## 5.1.0 — 2026-09-25

### New
- **Voice input** 🎤 next to the message field: click, speak, click again —
  the text lands in the field so you can correct it before sending (Esc
  discards). Gemini 3.5 Transcribe with the same key as read-aloud; filler
  words and false starts are left out.
- **Edit and resend now really rewinds.** ✎ on one of your messages lets Cody
  continue from exactly that point, as if the old version and everything after
  it had never happened (the session branches with
  `--resume-session-at`). The original goes to the archive, so nothing is
  lost.

### Changed
- Read-aloud and voice input share one Gemini client (`server/gemini.py`).

## 5.0.0 — 2026-09-25

A rebuild of the interface and the server structure. Settings, sessions and
data carry over; nothing needs to be set up again. Update with `git pull` (or
just restart — CONSTRUCT updates itself on start).

### New
- **Plasma** (⚙ Settings → Color theme): panels become liquid glass over a
  living color field, rendered with WebGL, in the colors of any of the eight
  themes. Without a GPU the same layout falls back to a CSS glass look.
  Behind the glass: the animated plasma field, the Matrix rain, your own
  image (dimmed) or a plain background.
- **Fonts**: pick Share Tech Mono, JetBrains Mono, IBM Plex Mono, Space
  Grotesk, Exo 2 or Inter — bundled, no requests to Google.
- **Read aloud** with Gemini TTS: 🔊 on every reply, optional auto-read,
  voice per language (German and English catalog), style prompt.
- Settings navigation on the left jumps to each section.

### Changed
- **Interface rewritten in React 19 + TypeScript + Vite** (`frontend/`). The
  built files are committed in `static/app/`, so running CONSTRUCT still needs
  no Node.js. Every view has its own address (`/chat`, `/calendar`,
  `/mail/accounts` …); views other than the chat load on demand.
- Markdown, code highlighting and fonts are bundled instead of loaded from
  CDNs — CONSTRUCT works fully offline.
- **Server split into modules**: `app.py` only assembles the app; the logic
  lives in `server/` with one router per area. Startup uses FastAPI lifespan.
- Repository tidied: internal modules moved to `server/`, Linux helpers to
  `scripts/linux/`. The README starts with which file to run.

### Removed
- The one-line installers `install.sh` and `install.ps1` — clone the
  repository and run `./start.sh` (or `start.bat`).
- The CRT scanline overlay.

### Fixed
- Resuming a broken Hermes session could crash on a missing import.
- Many small fixes found while comparing the old and new interface
  (scrolling, mail compose, Microsoft login polling, diary links, …).

### Development
- CI on every push: type check, lint, format, tests and an up-to-date build
  check for the frontend; pyflakes and pytest for the backend.
- 81 frontend and 29 backend tests.
