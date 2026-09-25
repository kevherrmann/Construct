# CONSTRUCT frontend

React 19 + TypeScript + Vite, served by the FastAPI backend. The build output
goes to `../static/app/` and **is committed** — users install and update
CONSTRUCT via `git pull` without Node.js.

```bash
npm install
npm run dev      # http://localhost:5173 — proxies /api to CONSTRUCT on :8765
npm run check    # typecheck, lint, format, tests, build — run before every commit
```

Point the dev server at another backend with `CONSTRUCT_BACKEND=http://127.0.0.1:8799 npm run dev`.

## Layout

```
src/
├── main.tsx              entry: i18n, theme, React Query, router
├── App.tsx               routes: /:view/*  (the backend serves index.html for each view path)
├── api/                  React Query hooks + response types, one file per backend area
├── components/           shared UI; components/layout/ = app shell (sidebar, topbar, HUD)
├── views/                one folder per menu entry; registry.tsx wires them into the menu
├── stores/               Zustand stores (client state: settings, conversations, …)
├── hooks/                reusable hooks
├── lib/                  framework-free helpers (api client, i18n, bootstrap data, themes)
├── i18n/en.json          English dictionary (keys are the German source texts)
└── styles/               global CSS: theme variables, base styles, shared keyframes
```

## Conventions

- **Server data → React Query** (`src/api/*.ts`), **client state → Zustand** (`src/stores/`).
  Never keep a copy of server data in a store by hand.
- **API calls** only through `apiGet` / `apiPost` from `lib/api.ts`; errors are `ApiError`
  carrying the server's `{"error": …}` message, ready to show to the user.
- **Styling:** one CSS Module per component (`Foo.module.css` next to `Foo.tsx`). Colors
  only through the theme variables (`var(--green)`, `rgba(var(--accent-rgb), .1)`, …) —
  never hard-code a theme color, or it sticks when the user switches themes. Shared
  keyframes (`blink`, `pulse`, `fade`) are global.
- **Text:** German is the source language. Write `t('Deutscher Text')`; add the English
  version to `src/i18n/en.json` (`node scripts/add-en.mjs '{"Deutsch":"English"}'`).
  Placeholders use single braces: `t('bis {t}', { t: time })`. A test fails when a
  `t('…')` literal has no English entry.
- **No `dangerouslySetInnerHTML`** except for sanitized Markdown/HTML (DOMPurify) and
  inline markup from the dictionary; prefer `<Trans>` for the latter.
- **Comments** explain *why*, in German, like the backend. Hard-won workarounds from the
  old interface (WebKitGTK quirks, reconnect logic, …) keep their explanation when ported.
- **Tests:** logic in `lib/`, `stores/` and `api/` gets Vitest tests next to the file
  (`foo.test.ts`). Components get tests where behavior is non-trivial.
