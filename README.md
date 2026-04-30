# Insighta_IQ – Intelligence Query Engine
 
A demographic intelligence backend for **Insighta Labs** built with FastAPI + PostgreSQL.
 
---
 
## Stack
 
| Layer       | Tech                              |
|-------------|-----------------------------------|
| Framework   | FastAPI 0.115                     |
| Database    | PostgreSQL (SQLAlchemy 2 ORM)     |
| Migrations  | Alembic                           |
| Runtime     | Python 3.11+                      |
 
---
 
## Setup
 
### 1. Clone & install
 
```bash
cd stero_api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```
 
### 2. Configure environment
 
```bash
cp .env.example .env
# Edit DATABASE_URL to point to your PostgreSQL instance
```
 
### 3. Run migrations
 
```bash
alembic upgrade head
```
 
### 4. Seed the database
 
```bash
python scripts/seed.py --csv data/profiles.csv   # CSV format
# OR
python scripts/seed.py --json data/profiles.json  # JSON format
```
 
Re-running seed is **safe** — duplicates are skipped automatically via `ON CONFLICT DO NOTHING` on the `name` field.
 
### 5. Start the server
 
```bash
uvicorn main:app --reload
```
 
---
 
## API Reference

## Deployment Link
https://planned-silvie-afeh-052ca481.koyeb.app/
 
### `GET /api/profiles`
 
List profiles with filtering, sorting, and pagination.
 
**Query Parameters**
 
| Parameter               | Type   | Description                                      |
|-------------------------|--------|--------------------------------------------------|
| `gender`                | string | `male` or `female`                               |
| `age_group`             | string | `child`, `teenager`, `adult`, `senior`           |
| `country_id`            | string | ISO-2 code e.g. `NG`, `KE`, `AO`                |
| `min_age`               | int    | Minimum age (inclusive)                          |
| `max_age`               | int    | Maximum age (inclusive)                          |
| `min_gender_probability`| float  | Minimum gender confidence (0.0–1.0)              |
| `min_country_probability`| float | Minimum country confidence (0.0–1.0)             |
| `sort_by`               | string | `age`, `created_at`, `gender_probability`        |
| `order`                 | string | `asc` (default) or `desc`                        |
| `page`                  | int    | Page number (default: 1)                         |
| `limit`                 | int    | Results per page (default: 10, max: 50)          |
 
**Examples**
 
```
GET /api/profiles?gender=male&country_id=NG&min_age=25
GET /api/profiles?age_group=adult&sort_by=age&order=desc&page=2&limit=20
GET /api/profiles?min_gender_probability=0.9&min_country_probability=0.8
```
 
**Response**
 
```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 2026,
  "data": [ { ...profile... } ]
}
```
 
---
 
### `GET /api/profiles/search`
 
Natural language query — converted to filters by rule-based parser (no AI/LLMs).
 
**Query Parameters**
 
| Parameter | Type   | Description                              |
|-----------|--------|------------------------------------------|
| `q`       | string | Natural language query (required)        |
| `page`    | int    | Page number (default: 1)                 |
| `limit`   | int    | Results per page (default: 10, max: 50)  |
 
**Example queries**
 
| Query                              | Parsed as                                         |
|------------------------------------|---------------------------------------------------|
| `young males from nigeria`         | gender=male, min_age=16, max_age=24, country_id=NG |
| `females above 30`                 | gender=female, min_age=30                          |
| `people from angola`               | country_id=AO                                      |
| `adult males from kenya`           | gender=male, age_group=adult, country_id=KE        |
| `male and female teenagers above 17` | age_group=teenager, min_age=17                  |
| `senior women in egypt`            | gender=female, age_group=senior, country_id=EG     |
 
**Unrecognised query**
 
```json
{ "status": "error", "message": "Unable to interpret query" }
```
 
---
 
## Error Responses
 
All errors follow this shape:
 
```json
{ "status": "error", "message": "<description>" }
```
 
| Code | Meaning                              |
|------|--------------------------------------|
| 400  | Missing or empty parameter           |
| 422  | Invalid parameter type/value         |
| 404  | Profile not found                    |
| 500  | Server failure                       |
 
---
 
## Natural Language Parsing — How It Works
 
The parser (`app/services/nlp_parser.py`) is **purely rule-based**:
 
1. **Gender detection** — keyword matching (`male`, `men`, `boy`, `female`, `women`, `girl`).  
   `male and female` → no gender filter applied.
2. **Age modifiers** — regex patterns:
   - `"young"` → `min_age=16, max_age=24` (parsing alias only, not a stored group)
   - `"above 30"` / `"over 30"` / `"older than 30"` → `min_age=30`
   - `"below 18"` / `"under 18"` → `max_age=18`
3. **Age groups** — `child`, `teenager`/`teen`, `adult`, `senior`/`elderly`
4. **Country** — longest-match lookup against a 100+ entry dictionary mapping country names to ISO-2 codes. Prepositions (`from`, `in`, `of`) are stripped before matching.
---
 
## Database Schema
 
```
profiles
├── id                  VARCHAR(36)   UUID v7, primary key
├── name                VARCHAR        UNIQUE
├── gender              VARCHAR        "male" | "female"
├── gender_probability  FLOAT
├── age                 INTEGER
├── age_group           VARCHAR        child | teenager | adult | senior
├── country_id          VARCHAR(2)     ISO-2 code
├── country_name        VARCHAR
├── country_probability FLOAT
└── created_at          TIMESTAMPTZ   auto-generated (UTC)
```
 
Indexes on: `gender`, `age_group`, `country_id`, `age`, `created_at`.
 
---
 
## CORS
 
`Access-Control-Allow-Origin: *` is set globally.
 
---


## Authentication Flow

This project uses GitHub OAuth 2.0 with PKCE for authentication.

1. User visits `/auth/github` — backend generates a state token and PKCE 
   code_challenge, stores state in a secure HTTP-only cookie, and redirects 
   to GitHub's authorization page.
2. GitHub redirects back to `/auth/github/callback` with a one-time `code` 
   and the original `state`.
3. Backend validates the state, exchanges the code for a GitHub access token 
   (server-to-server), fetches the user's GitHub profile, and upserts the 
   user in the database.
4. Backend issues a short-lived JWT access token and a long-lived refresh 
   token. The frontend receives these and stores them as HTTP-only cookies 
   via the `/auth/session` endpoint.
5. All subsequent API requests are authenticated via the access token cookie 
   or Bearer header. The `/auth/refresh` endpoint rotates tokens when the 
   access token expires.

## Role Enforcement

Two roles exist: `admin` and `analyst`.

- **analyst** — default role assigned on first login. Can read profiles and 
  access `/api/profiles` and `/api/users/me`.
- **admin** — elevated role manually assigned in the database. Can access 
  all endpoints including user management.

Role is encoded in the JWT payload and enforced per-route via FastAPI 
dependencies (`require_admin`, `require_analyst_or_admin`).

## Interfaces

**Web Portal** — A browser-based dashboard deployed on Leapcell. Uses 
HTTP-only cookie authentication. Login is initiated by visiting 
`/auth/github` on the backend, which handles the full OAuth redirect flow.

**CLI** — A command-line tool that uses PKCE for secure OAuth without a 
client secret. The CLI generates a `code_verifier`/`code_challenge` pair, 
opens the browser for GitHub auth, captures the callback locally, and 
exchanges the code via `/auth/github/token` for JWT tokens stored locally.
 
## Timestamps
 
All `created_at` values are returned in **UTC ISO 8601** format.
 