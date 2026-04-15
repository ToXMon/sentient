# Sentient Architecture

## System Overview

```
                    ┌──────────────────┐
                    │   User's Browser  │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  sentient.fyi     │
                    │  (Landing Page)   │
                    │  Static HTML/JS   │
                    └────────┬─────────┘
                             │ POST /api/waitlist
                             │
                    ┌────────▼─────────┐
                    │  here.now Proxy   │
                    │  Reverse Proxy    │
                    │  TLS Termination  │
                    └────────┬─────────┘
                             │ HTTP (internal)
                             │
              ┌──────────────▼──────────────┐
              │    Akash Network Container   │
              │  ┌────────────────────────┐  │
              │  │  FastAPI (uvicorn)      │  │
              │  │  :8000                  │  │
              │  │                         │  │
              │  │  ┌───────────────────┐  │  │
              │  │  │  Rate Limiter     │  │  │
              │  │  │  (SlowAPI)        │  │  │
              │  │  └───────┬───────────┘  │  │
              │  │          │               │  │
              │  │  ┌───────▼───────────┐  │  │
              │  │  │  Router Layer     │  │  │
              │  │  │  /api/waitlist    │  │  │
              │  │  │  /api/admin/*     │  │  │
              │  │  └───────┬───────────┘  │  │
              │  │          │               │  │
              │  │  ┌───────▼───────────┐  │  │
              │  │  │  Validation       │  │  │
              │  │  │  - Email regex    │  │  │
              │  │  │  - MX record chk  │  │  │
              │  │  │  - XSS sanitize   │  │  │
              │  │  └───────┬───────────┘  │  │
              │  │          │               │  │
              │  │  ┌───────▼───────────┐  │  │
              │  │  │  SQLAlchemy 2.0   │  │  │
              │  │  │  (async + aiosqlite)│  │
              │  │  └───────┬───────────┘  │  │
              │  └──────────┼──────────────┘  │
              │             │                 │
              │  ┌──────────▼──────────────┐  │
              │  │  SQLite Database        │  │
              │  │  /data/waitlist.db      │  │
              │  │  (Persistent Volume)    │  │
              │  └─────────────────────────┘  │
              └──────────────────────────────┘
```

## Data Flow

### Waitlist Signup

1. User submits email on the landing page at `sentient.fyi`
2. JavaScript sends `POST /api/waitlist` with `{email, name?, referral_source?}`
3. here.now receives the request over TLS, proxies to the Akash container
4. FastAPI rate limiter checks the IP (10 req/min)
5. Router validates email syntax and MX records via `dnspython`
6. Sanitizes all text fields against XSS (HTML escaping, dangerous tag removal)
7. Checks for duplicate email in the database
8. Hashes the client IP with SHA256 + salt (never stores plaintext IP)
9. Assigns the next sequential queue position
10. Persists the entry to SQLite on the persistent volume
11. Returns `{success, message, queue_position, is_duplicate}`

### Queue Position Lookup

Users can check their position without exposing their email:

1. Client computes `SHA256(email.strip().lower())`
2. Sends `GET /api/waitlist/position/{email_hash}`
3. API performs an O(1) indexed lookup on the `email_hash` column
4. Returns position and signup date, or "not found"

This design means the API never receives the plaintext email for lookups. The hash is computed client-side.

### Admin Operations

All `/api/admin/*` endpoints require the `X-API-Key` header. The key is set via the `ADMIN_API_KEY` environment variable at deploy time. Without it, the endpoint returns 503.

- **List signups**: Paginated with `limit` (max 1000) and `offset` parameters
- **Export CSV**: Streams all entries as a CSV download
- **Delete signup**: Removes by ID (does not reassign queue positions)

## Security Architecture

### On-Device Privacy Model

IP addresses never touch the database as plaintext. The `hash_ip()` function combines the IP with a configurable salt (`IP_HASH_SALT` env var) before SHA256 hashing. This makes the hash irreversible without the salt, which is injected at deploy time and never stored in the database.

Email hashes for position lookups use plain SHA256 without salt (so clients can compute them independently). The actual email addresses are stored for waitlist management but never exposed through public endpoints.

### CORS Lockdown

Production allows exactly three origins:

- `https://sentient.fyi`
- `https://www.sentient.fyi`
- `https://here.now`

