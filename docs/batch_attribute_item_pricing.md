# Batch Attribute Item Pricing

Purva prices batched items by the batch's Make, Length, and Grade rather than by one physical
Batch No.

## Setup

Run the normal site migration after deploying the app:

```bash
bench --site <site-name> migrate
bench --site <site-name> clear-cache
```

The migration detects the existing Make, Length, and Grade fields on Batch and preserves their
field types and Link options. It creates corresponding mandatory fields on Item Price and
read-only fetched fields on Quotation Item, Sales Order Item, Delivery Note Item, and Sales
Invoice Item. Quotation Item and Sales Order Item also receive a Batch No field.

If the Batch fields do not exist on a fresh site, the migration creates `custom_batch_make`
(Data), `custom_batch_length` (Float), and `custom_batch_grade` (Data).

## Price Selection

Create one Item Price for each distinct combination of:

- Item
- Price List, party, UOM, and validity dates
- Batch Make
- Batch Length
- Batch Grade

Do not set the standard Batch No on Item Price. Purva blocks prices tied to one physical batch.

When a Batch No is selected in a sales row, Purva copies its three attributes to the row and
selects the exact matching Item Price. Saving is blocked if the batch has incomplete attributes,
belongs to another item, or has no matching Item Price.

Existing Item Price records must be backfilled with Make, Length, and Grade before they are
edited after this migration.
