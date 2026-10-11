# CSV import workflow

1. Start: `/imports/upload/` or onboarding import
2. Upload CSV → `ImportBatch` draft with raw bytes
3. Choose/create `Account`
4. Preview mapped rows; deselect bad rows
5. Commit → transactions + counters; `committed_at`
6. Alternate: retry, delete (may keep committed txns while dropping file)
