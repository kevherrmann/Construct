# Changelog

All notable changes to CONSTRUCT. Versions follow [semantic versioning](https://semver.org).

## 6.2.0 — 2026-10-04

### Added
- **A persona for local models only.** Under ⚙ Settings → Character a third
  tab "Local models" appears once Bonsai or Ollama is set up. Whatever you
  write there replaces the persona for those models only; Cody on Claude and
  the cloud models through Hermes keep theirs. Empty means the same persona
  as Cody. Hermes has a single SOUL.md, so runs that need different personas
  take turns writing it (a lock held until Hermes has read it); tested with a
  Bonsai and a Gemini run started at the same moment.

### Fixed
- **Replies no longer appear twice.** Streamed text is drawn on the next
  animation frame; an immediate redraw (stats, done) did not cancel that
  pending frame, so it fired after the run had finished and wrote the reply
  back into the live run — it stood twice until the next message. Showed up
  when the last text and "done" arrived together and the browser draws frames
  late: Bonsai in the desktop app (WebKitGTK). Reproduced and verified there.

## 6.1.1 — 2026-10-04

### Fixed
- **Bonsai: the second message no longer goes to Google.** Hermes stores a
  Bonsai session only as the anonymous provider `custom` and cannot resolve
  it when the session is continued; its automatic fallback then picked Gemini
  (whose key CONSTRUCT passes on), and the reply was "Please pass a valid API
  key". Bonsai runs now set `CUSTOM_BASE_URL` to the local server, and a
  session that already stored the wrong address is repaired on its next
  message.
- **Small local models answer instead of repeating the context.** Bonsai
  often echoed the calendar and image instructions CONSTRUCT attaches to each
  message, especially after short requests ("Say only: one"). For local models
  (Bonsai, Ollama) the context now comes before the message and without the
  image instructions; session titles still show the actual request.

## 6.1.0 — 2026-10-03

### Added
- **Image generation in the chat.** Ask Cody for an image and it shows up in
  the reply. Runs on fal.ai; key and model under ⚙ Settings → Image
  generation. Default is GPT Image 2: in a side-by-side test with hands, a
  fixed layout and German lettering it got everything right, where Flux 1.1
  Ultra centred the subject and misspelled the sign. Cody uses the new
  `bild.py`; images are kept in `uploads/` and can be copied into the project.
- **Automatic model choice, shadow mode (experimental).** For each new
  session a small model (Haiku) suggests which model would fit; nothing is
  switched, the suggestion is only logged to `auto_schatten.jsonl`.
  `scripts/auto_auswertung.py` compares it with what actually ran. Off by
  default and without a switch in the UI (`"auto": {"schatten": true}` in
  `settings.json`).

### Fixed
- **Images no longer push the end of a reply out of view.** The chat scrolls
  smoothly and images load late; if you were at the bottom, you stay there.

## 6.0.2 — 2026-10-03

### Fixed
- **No more endless flicker after background jobs.** If `claude` exited
  while background tasks were still open (on its own, after the 30-minute
  limit, or killed), the run ended without a final event. The UI took that
  for a dropped connection, reconnected every second and rebuilt the chat
  from scratch each time: messages appeared, vanished and reappeared until
  the app was closed. The stream now always ends with an explicit `closed`
  event, and a run that ends during the wait sends `nachlauf_ende`.

## 6.0.1 — 2026-10-03

### Added
- **Demo video and screenshots in the README**, recorded in a demo
  installation with made-up data (`docs/screenshots/`).

### Fixed
- **Switching views starts at the top.** The content area kept the chat's
  scroll position, so the calendar opened halfway down and cut off the
  current week.
- **Skill names are readable in the list.** Name and description shared the
  row equally, so short names shrank to "d…". The name now comes first.
- **A skill's YAML header shows as a code block.** Read as Markdown, the
  `---` line turned `description: …` into a huge heading.
- **"★ global (all projects)"** in the English skill list instead of the
  German label.

## 6.0.0 — 2026-10-02

### Changed
- **One look: the rounded glass design.** Borderless panels, glass cards and a
  calm gradient behind them are now the only design, in all eight color
  themes. The old boxy terminal look is gone, and so is the `plasma` setting.
  Inter is the default font; the font picker still offers the others.

### Removed
- **WebGL Plasma** (liquid glass and the moving plasma field). It was buggy
  on NVIDIA cards. A stored "plasma field" background becomes Matrix rain,
  which is what it already showed without WebGL. `@cruxgarden/plasma-ui` is
  no longer a dependency.

### Fixed
- **The calendar marks today and the selected day again.** The glass cards
  covered both; today now has a full accent-colored edge, the selected day a
  tint.

## 5.8.0 — 2026-10-02

### Added
- **Folder picker reaches subfolders.** Projects kept in collection folders
  (`company/clients/…`) are now selectable: a breadcrumb bar, search across
  all levels, "Use this folder", recently used folders and keyboard control.
  Projects (`.git`, `CLAUDE.md`, `package.json`, …) are not expanded;
  `node_modules`, `vendor` and the like stay hidden.
- The bar shows `clients › project` instead of just `project`.
- `/folder` finds subfolders too, as `clients/project` if needed.

## 5.7.1 — 2026-09-30

### Fixed
- **The effort switch has a readable icon.** 🎚 showed up on macOS as a grey
  box with a cross; it is 💪 now.
- **The top bar shows the right version.** 5.7.0 still said "build 5.6.0".

## 5.7.0 — 2026-09-30

### Added
- **Claude Sonnet 5.5** replaces Sonnet 5 in the model list. Opus 5 is gone
  too — the list now only has current models (Opus 5.5, Fable 5.1,
  Sonnet 5.5, Haiku 4.5). A stored choice of a removed model, and old chats
  continued from the sidebar, move on to its successor.
- **Effort switch 🎚** next to the model picker, plus `/effort`: how
  thoroughly Claude thinks (`--effort`, low … max). Defaults to **high** —
  without it, Opus 5.5 runs at medium. Telegram and scheduled tasks use high
  as well.
- **Automatic fallback model.** If the chosen model is overloaded or
  unavailable, the reply comes from the next one (Opus 5.5 → Sonnet 5.5 →
  Haiku 4.5, and so on); the next message tries the chosen model again. The
  stats line shows which model actually answered.
- **Claude in Chrome** is switched on for chat runs (`--chrome`).

### Changed
- **The self-update no longer gives up on any local change.** Before, a single
  edited program file skipped the update for good — a second development
  machine silently fell behind. Now local changes stay as they are and the
  update runs as long as it does not touch them; a local change that is
  already on GitHub in exactly the same form is dropped first. Only a
  *different* change to a file the update also changes still skips the update,
  and then nothing is touched.

## 5.6.0 — 2026-09-29

### Added
- **Time next to every message.** The name line above each message now shows
  when it was sent (e.g. `21:14`, on other days `28.09. 21:14`; hovering shows
  the full date). Older chats get their times from the Claude transcript or
  the Hermes database.

## 5.5.0 — 2026-09-29

### Changed
- **Images and PDFs no longer stay on disk forever.** Deleting a chat now also
  deletes its attachments from `uploads/`, unless another chat or the
  background image in the settings still uses them. Once a day, attachments
  older than 7 days that no chat mentions anymore are removed as well
  (Telegram files, uploads that were never sent).

## 5.4.3 — 2026-09-28

### Fixed
- **Pasting images copied in the browser works again.** "Copy image" also puts
  a bare `<img>` on the clipboard as `text/html`; since 5.4.1 that counted as
  text, so neither the image nor any text arrived. HTML now only counts as text
  if it contains visible text.
- **Links from the desktop window no longer slow the browser down.** A browser
  started from a link inherited `GDK_BACKEND=x11` from the window and ran over
  XWayland without the graphics card (even YouTube stuttered). Links now open
  with the window's own setting removed.
- **Read aloud: long texts and errors.** Gemini gets up to 5 minutes instead of
  2 (long texts took longer and ended in a silent server error). Timeouts and
  the free tier's daily quota now show a clear message, and the chat shows the
  error as text next to 🔊 for 10 seconds instead of a 3-second ⚠.

## 5.4.2 — 2026-09-28

### Fixed
- With Plasma on, the update card ("Checking tools") no longer ends up hidden
  in the bottom-left corner behind the interface. The glass style forced
  `position: relative` on every glass card and overrode the card's fixed
  position; it now only applies to cards that don't position themselves. The
  card also gets an opaque background under Plasma, so the chat no longer
  shows through its text.

## 5.4.0 — 2026-09-25

### Added
- **Paste images with Ctrl+V in the desktop window.** WebKitGTK does not pass
  copied images to the page, so `desktop.py` now reads them from the clipboard
  itself (copied images and copied image files alike). Text still pastes as
  text.
- **Rounded glass design without a graphics card.** Where liquid plasma cannot
  run (no WebGL2, or software rendering), the plasma switch is offered as
  "Rounded glass design": borderless sidebar, top bar and input over a calm,
  static gradient in the theme colors. The "Plasma field" background is only
  offered where WebGL really runs.

### Fixed
- **Flickering in the Linux window (NVIDIA + Wayland).** The router dropped
  `?fx=low` right after start, so the full WebGL plasma ran on the CPU and
  flickered, getting worse the longer CONSTRUCT ran. The low-effects mode is
  now read once at load. In that mode the glass surfaces also skip
  `backdrop-filter`.
- Select boxes were drawn white by WebKitGTK; they now follow the theme.

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
