# Review checklists

Use only the sections relevant to the scope. Each item is a prompt to investigate, not an automatic finding. Confirm it against the actual code, schema, and engine.

## 1. Query correctness

- [ ] Every join has the right condition, with no accidental Cartesian product, especially with comma joins or a missing `ON` term
- [ ] **Join cardinality:** a one-to-many join followed by `SUM` or `COUNT` multiplies rows. Aggregate in a subquery or CTE first, or use `EXISTS`
- [ ] `DISTINCT` used to hide a duplicate-producing join instead of fixing the join
- [ ] `WHERE` vs. `HAVING`: row filters belong in `WHERE`. `HAVING` is for aggregate conditions
- [ ] A filter on an outer-joined table placed in `WHERE` turns the `LEFT JOIN` into an inner join. Put it in `ON` if the outer join is intended
- [ ] `GROUP BY` covers the non-aggregated columns. MySQL without `ONLY_FULL_GROUP_BY` returns arbitrary values otherwise
- [ ] Window functions: correct `PARTITION BY`/`ORDER BY`, and the frame clause, since the default `RANGE` frame surprises people with ties
- [ ] **NULLs:** `col = NULL` is never true; `NOT IN (subquery)` returns no rows if the subquery contains a NULL, so prefer `NOT EXISTS`; `COUNT(col)` skips NULLs; NULL in arithmetic or concatenation propagates
- [ ] Implicit type conversions in comparisons, such as string vs. number or a timestamp vs. a date literal, which hurt both correctness and index use
- [ ] Empty-set behavior: an aggregate over zero rows returns NULL, not 0, and `MAX` over an empty set is NULL
- [ ] **Pagination:** `ORDER BY` is on a unique, deterministic key (add the PK as a tie-breaker). Large `OFFSET` values scan and discard rows, so consider keyset or seek pagination
- [ ] **N+1:** a query inside a loop over another query's results. Batch it with `IN`/`ANY`, a join, or the ORM's eager loading
- [ ] Selecting `*` or unneeded columns or rows, especially large text or blob columns
- [ ] Subqueries or CTEs that are redundant or recomputed. Check whether the engine materializes or inlines CTEs
- [ ] Dialect-specific syntax that matters if portability is a requirement

## 2. Performance

Without a plan, frame every item as a *risk*. With a plan, cite the specific node or operator.

- [ ] **Non-sargable predicates:** a function or cast on an indexed column (`WHERE DATE(created_at) = ...`, `LOWER(email) = ...`), arithmetic on a column, a leading-wildcard `LIKE '%x'`, or an `OR` across different columns
- [ ] Scans of large tables where a selective predicate could use an index
- [ ] Sorts or `GROUP BY` that an index matching the order could avoid
- [ ] Correlated subqueries that run once per outer row
- [ ] Repeated scans of the same table that could be combined into one
- [ ] Estimated vs. actual row counts far apart in the plan: stale statistics or a cardinality estimation problem
- [ ] Parameter-sensitive plans, where a plan cached for one parameter value is bad for skewed values (parameter sniffing)
- [ ] Spills to disk, temp tables, or large hash or sort memory use, if the plan shows them
- [ ] Too many round trips: unbatched inserts or updates, chatty ORM access
- [ ] **Diagnostics to recommend:** `EXPLAIN` or a plan at production-like data volumes, query statistics such as `pg_stat_statements`, the slow query log, or Query Store, and checking the table and index sizes

## 3. Indexes

