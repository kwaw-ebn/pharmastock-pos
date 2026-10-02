# PharmaStock POS

A responsive pharmacy operations application built with React, TypeScript, FastAPI, SQLAlchemy and PostgreSQL. Staff can search medicines, record deliveries, complete sales, print receipts and monitor stock by batch and expiry.

## Included workflows

- Administrator, pharmacist and cashier access with Argon2 password hashing, revocable JWTs, login throttling and a 15-minute UI inactivity timeout.
- Product catalogue with barcode search, generic names, prescription flags, configurable prices and reorder thresholds.
- Stock receiving with multiple lines, supplier invoice references, batch costs and expiry dates.
- First Expiry, First Out allocation, expired-stock exclusion, atomic checkout and protection against concurrent overselling.
- Cash, Mobile Money and card payment recording. These record a payment confirmed by staff; they do **not** charge a provider or verify an external payment automatically.
- Unique receipts, 80mm-compatible receipt layout, browser printing, PDF through the browser print dialog and downloadable HTML receipts.
- Admin-approved full-sale refunds, optional eligible restocking and permanent inventory/audit records.
- Optional customers with protected purchase history; supplier delivery history; staff administration.
- Dashboard, date-filtered financial reports, recorded-cost gross profit estimate, sales by day/week/month/payment/staff/category, product performance, inventory and expiry CSV exports.
- Optional SMTP password reset. Without SMTP, users should ask the administrator for help.
- Alembic migrations, Docker Compose and CI checks, including PostgreSQL integration tests.

## Run with Docker (recommended)

Requirements: Docker with Compose.

1. Copy `.env.example` to `.env`.
2. Replace `SECRET_KEY` and `POSTGRES_PASSWORD` with independent random values. Generate each using:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Use a hex password for the Compose PostgreSQL URL. Never commit `.env`.
3. Start the application:
   ```bash
   docker compose up --build -d
   ```
4. Create the first administrator interactively:
   ```bash
   docker compose exec backend python -m app.cli create-admin
   ```
5. Open **http://localhost:8080** and sign in with the account you created. There are no built-in production credentials or public signup.
6. Optional: load fictional demo products into an empty catalogue:
   ```bash
   docker compose exec -e ALLOW_DEMO_SEED=true backend python -m app.cli seed-demo
   ```

The PostgreSQL data is stored in the `pgdata` volume. `docker compose down` retains it; `docker compose down -v` deletes it.

## Local development

Requirements: Python 3.12+, Node.js 24+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
```

Generate and replace `SECRET_KEY`. Load the `.env` values into your shell (Bash):

```bash
set -a
source .env
set +a
cd backend
alembic upgrade head
python -m app.cli create-admin
# Optional, on a demo database only:
ALLOW_DEMO_SEED=true python -m app.cli seed-demo
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to the backend. The local default is SQLite; use PostgreSQL for deployment. On Windows, activate the virtual environment with `.venv\Scripts\Activate.ps1` and set the environment variables in PowerShell, or use Docker Compose.

API documentation: http://localhost:8000/docs.

## Verification

```bash
cd backend
python -m pytest -q
cd ../frontend
npm ci
npm run build
```

Tests cover FEFO, expiry blocking, inventory rollback, concurrent checkout, idempotency, refunds, role boundaries, prescription verification, tax rounding, logout revocation and CSV formula escaping. CI also runs the tests against PostgreSQL. Use an isolated test database: the test fixture drops and recreates the application tables.

## Structure

```text
backend/app/       API, schemas, models, security and admin commands
backend/migrations/ Versioned schema migrations
backend/tests/     Workflow integration tests
frontend/src/      Responsive React/TypeScript interface
frontend/nginx.conf Same-origin production proxy
Docker Compose     PostgreSQL, backend and frontend
```

See [deployment instructions](docs/DEPLOYMENT.md), [data model](docs/DATA_MODEL.md) and [operational scope](docs/SCOPE.md).

This application manages operations. It does not diagnose patients or recommend medicines or dosages. Professional prescription checks and the pharmacy's return policy remain the responsibility of authorized staff.
