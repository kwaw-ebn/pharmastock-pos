# Data model

Alembic's initial migration is the authoritative schema. PostgreSQL and SQLite share the same SQLAlchemy model definitions.

| Table | Purpose |
|---|---|
| users | Individual accounts, role, Argon2 hash, active state and token revocation version |
| suppliers | Supplier identity and contact details |
| products | Catalogue, sale unit, barcode, generic name, price and reorder threshold |
| stock_batches | Batch identity, expiry, manufacture date, recorded cost and current units |
| stock_receipts / stock_receipt_items | Delivery header and batch additions |
| inventory_movements | Append-only signed changes for opening stock, receipts, sales, adjustments and eligible returns |
| customers | Optional minimal customer identity |
| sales / sale_items | Immutable sale values, item names, batch costs, prices and quantities |
| returns | One controlled full-sale reversal, refund amount, reason and restocking choice |
| settings | Pharmacy and checkout settings |
| audit_logs | User, action, record, details and timestamp |
| password_resets | Hashed one-time reset token and expiry |

Roles and categories use constrained/string values rather than separate join tables. A payment is recorded on each sale; split payments are not currently supported. All amounts are integer minor currency units in storage. Public API prices use decimal major units. The supported currency configuration assumes two decimal places (including GHS).

Expiry dates are handled conservatively: batches dated today or earlier are excluded from normal sale. Products are sold in the configured unit; pack-to-tablet conversion is not automatic. Define a separate SKU when a different sale unit must be tracked.

Every stock mutation produces a movement in the same database transaction. A new delivery adds units rather than replacing a balance. A batch cannot become negative. Re-receiving an existing batch requires matching expiry and cost; use a separate batch reference when costs differ.

Product prices and pharmacy settings are copied into sale records, so historic receipts remain stable after changes. Sale records are never deleted by the application. Reversal records mark sales refunded and optionally create stock movements under admin control.

Business-date calculations and display timestamps use UTC / Africa/Accra for the Ghana pilot, independent of the application host's local timezone.
