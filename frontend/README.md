# Frontend Prototype (Static)

This folder currently contains a static HTML/CSS/JS prototype focused on side-by-side candidate claim comparisons.

Run it via Docker (recommended):
1. `docker compose up -d --build`
2. Seed example data: `docker compose run --rm api python -m app.scripts.seed_tx_us_senate_example`
3. Open: `http://localhost:3001`

Notes:
- This is a UI-development dataset and is not an endorsement.
- The UI calls the backend through the Nginx proxy at `/api/*`.
