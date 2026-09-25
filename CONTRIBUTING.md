# Contributing to CONSTRUCT

Thanks for helping. This page is the short version of how the project is put
together and what a change needs before it goes in.

## Layout

| Where | What |
|---|---|
| `app.py` | Assembles the FastAPI app: middleware, static files, routers, start/stop |
| `server/` | Backend logic — `server/routes/` holds the HTTP API, one module per area |
| `frontend/` | The interface: React 19 + TypeScript + Vite ([conventions](frontend/README.md)) |
| `static/app/` | The **built** interface — committed on purpose, see below |
| `tests/` | Backend tests (pytest) |
| `desktop.py`, `start.sh`, `start.bat` | Native window and launchers |

## Getting started

```bash
git clone https://github.com/kevherrmann/Construct.git construct
cd construct
./start.sh                                # creates the venv, starts CONSTRUCT

# Backend checks
pip install -r requirements-dev.txt
python -m pyflakes app.py desktop.py cal.py selfupdate.py server tests
python -m pytest -q

# Frontend (needs Node.js 20+)
cd frontend
npm install
npm run dev      # http://localhost:5173, talks to CONSTRUCT on :8765
npm run check    # types, lint, format, tests, build
```

## Before you open a pull request

- **Run the checks above.** CI runs the same ones and must be green.
- **Commit the rebuilt `static/app/`** together with frontend changes. Users run
  CONSTRUCT without Node.js and update with `git pull`, so the built interface
  lives in the repository. CI fails if it is out of date.
- **Text in the interface:** German is the source language. Write `t('…')` and
  add the English version to `frontend/src/i18n/en.json`
  (`node scripts/add-en.mjs '{"Deutsch":"English"}'`). A test catches missing
  translations.
- **Colors only through theme variables** (`var(--green)`, …) so all eight
  themes and Plasma keep working.
- **User data stays out of git.** Settings, keys, mail accounts, calendar and
  uploads live in the project folder but are gitignored. Modules in `server/`
  find them through `BASE_DIR` (the project folder), which a test checks.
- **Comments explain why**, not what. Workarounds for WebKitGTK, pywebview or
  the reconnect logic keep their explanation.
- After updating frontend dependencies, refresh the notices:
  `cd frontend && npm run notices`.

## Reporting bugs

Open an issue with your OS, how you started CONSTRUCT (window or `--web`) and
what you expected. For interface problems, the browser console helps a lot:
start with `CODY_DEBUG=1 ./start.sh` and right-click → Inspect.
