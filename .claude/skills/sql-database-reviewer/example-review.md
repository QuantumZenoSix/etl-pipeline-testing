# Example review

This illustrates the output format. The scenario is invented. A real review cites real files and evidence.

**Scenario:** reviewing `migrations/0042_add_order_status.sql` and `src/orders/repository.ts` in a PostgreSQL 15 project (the version comes from `docker-compose.yml`).

---

**Overall assessment:** The migration is correct on a small database but will block writes to `orders` on a large table, and one repository query has a race that can oversell inventory. Two issues should be fixed before deploying. No execution plans were available, so the performance findings are framed as risks.

**[HIGH] Inventory decrement is a read-then-write race**

- **Location:** `src/orders/repository.ts:88-97`, `reserveItem()`
- **Category:** transaction safety
- **Confidence:** high
- **Evidence:** The code runs `SELECT stock FROM products WHERE id = $1`, checks `stock > 0` in application code, then runs `UPDATE products SET stock = $2`, with no row lock and no conditional update.
- **Impact:** Two concurrent orders can both read `stock = 1` and both succeed, leaving the stock wrong (overselling).
- **Recommendation:** Use one atomic conditional update and check the affected-row count.
- **Example:**
  ```sql
  UPDATE products SET stock = stock - 1
  WHERE id = $1 AND stock > 0;
  -- 0 rows affected → out of stock
  ```
- **Validation:** A concurrency test with two parallel transactions reserving the last unit. Exactly one should succeed.

**[HIGH] Constraint added with a full validating scan while holding a blocking lock**

- **Location:** `migrations/0042_add_order_status.sql:3`
- **Category:** migration risk
- **Confidence:** medium. The table size is unknown, and the risk grows with the row count.
- **Evidence:** `ALTER TABLE orders ADD CONSTRAINT orders_status_chk CHECK (status IN (...));` validates every existing row while holding a lock that blocks writes.
- **Impact:** On a large `orders` table, writes stall for as long as the scan takes, and queued queries pile up behind the lock.
- **Recommendation:** Add the constraint as `NOT VALID`, then run `VALIDATE CONSTRAINT` in a separate step. Set `lock_timeout`.
- **Example:**
  ```sql
  SET lock_timeout = '5s';
  ALTER TABLE orders ADD CONSTRAINT orders_status_chk
    CHECK (status IN ('pending','paid','shipped','cancelled')) NOT VALID;
  -- separate migration or step:
  ALTER TABLE orders VALIDATE CONSTRAINT orders_status_chk;
  ```
- **Validation:** First run `SELECT count(*) FROM orders WHERE status NOT IN (...)` to confirm no existing rows violate the constraint. Then test the migration on a production-sized copy.

**[MEDIUM] Offset pagination on order history**

- **Location:** `src/orders/repository.ts:140`, `listOrders()`
- **Category:** performance
- **Confidence:** low. This is a risk, not a measured bottleneck.
- **Evidence:** `ORDER BY created_at DESC LIMIT $1 OFFSET $2`, where `created_at` isn't unique.
- **Impact:** Deep pages get slower as the offset grows, and rows with the same `created_at` can repeat or be skipped between pages.
- **Recommendation:** At minimum, add `id` as a tie-breaker. If deep pagination is a real use case, consider keyset pagination on `(created_at, id)`.
- **Validation:** Run `EXPLAIN ANALYZE` with a large offset on representative data.

**What looks good**
- All queries use bound parameters. No string interpolation was found.
- The FK from `order_items.order_id` has an index, which supports the cascade deletes.

**Recommended tests and diagnostics**
- A concurrency test for `reserveItem()`, described above.
- A constraint-violation pre-check query, and a migration rehearsal on a production-sized copy.
- `pg_stat_statements` data for `listOrders()` to decide whether keyset pagination is worth doing.

**Overall verdict: CHANGES REQUIRED.** The race condition and the blocking constraint validation should be fixed before deploying. The pagination concern is optional.

**Unverified:** No execution plans were run, and the production row counts for `orders` are unknown.