Dev mode (`ENABLE_DEV_CORS=true`) adds `localhost:3000` and `localhost:8000`. Only `GET`, `POST`, and `OPTIONS` methods pass. Only `Content-Type` and `X-API-Key` headers are accepted.

### Rate Limiting

SlowAPI enforces per-IP limits:

| Endpoint | Limit |
|----------|-------|
| Public (default) | 10 req/min/IP |
| Admin list | 30 req/min/IP |
| Admin export | 10 req/min/IP |
| Admin delete | 20 req/min/IP |

Rate limit headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`) are included in responses.

### Additional Security Layers

- **Request size cap**: 1MB max. Requests exceeding this get 413.
- **Security headers**: Every response includes `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, CSP (`default-src 'none'`), HSTS (63072000s with preload), `Referrer-Policy`, and `Permissions-Policy` disabling camera, mic, geolocation, USB, payment, and sensors.
- **Server identification removed**: `Server: sentient-api` replaces default uvicorn headers.
- **No stack traces**: The global exception handler catches all unhandled errors and returns `{"error": "Internal server error"}` with a 500 status. Stack traces go to logs only.
- **Swagger/ReDoc disabled**: API documentation endpoints return 404 unless `ENABLE_DOCS=true` is set.
- **Non-root container**: The Docker image creates a `sentient` user. The process never runs as root.
- **tini as PID 1**: Proper signal handling and zombie reaping inside the container.

## Deployment Topology

```
┌──────────────────────────────────────────────┐
│              Production Setup                │
│                                              │
│  sentient.fyi (DNS)                          │
│       │                                      │
│       ├──► Landing Page (static hosting)     │
│       │                                      │
│       └──► here.now Proxy                    │
│              │                               │
│              └──► Akash Container            │
│                   (0.5 CPU, 512Mi RAM)       │
│                   (1Gi ephemeral + 2Gi       │
│                    persistent storage)        │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│              Local Development               │
│                                              │
│  localhost:3000 ─► nginx (landing page)      │
│  localhost:8000 ─► FastAPI (api)              │
│                   SQLite at ./data/           │
└──────────────────────────────────────────────┘
```

### Akash SDL Configuration

The `deploy.yaml` specifies:
- **Compute**: 0.5 CPU units, 512Mi RAM
- **Storage**: 1Gi default + 2Gi persistent (class `beta2`)
- **Persistence**: The `api-data` volume mounts at `/data` and survives container restarts and redeployments
- **Exposure**: Port 8000 exposed as port 80 to the global Akash network
- **Pricing**: 1000 uact per block

### CI/CD Pipeline

GitHub Actions (`.github/workflows/ci.yml`) runs on every push to `main` that touches `api/**`:

1. **Lint job**: `ruff check` and `ruff format --check` on `api/app/`
2. **Build job**: Multi-stage Docker build from `api/Dockerfile`
3. **Push to GHCR**: `ghcr.io/toxmon/sentient-api:latest` and `ghcr.io/toxmon/sentient-api:{sha}`

Pull requests trigger lint only (no image push).

## Scaling Considerations

### Current Constraints

SQLite handles concurrent reads well but locks on writes. With a single writer at a time, this works for a waitlist API receiving dozens to low hundreds of signups per minute. The persistent volume on Akash ensures data survives container restarts.

### Growth Path

When write throughput becomes a bottleneck:

1. **WAL mode**: Enable SQLite's Write-Ahead Logging for better concurrent read/write performance (no code changes, just a pragma)
2. **Connection pooling**: Tune SQLAlchemy's pool size for the Akash resource limits
3. **External database**: Swap `aiosqlite` for `asyncpg` (PostgreSQL) or move to a managed database service. The SQLAlchemy abstraction makes this a config change, not a rewrite.
4. **Horizontal scaling**: Add a second Akash deployment with a shared persistent volume or external database, load-balanced via here.now

### Resource Profile

The current Akash allocation (0.5 CPU, 512Mi RAM) handles roughly:
- 50 concurrent connections (uvicorn `limit-concurrency`)
- 10 requests/second sustained throughput
- ~100K stored entries before SQLite query patterns need indexing review

The `email_hash` and `email` columns are indexed. The `queue_position` column has a unique constraint for O(1) max-position lookups.
