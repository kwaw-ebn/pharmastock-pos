# Deployment and operations

## Single-server deployment

Use Docker Compose with PostgreSQL. Put the frontend port behind an HTTPS reverse proxy such as Caddy or your organization's gateway. Set the pharmacy information, tax rate, currency, payment methods and expiry alerts before entering real stock. Do not expose the database or backend container directly to the internet.

Create your administrator using the interactive CLI. Add individual staff accounts through Users. Seed data only in a separate demonstration environment. Check medicine identifiers, sale units, batch costs, prescription settings and opening stock before a pilot.

## Render frontend/API and Neon database

`render.yaml` defines a free Render API in Frankfurt and a separate static frontend. Use a Neon PostgreSQL project in Frankfurt; copy its pooled connection string (TLS enabled) into the API's `DATABASE_URL`. Database migrations run before the API starts.

- API build: `pip install -r backend/requirements.txt`
- API start: `cd backend && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
- Frontend build: `cd frontend && npm ci && npm run build`; publish `frontend/dist`.
- `VITE_API_URL`: API HTTPS origin, without `/api`. Rebuild the frontend after changing it.
- API `SECRET_KEY`: random secret with at least 32 characters; `BOOTSTRAP_TOKEN`: a separate random setup token.
- API `CORS_ORIGINS` and `PAYMENT_CALLBACK_URL`: exact frontend HTTPS origin.
- API `REQUIRE_GATEWAY_PAYMENTS=true`: rejects staff-confirmed Card/Mobile Money records even before the gateway is configured.

Open the frontend and create the first administrator with `BOOTSTRAP_TOKEN` from the Render Environment page. Choose your own password; no default account exists. The setup endpoint becomes unavailable once any user exists. Remove the bootstrap variable afterward if desired. Configure pharmacy information and add staff and opening inventory. Production is initially empty; demonstration data is not installed.

Free API services may sleep when inactive. Consider an always-on plan when operational use requires predictable response times. Keep one API worker until the rate limiter is shared.

## Paystack Card and Mobile Money

Set `PAYSTACK_SECRET_KEY` only in the API's Render environment. Start with the merchant account's test secret. Hosted checkout collects payment details on Paystack; the pharmacy application does not collect card numbers. Set the merchant webhook URL to `https://<api-host>/api/payments/webhook`. Enable the appropriate Ghana payment channels in the merchant account, complete its onboarding, and replace the test key with a live secret before accepting real payments.

Digital checkout reserves stock and creates a pending sale. The pending-payments panel opens hosted checkout and can request verification after the customer returns. Signed webhooks also verify payment. The backend independently checks the reference, amount, currency and test/live environment. Success completes the existing reservation once; verified failure releases stock once. Closing a browser tab does not prove failure, so abandoned/unknown payments remain reserved for reconciliation. Late success after a failed reservation or expired stock is marked `paid_review`; do not dispense without resolving it.

Gateway refunds must be performed and reconciled through the merchant dashboard. The local refund endpoint blocks gateway sales to avoid recording an unexecuted refund. Partial refunds and automated gateway refund reconciliation are not included. Test a successful payment, failed payment, duplicate webhook and return-to-app verification with the merchant's test credentials before enabling live payments.

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

Manual cash refunds record the reversal. Paystack refunds require merchant-dashboard reconciliation. CSV can be opened in Excel; native XLSX export is not included. PDF uses the browser print dialog.
