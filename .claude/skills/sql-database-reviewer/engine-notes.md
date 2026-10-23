# Engine notes

These are reminders of behavior that often affects review conclusions. **Behavior varies by version and configuration.** Confirm the actual version and check the official docs before relying on any version-specific point in a finding.

## How to identify the engine

Look for: `docker-compose.yml` service images, connection URLs (`postgres://`, `mysql://`, `sqlserver://`, `sqlite:`), driver packages (`pg`, `psycopg`, `mysql2`, `PyMySQL`, `mssql`, `pyodbc`, `sqlite3`, `better-sqlite3`), ORM dialect config, migration tool config, and dialect hints in the SQL (`SERIAL`, `RETURNING`, backtick quoting, `AUTO_INCREMENT`, `TOP`, `NVARCHAR`).

## PostgreSQL

- **DDL is transactional**, so most migrations can roll back cleanly. Exceptions include `CREATE INDEX CONCURRENTLY`, which can't run inside a transaction block.
- **`CREATE INDEX CONCURRENTLY`** avoids blocking writes but is slower. If it fails, it leaves an `INVALID` index that has to be dropped.
- **Adding a column** with a constant default doesn't rewrite the table (version 11+). A volatile default, such as `random()` or `clock_timestamp()`, does rewrite it.
- **Changing a column's type** usually rewrites the table under an `ACCESS EXCLUSIVE` lock. Some changes, like increasing a `varchar` length, don't.
- **Constraints:** `ADD CONSTRAINT ... NOT VALID` followed by `VALIDATE CONSTRAINT` avoids a long blocking scan, for CHECK and FK constraints. `SET NOT NULL` scans the table, but on version 12+ it can skip the scan if a validated `CHECK (col IS NOT NULL)` already exists.
- **Lock queueing:** a DDL lock waiting behind a long transaction blocks every query queued after it. Recommend `SET lock_timeout` and `statement_timeout` for migrations.
- **FK columns are not indexed automatically** on the referencing side.
- **Plans:** `EXPLAIN` estimates only. `EXPLAIN (ANALYZE, BUFFERS)` **executes the statement**, so for writes wrap it in `BEGIN; ... ROLLBACK;`. Use `pg_stat_statements` for workload statistics and `pg_stat_user_indexes.idx_scan` for index usage.
- **Isolation:** the default is READ COMMITTED. Under REPEATABLE READ and SERIALIZABLE, the app must retry SQLSTATE `40001`. Deadlocks are `40P01`.
- **Indexes:** partial indexes, expression indexes, `INCLUDE` (version 11+), GIN/GiST for arrays, JSONB, and full-text search.
- **Uniqueness:** NULLs count as distinct by default. `NULLS NOT DISTINCT` is available on version 15+.
- **CTEs:** inlined since version 12 unless `MATERIALIZED` is specified. Before 12, they always acted as an optimization fence.
- **Upsert:** `INSERT ... ON CONFLICT (...) DO UPDATE/NOTHING`. `RETURNING` is available on writes.

## MySQL / MariaDB (InnoDB)

- **DDL is not transactional.** It causes an implicit commit, so a migration that fails partway leaves a partially changed schema.
- **Online DDL:** `ALGORITHM=INSTANT | INPLACE | COPY` and `LOCK=NONE | SHARED | EXCLUSIVE`. Specify them explicitly so the statement fails instead of silently falling back to a blocking copy. Instant `ADD COLUMN` is available from 8.0.12, in any column position from 8.0.29. Many type changes still need `COPY`. Large tables often use `gh-ost` or `pt-online-schema-change`.
- **FKs require an index** on the referencing column. InnoDB creates one if none exists.
- **Isolation:** the default is REPEATABLE READ, with next-key and gap locks, which can cause unexpected blocking and deadlocks on range writes and on inserts into gaps.
- **Plans:** `EXPLAIN` and `EXPLAIN FORMAT=JSON` estimate only. `EXPLAIN ANALYZE` (8.0.18+) **executes the query**. Use the slow query log and `performance_schema` or `sys.schema_unused_indexes` for usage data.
- **Invisible indexes** (8.0+) let you test the effect of dropping an index safely before actually dropping it.
- **No partial indexes.** Functional indexes are available from 8.0.13. Prefix indexes exist for long strings.
- **Character set:** `utf8` means `utf8mb3`, so use `utf8mb4`. The default collations are case-insensitive, which affects `UNIQUE` and `=` comparisons.
- **`ONLY_FULL_GROUP_BY`:** check whether it's enabled, because without it non-aggregated columns return arbitrary values.
- **Upsert:** `INSERT ... ON DUPLICATE KEY UPDATE` fires on *any* unique key, not just the one you meant. `UPDATE`/`DELETE ... LIMIT` is supported, which is useful for batching.
- **Unique indexes** allow multiple NULLs.

## SQL Server

- **Most DDL is transactional.**
- **Online index operations** (`WITH (ONLINE = ON)`) depend on the edition, generally Enterprise. Otherwise index builds block.
- **Adding a `NOT NULL` column with a default** is a metadata-only operation on Enterprise edition (2012+). Check the edition and version.
- **Isolation:** the default is READ COMMITTED with locking reads, unless `READ_COMMITTED_SNAPSHOT` is on. Watch for lock escalation on large writes, which happens around 5,000 locks.
- **Plans:** compare estimated and actual execution plans, and use `SET STATISTICS IO, TIME ON` and Query Store. **Parameter sniffing** is a common cause of parameter-sensitive plans.
- **Indexes:** filtered indexes, `INCLUDE` columns, columnstore. FKs are not indexed automatically.
- **Unique constraints** allow only **one** NULL. Use a filtered unique index to allow more.
- **`MERGE`** has known concurrency pitfalls. Prefer explicit `UPDATE` plus `INSERT` with appropriate locking hints, or at least use `HOLDLOCK`.
- **`OUTPUT`** captures rows affected by a write.

## SQLite

- **DDL is transactional.** There is a **single writer** at a time. WAL mode improves read and write concurrency.
- **Limited `ALTER TABLE`:** `ADD COLUMN`, `RENAME COLUMN` (3.25+), and `DROP COLUMN` (3.35+, with restrictions). Most other changes need the documented create-copy-drop-rename table rebuild.
- **Foreign keys are off by default.** `PRAGMA foreign_keys = ON` has to be set on each connection.
- **Dynamic typing (type affinity):** a column accepts values of other types unless the table is `STRICT` (3.37+).
- **Plans:** `EXPLAIN QUERY PLAN`.
- **Indexes:** partial and expression indexes are supported.
- **Upsert:** `INSERT ... ON CONFLICT ... DO UPDATE` (3.24+). `RETURNING` is available from 3.35.

## Other engines

For other engines, such as Oracle, CockroachDB, ClickHouse, or BigQuery, say that engine-specific behavior hasn't been checked against this reference, and qualify any recommendations about locking, DDL, and optimizer behavior.
