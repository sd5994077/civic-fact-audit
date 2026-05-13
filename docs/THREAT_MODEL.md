# Threat Model

_Last updated: 2026-05-13. Scope: civic-fact-audit backend API and admin frontend._

---

## Trust Boundaries

| Boundary | Description |
|---|---|
| **Public internet → API** | Unauthenticated read-only endpoints (`GET /candidates`, `GET /compare`, `GET /compare/export`) |
| **Reviewer browser → API** | Authenticated reviewer/admin actions — JWT bearer token required |
| **Admin browser → API** | Admin-only actions — `require_admin` dependency enforced |
| **API → PostgreSQL** | Internal — credentials from environment variables, never from request data |
| **API → OpenAI** | Script-only; not used by the runtime API server |

---

## Authentication and Token Security

**Mechanism:** Custom HMAC-SHA256 signed tokens (not JWT library). Tokens are stateless; verification requires only the `AUTH_SECRET_KEY`.

| Property | Value |
|---|---|
| Algorithm | HMAC-SHA256, base64url payload + signature |
| Default TTL | 480 minutes (8 h) — tighten via `AUTH_TOKEN_TTL_MINUTES` |
| Dual-control TTL | 15 minutes (hard-coded) |
| Token type separation | `token_use` field prevents using dual-control tokens as bearer auth |
| Identity check on every request | `ReviewerUser.is_active` checked on each authenticated call |

**Risks and mitigations:**

- **No token revocation** — tokens are valid until expiry. If a reviewer account is deactivated, subsequent requests with an existing token will be rejected (active check on `ReviewerUser`). However a compromised token is live until it expires. Mitigation: short `AUTH_TOKEN_TTL_MINUTES` in production (recommend 60–120 minutes).
- **Secret key strength** — `AUTH_SECRET_KEY` defaults to `change-me-in-prod`. The startup validator raises `ValueError` if the default is present outside `development`. **Action required**: generate with `python -c "import secrets; print(secrets.token_hex(32))"` before deploying.
- **Brute-force protection on `POST /auth/login`** — the server enforces a 10 req/min per-IP sliding-window limit via `app/core/rate_limiter.py`. Responses include a `Retry-After` header. A 429 `rate_limit_exceeded` error is returned with `retry_after_seconds` in the details payload. A reverse-proxy limit (nginx `limit_req_zone`, Cloudflare, etc.) is still recommended as a defence-in-depth layer.

---

## Authorization

**Role model:** `admin` > `reviewer`. Every mutation endpoint uses `require_admin` or `require_reviewer_or_admin` FastAPI dependency.

**Auth guard audit (as of 2026-05-13): PASS** — all mutation endpoints (`POST`, `PATCH`, `DELETE`) are guarded. Intentionally public read endpoints:
- `GET /candidates` — public candidate list
- `GET /compare` — public fact-check comparison view
- `GET /compare/export` — public data export
- `GET /health`, `GET /version` — infrastructure probes

**Dual-control enforcement:**
- Candidate mutations, evaluation overwrites, and verification-source bulk attach require two distinct active reviewer/admin identities (approval token + applying token). Reviewer identity is resolved against the database on every dual-control operation — deactivated accounts cannot approve.

---

## Rate Limiting

All mutating write endpoints enforce per-IP sliding-window rate limits via `app/core/rate_limiter.SlidingWindowRateLimiter`. Limits are applied as FastAPI `Depends` on each route.

| Endpoint group | Limit | Window |
|---|---|---|
| `POST /auth/login` | 10 req | 60 s |
| `POST /auth/dual-control-approval-token` | 30 req | 60 s |
| `POST /claims/{id}/evaluate` | 120 req | 60 s |
| `POST /claims/{id}/publish` | 60 req | 60 s |
| `POST /claims/{id}/unpublish` | 60 req | 60 s |
| `POST /claims/sources/bulk` | 60 req | 60 s |
| `POST /claims/{id}/proposals` | 120 req | 60 s |
| `POST /claims/proposals/{id}/approve` | 60 req | 60 s |
| `POST /claims/proposals/{id}/reject` | 60 req | 60 s |
| `POST /claims/proposals/{id}/apply` | 60 req | 60 s |

