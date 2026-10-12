# Website (Next.js)

Reads the PostgreSQL database filled by `engine/` and shows fixtures, match analysis,
comparisons and model performance. It never calculates probabilities itself.

```bash
cp .env.example .env.local      # set DATABASE_URL (server-only)
npm install
npm run dev                      # http://localhost:3000
npm test && npm run lint && npm run typecheck
```

* `DATABASE_URL` is read only on the server (`lib/db.ts` is `server-only`); CI checks that
  no connection details end up in the browser bundle.
* Data is cached for one hour (`"use cache"` + `cacheLife("hours")`); the engine updates the
  database once a day.
* For local development without network access, `engine/devtools/seed_synthetic.py` fills a
  **local** database with clearly labelled synthetic data; the site then shows a warning banner.
