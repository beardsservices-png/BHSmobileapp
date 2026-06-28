# Change Log — Training & Help Button (June 2026)

Short note documenting a small change to the BHS business app, for future
reference.

---

## What changed

Added a circular **question-mark "Help" button** to the top-right of the app
header. Tapping it opens Jazzlyn's **Training & Reference** app (a separate
web app) in a new tab. It appears on every page, on both mobile and desktop.

This is the in-app entry point to the training/reference material — the
equivalent of the little "?" help icon on big-tech apps.

---

## Where it lives

All in `frontend/src/App.jsx`:

1. **The link target** — a constant near the top of the file:
   ```js
   const TRAINING_URL = 'https://jazzytraining-production.up.railway.app'
   ```
   To change where the button points, edit this one line.

2. **The button** — an `<a>` in the top header `<nav>`, after the desktop nav
   links, with `ml-auto` so it floats to the right edge:
   ```jsx
   <a href={TRAINING_URL} target="_blank" rel="noopener noreferrer"
      className="ml-auto ... w-9 h-9 rounded-full text-blue-600 bg-blue-50 ...">
     {/* heroicons question-mark-circle svg */}
   </a>
   ```
   It sits inside the `print:hidden` nav, so it does not appear on printouts.

---

## Notes / gotchas

- The button styling uses the app's existing **blue** accent (`text-blue-600`,
  `bg-blue-50`) to match the rest of the header.
- The target is an **absolute URL** because the training app is a *separate*
  Railway deployment, not a route within this app.
- When this change was made, the working branch was **behind `main`** (it did
  not yet have the **Jazzlyn Pay** page or the SMS lead extractor). `main` was
  merged in first so those features were preserved, then the button was added
  on top. Lesson: `git fetch` and rebase/merge `origin/main` before adding new
  work.

---

## Tech stack reminders (this repo)
- **Frontend**: `frontend/` — React + Vite 6 + Tailwind CSS v4 (blue theme) +
  react-router-dom + recharts. Built to `frontend/dist`.
- **Backend**: `api/app.py` — Flask, **raw `sqlite3` (NEVER SQLAlchemy)**,
  DB at `data/beard_business.db` (`conn.row_factory = sqlite3.Row` + `dict(row)`).
- **Deployment**: Railway (Docker). The Dockerfile builds the React frontend and
  serves it statically from Flask via Gunicorn. **Deploys the `main` branch.**
  Health check: `GET /api/health`. See `CLAUDE.md` for the full picture.
- Pushing to `main` triggers an automatic rebuild + deploy.
