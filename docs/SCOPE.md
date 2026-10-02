# Pilot scope

This first implementation supports a single pharmacy with three roles and two-decimal currencies. It has functional database-backed workflows, but should be piloted and reviewed with pharmacy staff before operational use.

## Role permissions

| Action | Administrator | Pharmacist | Cashier |
|---|---|---|---|
| Search products and prices | Yes | Yes | Yes |
| Process ordinary sales | Yes | Yes | Yes |
| Verify prescription products | Yes, if professionally authorized | Yes | No |
| View/reprint sales | All | All | Own only |
| Apply discounts | Yes | Yes | No |
| Receive stock / inspect batches | Yes | Yes | No |
| Customer records and history | Yes | Yes | No |
| Edit products and suppliers | Yes | No | No |
| Adjust stock / refund completed sales | Yes | No | No |
| Financial reports / audit / users / settings | Yes | No | No |

Account role does not establish a professional qualification. Grant prescription access only to appropriately authorized staff.

## Explicit limitations

- Single branch, no purchase orders, supplier accounting, insurance claims or external accounting integrations.
- Full-sale manual-payment refunds only; gateway refunds require merchant-dashboard reconciliation. No partial item refunds.
- No SMS/WhatsApp notifications or offline transactions. Paystack supports hosted Card/Mobile Money payments; merchant credentials and onboarding are required.
- CSV exports and browser PDF printing; no native XLSX or server-generated PDF.
- Inventory and audit lists have display limits; inventory CSV exports are unpaginated for admin reporting.
- Currency assumes two decimal places. Product receiving/cost forms are labelled GHS for the intended Ghana pilot.
- No automatic package-unit conversions or barcode camera recognition; keyboard-emulating scanners are supported.
- A configurable warning window is available, plus 30/60/90-day batch filters. The per-product reorder threshold is authoritative.
- Local workflow tests are separate from a pharmacy security/privacy review and printer compatibility check.

The roadmap can add partial returns, supplier invoicing, shared rate limiting, branch isolation, native document exports and prescription record workflows after the pilot validates the core operations.
