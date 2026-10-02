# Deployment and operations

## Single-server deployment

Use Docker Compose with PostgreSQL. Put the frontend port behind an HTTPS reverse proxy such as Caddy or your organization's gateway. Set the pharmacy information, tax rate, currency, payment methods and expiry alerts before entering real stock. Do not expose the database or backend container directly to the internet.

Create your administrator using the interactive CLI. Add individual staff accounts through Users. Seed data only in a separate demonstration environment. Check medicine identifiers, sale units, batch costs, prescription settings and opening stock before a pilot.

## Render deployment option

The repository includes a Docker backend and a Vite frontend. Deployment has not been provisioned automatically.

1. Create a managed PostgreSQL database and a backend web service from this repository with root directory `backend`, Docker runtime and `/api/health` as its health endpoint.
2. Set `DATABASE_URL` to the managed database URL, `SECRET_KEY` to a generated random secret, and `CORS_ORIGINS` to the exact frontend HTTPS origin. Set `PORT` as required by the host; the Docker command reads it. Keep one API worker for the in-process login limiter.
3. The backend start command applies Alembic migrations and starts Uvicorn. Review deployment logs. For later migrations that can take time, run `alembic upgrade head` in a controlled pre-deploy job before rollout.
4. Create a frontend static site, root directory `frontend`, build command `npm ci && npm run build`, publish directory `dist`.
5. Set the frontend build variable `VITE_API_URL` to the backend HTTPS origin, without `/api` and without a trailing slash. Rebuild after changing it.
6. Configure a rewrite from `/*` to `/index.html` for client-side fallback. Configure appropriate security headers at the hosting layer, including a Content Security Policy whose `connect-src` permits the backend origin.
7. Through the backend service shell, run `python -m app.cli create-admin`. Sign in and verify one test stock receipt, sale, receipt and refund before entering real records.

When the frontend is built for a separate origin, use static hosting or change the Nginx `connect-src` to include that API origin. The default Nginx configuration is intended for the same-origin Compose setup.

## Email

Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, and optional `SMTP_USERNAME`/`SMTP_PASSWORD`. The implementation requires STARTTLS. Reset tokens expire after 30 minutes, can be used once and revoke previous sessions. Delivery failures are logged without including tokens or passwords. No token is returned by the reset-request API.

## Backups and restores

Take regular encrypted database backups and store them separately from the application host. For Compose:

```bash
docker compose exec -T db pg_dump -U pharmastock -d pharmastock > pharmastock-backup.sql
```

Restore only to the intended database in a controlled maintenance window, with application writes paused:

```bash
docker compose exec -T db psql -U pharmastock -d pharmastock < pharmastock-backup.sql
```

Test restores in an isolated environment. Back up before upgrades. Review retention and access with the pharmacy owner.

## Scale and integrations

All stock writers lock product rows in a deterministic order; checkout locks batches as well. PostgreSQL is required for multi-instance deployment. The login limiter is process-local: add a shared Redis limiter or gateway limiter before scaling beyond one process. Browser inactivity logout does not shorten the JWT's eight-hour maximum server expiry; logging out or disabling an account revokes existing tokens.

Payment recording has no external gateway integration. Refunds record the reversal and must be executed with the actual payment provider separately. CSV can be opened in Excel; native XLSX export is not included. PDF uses the browser print dialog.