- [ ] **Check the existing indexes first:** the migrations, schema dump, or catalog queries
- [ ] A missing index for an important, frequent, selective predicate, join key, or sort
- [ ] **Composite index column order:** equality columns first, then range or sort columns. The leftmost-prefix rule decides which queries can use the index
- [ ] Selectivity: an index on a low-cardinality column, like a boolean or status, often goes unused unless it's partial or filtered or part of a composite index
- [ ] Redundant indexes: `(a)` is redundant when `(a, b)` exists, in most engines. Also exact duplicates, and a unique index that duplicates the PK
- [ ] Write cost: every index slows inserts and updates and uses storage. Weigh this on write-heavy tables
- [ ] Covering indexes or `INCLUDE` columns for hot read paths, where the engine supports them
- [ ] Unique indexes that enforce business rules, which are integrity features, not just performance features
- [ ] Foreign keys: whether the referencing column needs an index depends on the engine and workload, for example deletes or updates on the parent and joins from the parent. Don't add one automatically
- [ ] Partial, filtered, or expression indexes where they fit, for example unique among non-deleted rows, or `LOWER(email)`
- [ ] **Build and drop cost:** locking during creation, whether online or concurrent builds are available, and the build time on large tables
- [ ] **Dropping "unused" indexes:** you need index usage statistics from production covering a representative period, a check that the index isn't backing a constraint, and a check for rare but important queries such as month-end reports. A code sample alone is never enough

## 4. Schema and data modeling

- [ ] Types fit the domain, with appropriate lengths and precision
- [ ] **Money:** use `DECIMAL`/`NUMERIC` or integer minor units, never `FLOAT`/`REAL`/`DOUBLE`
- [ ] **Time:** timezone-aware timestamps, or UTC stored by convention, used consistently. Know the difference between a date and a timestamp
- [ ] Nullability matches the domain. NULL means unknown, which is different from empty or zero
- [ ] A primary key on every table. Natural vs. surrogate keys chosen deliberately
- [ ] Foreign keys present, with deliberate `ON DELETE`/`ON UPDATE` behavior, especially `CASCADE` on important parents
- [ ] `UNIQUE` and `CHECK` constraints for invariants such as allowed status values or `quantity >= 0`
- [ ] Defaults that make sense, and no misleading defaults such as `0` for "unknown"
- [ ] Normalization: duplicated facts that can drift. Denormalization is acceptable when justified and kept in sync
- [ ] Junction tables with a composite PK or unique constraint on the pair
- [ ] Collation, encoding, and case sensitivity: they affect uniqueness and comparisons. MySQL `utf8` is 3-byte, so use `utf8mb4`
- [ ] Unbounded text in indexed columns, which can hit index key size limits
- [ ] Compatibility with existing data and the application code, and the expand-contract pattern for changes that must coexist with old app versions

## 5. Transactions and concurrency

- [ ] Operations that must be all-or-nothing share one transaction
- [ ] Transactions are short. No network calls, file I/O, or user waits while locks are held
- [ ] Commit and rollback happen on every path, including exceptions. Check how the ORM or driver handles autocommit and implicit transactions
- [ ] **Read-then-write races:** "check if exists, then insert" or "read balance, then update" break under concurrency. Fix with a unique constraint plus conflict handling, an atomic `UPDATE ... SET x = x - 1 WHERE x >= 1`, `SELECT ... FOR UPDATE`, or a version column for optimistic locking
- [ ] Lost updates when two writers do read-modify-write
- [ ] Deadlocks from inconsistent lock ordering across code paths. Lock rows in a consistent order
- [ ] Is the isolation level right for the invariant? Know the engine's default and what anomalies it allows
- [ ] Retries for deadlocks, serialization failures, and transient errors, with bounded backoff, and **only for idempotent operations**
- [ ] DDL inside transactions: some engines commit implicitly (see engine-notes.md)

## 6. INSERT, UPDATE, DELETE, and other writes

