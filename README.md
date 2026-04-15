# Sentient

> The AI that actually knows how you feel.

[![CI](https://github.com/ToXMon/sentient/actions/workflows/ci.yml/badge.svg)](https://github.com/ToXMon/sentient/actions/workflows/ci.yml)
[![GHCR](https://img.shields.io/badge/ghcr.io-toxmon%2Fsentient--api-blue)](https://github.com/ToXMon/sentient/pkgs/container/sentient-api)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## What It Does

Sentient is an emotionally intelligent AI companion. The landing page collects waitlist signups at sentient.fyi. The API validates emails, assigns queue positions, and stores data with privacy-first hashing. Built for deployment on Akash Network's decentralized cloud with here.now handling the reverse proxy layer.

## Architecture

```
Browser
  │
  ▼
sentient.fyi (Landing Page)
  │
  ▼
here.now Reverse Proxy (/api/*)
  │
  ▼
Akash Network (Docker Container)
  │
  ▼
FastAPI + SQLite (Persistent Volume)
```

The landing page sits at `sentient.fyi` and posts signups to `/api/waitlist`. here.now proxies those API calls to the Akash-deployed container. The API validates emails (syntax + MX records), hashes IPs with SHA256 + salt, assigns sequential queue positions, and persists to SQLite.

Admin endpoints (list signups, export CSV, delete entries) require an API key via the `X-API-Key` header.

## Quick Start

### Local Development

```bash
# Clone and run
git clone https://github.com/ToXMon/sentient.git
cd sentient
docker compose up --build

# API runs on http://localhost:8000
# Landing page on http://localhost:3000
```

### API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/waitlist` | None | Submit email to waitlist |
| GET | `/api/waitlist/count` | None | Get total signup count |
| GET | `/api/waitlist/position/{email_hash}` | None | Look up queue position by SHA256 hash |
| GET | `/api/health` | None | Health check (status, version, uptime) |
| GET | `/api/admin/waitlist` | API Key | List signups (paginated) |
| GET | `/api/admin/waitlist/export` | API Key | Export all signups as CSV |
| DELETE | `/api/admin/waitlist/{id}` | API Key | Delete a signup by ID |

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ADMIN_API_KEY` | Yes | — | API key for admin endpoints |
| `IP_HASH_SALT` | Yes | — | Salt for SHA256 IP hashing |
| `DB_DIR` | No | `/data` | Directory for SQLite database |
| `ENABLE_DEV_CORS` | No | `false` | Allow localhost CORS origins |
| `ENABLE_DOCS` | No | `false` | Enable Swagger/ReDoc endpoints |

## Deployment

### Akash Network (Decentralized Cloud)

1. Install the [Akash CLI](https://docs.akash.network/)
2. Set your secrets:
   ```bash
   export ADMIN_API_KEY="your-secure-key"
   export IP_HASH_SALT="your-random-salt"
   ```
3. Deploy:
   ```bash
   akash deployment create api/deploy.yaml
   ```
4. Update `api/.herenow/proxy.json` with the Akash endpoint URL

The SDL (`api/deploy.yaml`) requests 0.5 CPU, 512Mi RAM, 1Gi ephemeral + 2Gi persistent storage. The persistent volume survives container restarts.

### Docker

```bash
# Build
docker build -t sentient-api ./api

# Run
docker run -d \
  -p 8000:8000 \
  -e ADMIN_API_KEY=your-key \
  -e IP_HASH_SALT=your-salt \
  -v sentient-data:/data \
  sentient-api
```

### here.now Integration

`api/.herenow/proxy.json` defines the routing rules:

- `POST /api/waitlist` → Akash endpoint
- `GET /api/health` → Akash endpoint
- `GET /api/waitlist/count` → Akash endpoint

Replace `AKASH_ENDPOINT` with the deployed container URL after Akash deployment.

## Project Structure

```
sentient/
├── api/                          # FastAPI backend
│   ├── app/
│   │   ├── main.py               # App factory, middleware, CORS
│   │   ├── database.py           # Async SQLAlchemy + SQLite
│   │   ├── models.py             # WaitlistEntry model
│   │   ├── schemas.py            # Pydantic v2 request/response schemas
│   │   ├── routers/
│   │   │   ├── waitlist.py       # Public endpoints
│   │   │   └── admin.py          # API-key-protected endpoints
│   │   └── utils/
│   │       ├── security.py       # API key auth, IP hashing, XSS sanitization
│   │       └── validation.py     # Email regex + MX record checks
│   ├── Dockerfile                # Multi-stage Alpine build
│   ├── deploy.yaml               # Akash Network SDL
│   └── requirements.txt
├── landing/                      # Static landing page
│   └── index.html
├── docs/
│   ├── blueprint.md              # Product system blueprint
│   └── architecture.md           # Architecture deep-dive
├── .github/workflows/ci.yml     # Build, lint, push to GHCR
├── docker-compose.yml            # Local development
├── LICENSE
└── README.md
```

## Security

- **Non-root container**: Runs as `sentient` user, not root
- **CORS lockdown**: Only `sentient.fyi`, `www.sentient.fyi`, and `here.now` origins allowed in production
- **Rate limiting**: 10 requests/minute per IP (public), 20-30/minute (admin)
- **IP hashing**: Client IPs stored as SHA256 + salt, never plaintext
- **XSS prevention**: All user input sanitized with HTML escaping and dangerous tag removal
- **Security headers**: `X-Content-Type-Options`, `X-Frame-Options`, CSP, HSTS, `Referrer-Policy`, `Permissions-Policy`
- **Request size limit**: 1MB max body size
- **No stack trace leaks**: Global exception handler returns generic 500 responses
- **API key gating**: Admin endpoints require `X-API-Key` header
- **Docs disabled by default**: Swagger/ReDoc only exposed when `ENABLE_DOCS=true`

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI 0.110+ |
| Database | SQLite via async SQLAlchemy 2.0 + aiosqlite |
| Validation | Pydantic v2 with email support |
| Rate Limiting | SlowAPI |
| DNS Verification | dnspython (MX record checks) |
| Runtime | Uvicorn with tini as PID 1 |
| Container | Python 3.11 Alpine, multi-stage build |
| CI/CD | GitHub Actions → GHCR |
| Deployment | Akash Network (decentralized) |
| Proxy | here.now reverse proxy |
| Landing Page | Static HTML/CSS/JS |

## API Reference

### Submit to Waitlist

```bash
curl -X POST http://localhost:8000/api/waitlist \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "name": "Ada"}'
```

Response (201):
```json
{
  "success": true,
  "message": "You have been added to the waitlist!",
  "queue_position": 42,
  "is_duplicate": false
}
```

### Check Queue Position

```bash
# Hash the email first
EMAIL_HASH=$(echo -n "user@example.com" | sha256sum | cut -d' ' -f1)
curl http://localhost:8000/api/waitlist/position/$EMAIL_HASH
```

Response:
```json
{
  "found": true,
  "email_hash": "a3c0b...",
  "queue_position": 42,
  "signup_date": "2025-04-15T12:00:00Z",
  "message": "Position found"
}
```

### Get Signup Count

```bash
curl http://localhost:8000/api/waitlist/count
```

Response:
```json
{
  "total_signups": 150,
  "message": "There are 150 people on the waitlist"
}
```

### Admin: List Signups

```bash
curl http://localhost:8000/api/admin/waitlist?limit=10&offset=0 \
  -H "X-API-Key: your-api-key"
```

### Admin: Export CSV

```bash
curl http://localhost:8000/api/admin/waitlist/export \
  -H "X-API-Key: your-api-key" \
  -o waitlist.csv
```

### Admin: Delete Signup

```bash
curl -X DELETE http://localhost:8000/api/admin/waitlist/42 \
  -H "X-API-Key: your-api-key"
```

### Health Check

```bash
curl http://localhost:8000/api/health
```

Response:
```json
{
  "status": "healthy",
  "version": "1.1.0",
  "database": "connected",
  "uptime_seconds": 3600.42
}
```

## License

[MIT](LICENSE)
