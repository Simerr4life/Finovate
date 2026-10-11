# CSV bank-statement import

![Import upload](assets/screenshots/annotated/imports-upload-annotated.png)

## Purpose

Import real CSV statement rows into ordinary `Transaction` records after review. No fabricated amounts.

## Wizard

1. `/imports/upload/` — choose CSV (≤ 2MB)
2. `/imports/<id>/account/` — choose or create statement account
3. `/imports/<id>/preview/` — review detected columns/rows; select rows
4. Commit → status `committed`; transactions created with import source
5. History at `/imports/`; retry/delete available

## Technical notes

- Pipeline: `imports/pipeline.py` (+ enhanced CSV helpers when present)
- Model: `ImportBatch` stores raw file in `BinaryField`, column mapping, counters
- Unreadable files route toward manual setup guidance
- Only CSV is supported today

## Errors

| Condition | Behavior |
|---|---|
| File too large / invalid | Validation error; batch may be failed/discarded |
| Duplicate fingerprints | Skipped / not double-imported |
| Commit failure | Error message on batch; retry path |

See also existing deep dive: [bank-statement-import.md](../bank-statement-import.md).