- [ ] **`WHERE` present and narrow enough.** Watch for predicates that match more rows than intended, such as NULL comparisons, wrong operator precedence with `OR`, or an empty-list `IN` handled by the ORM
- [ ] Multi-table `UPDATE`/`DELETE` join conditions are correct, so rows aren't touched more than once or by mistake
- [ ] Duplicate inserts: idempotency keys, unique constraints, `ON CONFLICT`/`ON DUPLICATE KEY`/`MERGE`
- [ ] **Upsert semantics:** which columns get overwritten on conflict, which values are kept, and whether a stale write can clobber newer data
- [ ] Cascading deletes and updates, and triggers with side effects
- [ ] Bulk operations: batch size, lock escalation, transaction log or WAL growth, replication lag
- [ ] The application checks the affected-row count when it matters, for example for optimistic locking or "exactly one row"
- [ ] Partial failure across several statements or tables
- [ ] **Recovery plan for destructive changes:** a backup or snapshot, a soft delete, an audit table, or `RETURNING`/`OUTPUT` to capture changed rows
- [ ] **Safeguards to recommend:** run a `SELECT COUNT(*)` with the same predicate first, wrap in a transaction and check the count before committing, use batched deletes with limits, and test on representative data

## 7. Migrations and schema changes

- [ ] **Data loss:** dropped columns or tables, narrowing types, truncation, lossy casts
- [ ] Adding `NOT NULL` to a populated table: needs a default or backfill first, and check the engine's rewrite and lock behavior
- [ ] New `UNIQUE`/`CHECK`/`FK` constraints that existing rows may violate. Run a violation query first, and consider adding the constraint unvalidated and then validating it
- [ ] **Locking:** table rewrites, blocking index builds, and a lock queued behind long transactions that then blocks all traffic. Set lock and statement timeouts
- [ ] Duration at production row counts, transaction size, replication lag
- [ ] **Rolling-deploy compatibility:** do the old and new app versions both work during the deploy? Renames and drops need coordinated phases
- [ ] **Expand → migrate → transition → contract:**
  1. **Expand:** add new columns or tables, nullable or defaulted, so old code is unaffected
  2. **Migrate:** backfill in resumable, batched, idempotent chunks
  3. **Transition:** deploy app code that uses the new schema, and verify it
  4. **Contract:** drop the old elements in a later release, once nothing reads them
- [ ] Large backfills are batched, throttled, resumable, and outside the DDL transaction
- [ ] Ordering and dependencies, plus assumptions about the previous schema version
- [ ] Rerun safety and interrupted runs: `IF [NOT] EXISTS`, and what state a partial failure leaves behind
- [ ] **Rollback:** is there a down migration, and would running it lose data? Some changes are only forward-fixable. Say so
- [ ] Compatibility with the actual engine and version

## 8. Data integrity

- [ ] Uniqueness is enforced in the DB, not only in the app, wherever concurrent writers exist
- [ ] Orphan risk: missing FKs, or cascade gaps
- [ ] Inconsistent representations, such as mixed case, whitespace, or `''` vs. `NULL`
- [ ] Precision and rounding: where rounding happens, and whether it happens consistently
- [ ] Timezone and date-boundary errors in range filters. Prefer half-open ranges, `>= start AND < end`
- [ ] Related tables updated together inside one transaction
- [ ] Don't assume generated IDs or sequences are gapless or ordered by commit time
- [ ] Soft delete vs. uniqueness, for example a deleted user blocking reuse of an email address. A partial unique index on non-deleted rows fixes this
- [ ] For each invariant, say whether it is a **DB-enforced guarantee** or an **application-level assumption**

## 9. Security

- [ ] **Injection:** user input concatenated or interpolated into SQL, or ORM "raw" escape hatches with interpolation
- [ ] Dynamic identifiers (table, column, sort direction) need an allowlist, because parameters can't bind identifiers
- [ ] Stored procedures that run dynamic SQL with input
- [ ] Least privilege: the app user shouldn't own the schema or have superuser rights. Migrations should use a separate role where possible
- [ ] Hardcoded credentials in SQL, scripts, migrations, or seed files. Report the location, **never the value**
- [ ] Sensitive data in query logs, error messages, or `SELECT *` responses
- [ ] **Multi-tenant:** every query on tenant data filters by tenant or owner, including joins and subqueries. Check for row-level security where it's used
- [ ] Authorization checks before sensitive writes
