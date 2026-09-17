# Batch Attribute Item Pricing

Purva prices batched items by the batch's Batch Name, Batch Length in mm, and Sub Grade rather
than by one physical Batch No.

## Setup

Run the normal site migration after deploying the app:

```bash
bench --site <site-name> migrate
bench --site <site-name> clear-cache
```

The migration uses the existing `custom_batch_name`, `custom_batch_length_in_mm`, and
`custom_sub_grade` fields on Batch and preserves their field types and Link options. It creates
corresponding mandatory fields on Item Price and read-only fetched fields on Quotation Item,
Sales Order Item, Delivery Note Item, and Sales Invoice Item. Quotation Item and Sales Order Item
also receive a Batch No field.

## Price Selection

Create one Item Price for each distinct combination of:

- Item
- Price List, party, UOM, and validity dates
- Batch Name
- Batch Length in mm
- Sub Grade

Do not set the standard Batch No on Item Price. Purva blocks prices tied to one physical batch.

When a Batch No is selected in a sales row, Purva copies its three attributes to the row and
selects the exact matching Item Price. Saving is blocked if the batch has incomplete attributes,
belongs to another item, or has no matching Item Price.

Existing Item Price records must be backfilled with Batch Name, Batch Length in mm, and Sub Grade
before they are edited after this migration.
