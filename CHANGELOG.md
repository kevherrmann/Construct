# Changelog

All notable changes to CONSTRUCT. Versions follow [semantic versioning](https://semver.org).

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
