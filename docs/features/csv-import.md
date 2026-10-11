# CSV import

**Last reviewed:** 2026-10-11

## 1. Feature overview

- **Purpose:** Bring bank CSV history into Finovate without inventing rows.
- **Intended users:** Signed-in users during or after onboarding
- **Permissions:** Authenticated user owning the data (unless noted)
- **Dependencies / prerequisites:** CSV ≤ 2MB; readable columns
- **Related:** See [feature inventory](../feature-inventory.md)



## 2. User interface walkthrough

Upload → account → preview → commit. ![Upload](assets/screenshots/raw/imports-upload.png)

## 3. Step-by-step workflow

See user-guide/imports.md wizard steps; cancel/delete batch; retry failed.

## 4. Business logic

Column detection, dedupe fingerprints, commit creates Transactions with source imported.

## 5. Technical implementation

`imports/views.py`, `pipeline.py`, `models.ImportBatch`.

## 6. Errors and edge cases

Unreadable → guidance/manual setup. Oversized file rejected. Commit errors stored on batch.

## 7. Testing and acceptance criteria

`imports/tests.py` pipeline + isolation coverage.
