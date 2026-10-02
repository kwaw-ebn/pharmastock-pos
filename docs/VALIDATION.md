# Validation record

Validated locally on 2 October 2026.

- 22 backend integration tests passed on SQLite, including FEFO, expiry exclusion, concurrent checkout, transaction rollback, refunds, role controls, password reset/revocation and Ghana business dates.
- TypeScript typecheck and Vite production build passed.
- Browser smoke test completed an admin login, product selection, checkout and receipt display, and opened every main navigation page without JavaScript errors.
- Desktop (1440 px) and mobile (390 px) layouts inspected; mobile document had no horizontal overflow.
- Python and npm dependency audits reported no known vulnerabilities in the checked package set.

PostgreSQL checks are configured in GitHub Actions. Local Docker and real thermal-printer checks were not performed in this environment. A passing software test does not verify external Mobile Money/card payments or professional dispensing decisions; Paystack integration tests mock provider responses; real merchant test/live transactions remain to be verified after credentials are configured.

Hosting/payment update: 28 backend tests passed and production frontend build passed. Tests cover first-admin setup, signed webhook verification, idempotency, amount/currency/environment mismatch, failure release and late-success review.
