# Dev Database — Planted Bugs

The seed data contains **deliberate data issues**. Every WiseQL demo recipe is
expected to catch them; they double as integration-test fixtures.

| ID | Bug | Where | Expected detection |
|---|---|---|---|
| BUG-1 | **3 orphaned returns** — `order_id` 9991/9992/9993 don't exist in `orders` | `returns` (return_id 5901–5903) | Anti-join step + `rows_max = 0` assertion fails, samples show the 3 rows |
| BUG-2 | **5 orders with NULL `customer_id`** | `orders` (order_id 1201–1205) | `no_nulls = ["customer_id"]` assertion fails |
| BUG-3 | **Duplicate order rows** — order 1042 appears 3× (exact duplicates; table has no PK, like a staging load) | `orders` | `unique = ["order_id"]` assertion fails |
| BUG-4 | **Date gap** — no orders between 2026-05-15 and 2026-05-17 | `orders.order_date` | Calendar/spine comparison step; row-count-per-day step shows the hole |

Also intentional (not bugs, but realistic mess):

- `returns.order_id` has **no foreign key** — orphans are possible by design (mirrors real staging schemas).
- `orders` has **no primary key** — exact duplicates are possible.
- Store 217 receives a disproportionate share of orders (`MOD(i,7)=0`) — useful for group-by demos.

## Quick verification queries

```sql
-- BUG-1
SELECT r.* FROM returns r LEFT JOIN orders o ON r.order_id = o.order_id WHERE o.order_id IS NULL;

-- BUG-2
SELECT * FROM orders WHERE customer_id IS NULL;

-- BUG-3
SELECT order_id, COUNT(*) FROM orders GROUP BY order_id HAVING COUNT(*) > 1;

-- BUG-4
SELECT TO_CHAR(order_date,'YYYY-MM-DD') d, COUNT(*) FROM orders GROUP BY order_date ORDER BY 1;
```
