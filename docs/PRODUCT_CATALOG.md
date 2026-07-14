# Product catalog (Block V1-2)

CloserOS keeps a **tenant-scoped structured catalog** as the source of truth for
products, variants, prices, inventory, delivery facts, and commercial policy.

AI (DeepSeek / OpenAI-compatible) may **select product IDs** and draft language.
Deterministic application code owns all critical commercial facts.

## Entities

- `Product`, `ProductVariant`, `ProductPrice`, `InventoryLevel`, `DeliveryFact`
- `CatalogSource`, `CatalogImportRun`, `CatalogImportRowResult`
- `CommercialPolicy`, `CatalogFreshnessPolicy`

Money uses **integer minor units** only (no binary floats).

## Freshness

Default TTLs (tenant-configurable; never hard-coded into AI prompts):

| Fact | Default TTL |
|------|-------------|
| Inventory | 5 minutes |
| Price | 24 hours |
| Delivery | 12 hours |
| Promotion | 6 hours |
| Description | 90 days |

Usability:

- `live` — usable
- `verified` / recent `synced` — usable within TTL
- `stale` / `unverified` — must not be stated as confirmed to a customer

## CSV import

Flow: upload → parse/map/validate → preview → **explicit publish** → upsert → audit.

XLSX is **not** implemented. Port: `CatalogSpreadsheetParser`. Only CSV is shipped.

## AI tools

`search_products` arguments are validated; `tenant_id` supplied by the model is rejected.
Tenant is taken from authenticated application context only.

## Grounding

Before outbound draft creation, `validate_catalog_claim` verifies IDs, tenant,
active status, price/currency/stock, discounts, and tool-result inclusion.
Failures return a safe confirmation message and block inventing facts.

## Roles

- Mutate: `owner`, `sales_head`
- Read: owner, sales_head, manager, analyst, compliance_admin
- Managers do **not** change catalog facts in V1 unless a future policy grants it.
