Migrations are versioned Python steps in `kiza8/schema.py` (table `schema_version`). They run automatically at start and are additive (no drops).
Manual run: `python -m kiza8.schema`. Rollback: restore the DB backup taken before upgrading (SQLite file copy); new tables can be dropped safely because v7 code does not use them.