**Response:** HTTP 429 with `Retry-After: N` header and body `{"error": {"code": "rate_limit_exceeded", "details": {"retry_after_seconds": N}}}`.

**Implementation note:** The limiter is in-process (single-instance). For multi-instance deployments, replace `SlidingWindowRateLimiter` backing store with Redis (the interface is isolated to `app/core/rate_limiter.py`).

---

## Input Validation

- All request bodies are validated via Pydantic v2 with strict field types and length limits.
- All ORM queries use SQLAlchemy parameterized queries — no raw string interpolation with user data.
- The one `text()` call in the codebase is the static `SELECT 1` health probe in `main.py`.
- Source URLs and publisher names are normalized before storage (strip, lowercase comparison keys).
- Partisan/advocacy source admission is enforced at the service layer for all source write paths (add, bulk attach, proposal apply).
- Moderation boundary phrase enforcement applies to rationale and citation notes in evaluations and proposals.

---

## Cross-Origin Resource Sharing (CORS)

`CORSMiddleware` is configured with an explicit allowlist from `CORS_ALLOWED_ORIGINS`. The startup validator raises `ValueError` if the default localhost list is present outside `development`.

| Environment | Default origins |
|---|---|
| `development` | `http://localhost:5500`, `http://127.0.0.1:5500` |
| non-development | **must be set explicitly** — startup fails otherwise |

Credentials (`Authorization` header) are allowed only from listed origins. Wildcard `*` is never used.

---

## Secrets Management

| Secret | Validated at startup | Stored |
|---|---|---|
| `AUTH_SECRET_KEY` | Yes (non-dev rejects default) | Environment variable |
| `POSTGRES_PASSWORD` | Yes (non-dev rejects default) | Environment variable |
| `REVIEWER_BOOTSTRAP_PASSWORD` | Yes (non-dev rejects default) | Environment variable; hash stored in DB via PBKDF2-SHA256 390 000 iterations |
| `CORS_ALLOWED_ORIGINS` | Yes (non-dev rejects default localhost list) | Environment variable |
| `OPENAI_API_KEY` | No (scripts only, not runtime) | Environment variable |

All secrets are loaded from `.env` via `pydantic-settings`. `.env` is listed in `.gitignore`. `.env.example` with safe placeholders is committed for deployer reference.

**Password hashing:** PBKDF2-SHA256 with 390 000 iterations and a random 16-byte salt per hash. Timing-safe comparison via `hmac.compare_digest`.

---

## Sensitive Data Exposure

- `POST /auth/login` returns an access token and reviewer role — no password hash is ever returned.
- `GET /version` returns `app_version` and `app_env`. Acceptable for infrastructure probes; no secrets exposed.
- `SQLAlchemyError` handler returns only the exception class name (e.g. `IntegrityError`), not the raw SQL or message.
- `AppError` details may include field names and error codes but never raw DB data.

---

## Operational Checklist (Before Production Deployment)

- [ ] Set `APP_ENV=production` (enables all startup validators)
- [ ] Generate `AUTH_SECRET_KEY` with `python -c "import secrets; print(secrets.token_hex(32))"`
- [ ] Set `POSTGRES_PASSWORD` to a strong random value
- [ ] Set `REVIEWER_BOOTSTRAP_PASSWORD` to a strong password; rotate immediately after first login
- [ ] Set `CORS_ALLOWED_ORIGINS` to the exact production frontend origin(s)
- [ ] Set `AUTH_TOKEN_TTL_MINUTES` to 60–120 for production
- [x] Application-level rate limiting applied to all write endpoints (built-in, no reverse-proxy config required)
- [ ] Optionally add defence-in-depth reverse-proxy rate limiting (nginx `limit_req_zone`, Cloudflare) for additional protection
- [ ] Confirm `.env` is not committed (check `.gitignore`)
- [ ] Rotate `AUTH_SECRET_KEY` if any reviewer credentials are believed compromised (invalidates all live tokens)
