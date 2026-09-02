# Reckoner — frontend

Next.js 16 app. Talks to the backend at `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

```bash
pnpm install
pnpm dev          # http://localhost:3000
pnpm typecheck && pnpm lint
pnpm test:e2e     # Playwright; starts the backend (backend/.venv) and the frontend itself
```

Styling is a deliberate placeholder (see `docs/DECISIONS.md`, ADR-005).
