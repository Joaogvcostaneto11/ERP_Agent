# Deploy ERP Chat to Render (free tier) — Design

**Date:** 2026-07-06
**Status:** Approved

## Goal

Make the ERP Agent **chat UI** reachable on the public web at a stable URL, for a
small private group to experiment with. Hosting must be free; a slow first
request (cold start) is acceptable.

## Scope

- **In scope:** Deploy `logic.chat.app:app` (read-only conversational query UI)
  to Render's free web-service tier, behind a shared-password gate.
- **Out of scope:** DevCare CRUD (writes) and `logic.main`. Only the chat UI
  goes live. No CI/CD beyond Render's auto-deploy-on-push.

## Constraints (why the choices below)

- The app uses **`pyodbc` + ODBC Driver 18**, a system-level dependency → the
  host must build from a **Dockerfile**. Rules out serverless (Vercel/Netlify).
- Every chat message calls the **Anthropic API** (metered) → the app must not be
  open to the public. Hence a password gate.
- The database is **Azure SQL**, already cloud-hosted and reachable from Render.
- Render **free tier has no static outbound IP** → to let Render reach Azure
  SQL, the Azure SQL firewall must allow all IPs (`0.0.0.0/0`). Acceptable
  because the `DATABASE_URL` login is **read-only** and password-protected;
  opening the firewall does not bypass authentication.

## Design

### Components (all new files except the one edit)

1. **`Dockerfile`** — `python:3.12-slim` base; install Microsoft ODBC Driver 18
   from the MS apt repo added with `[trusted=yes]` (Debian 12's `sqv` verifier
   rejects Microsoft's SHA-1-bound signing key after 2026-02-01, so the
   apt-layer signature check is bypassed; fetch is still HTTPS from Microsoft's
   host); `pip install -r requirements.lock`; `COPY . .`; run
   `uvicorn logic.chat.app:app --host 0.0.0.0 --port $PORT`.
   Render injects `$PORT`.

2. **`.dockerignore`** — exclude `.env`, `.venv`, `.git`, caches, and local
   `logs/*` so local secrets and bulk are never copied into the image.

3. **`render.yaml`** — Render Blueprint: one `web` service, `runtime: docker`,
   `plan: free`, `healthCheckPath: /healthz`, and the required env vars declared
   with `sync: false` (values entered in the dashboard, never in git).

4. **Password gate** — a `@app.middleware("http")` HTTP Basic Auth check added
   to `logic/chat/app.py`:
   - Reads `APP_PASSWORD` from the environment.
   - **If unset → no auth** (local dev is unchanged).
   - If set → every request needs `Authorization: Basic <base64(user:APP_PASSWORD)>`;
     the browser prompts once and remembers it. Password compared with
     `secrets.compare_digest`. Any username is accepted.
   - `/healthz` is exempt so Render's health check (which sends no credentials)
     succeeds; otherwise the deploy would be marked unhealthy.

5. **`/healthz`** — a tiny unauthenticated route returning `{"status": "ok"}`.

### Data flow (unchanged from local)

Browser → (Basic Auth gate) → FastAPI chat routes → `ChatService` → Anthropic
API + read-only Azure SQL. Chat history/audit are written to the container's
ephemeral `logs/` (wiped on redeploy; fine for an experiment, since history is
per-session).

### Env vars set in Render

| Var | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API (metered) |
| `DATABASE_URL` | Read-only Azure SQL login |
| `APP_PASSWORD` | Shared password for the gate |
| `CHAT_FEEDBACK_TOKEN` | Optional; enables the dev feedback panel |

## Verification

- **Config sanity:** the auth middleware is importable and returns 401 without
  credentials / passes with them (Python smoke test, no DB needed).
- **Real build:** Render's build log (Docker is not installed locally). A green
  build + a reachable URL that prompts for a password is the success signal.
- **DB reachability:** first real chat query returns data → confirms the Azure
  SQL firewall change worked.

## Risks / notes

- Free instance sleeps after ~15 min idle → ~50s first-request wake. Accepted.
- Opening the Azure SQL firewall to `0.0.0.0/0` widens exposure of the read-only
  login; mitigated by a strong password and read-only grants. Revisit if the app
  ever needs the writable `DEVCARE_WRITE_DATABASE_URL` online.
- If a future need arises for a static DB IP, upgrade to Render's paid tier.
