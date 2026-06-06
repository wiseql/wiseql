-- WiseQL dev database: schema + seed data WITH PLANTED BUGS.
-- See KNOWN_BUGS.md for the catalogue. Deterministic — no random().
-- Runs as the APP_USER (wiseql) inside FREEPDB1.

ALTER SESSION SET CURRENT_SCHEMA = WISEQL;

--------------------------------------------------------------------
-- Schema
--------------------------------------------------------------------

CREATE TABLE customers (
    customer_id   NUMBER        PRIMARY KEY,
    full_name     VARCHAR2(100) NOT NULL,
    email         VARCHAR2(100),
    province      VARCHAR2(2)   NOT NULL
);

CREATE TABLE products (
    product_id    NUMBER        PRIMARY KEY,
    product_name  VARCHAR2(100) NOT NULL,
    category      VARCHAR2(50)  NOT NULL,
    price         NUMBER(10,2)  NOT NULL
);

-- NOTE: orders is intentionally a HEAP WITHOUT a primary key,
-- like a staging/load table — this allows planted duplicate rows (BUG-3).
CREATE TABLE orders (
    order_id      NUMBER        NOT NULL,
    customer_id   NUMBER,                      -- nullable on purpose (BUG-2)
    product_id    NUMBER        NOT NULL,
    store_id      NUMBER        NOT NULL,
    quantity      NUMBER        NOT NULL,
    order_date    DATE          NOT NULL,
    status        VARCHAR2(20)  DEFAULT 'COMPLETED' NOT NULL
);

CREATE TABLE returns (
    return_id     NUMBER        PRIMARY KEY,
    order_id      NUMBER        NOT NULL,      -- no FK on purpose (BUG-1)
    return_date   DATE          NOT NULL,
    reason        VARCHAR2(50)  NOT NULL,
    refund_amount NUMBER(10,2)  NOT NULL
);

--------------------------------------------------------------------
-- Reference data
--------------------------------------------------------------------

INSERT INTO customers VALUES (1, 'Aria Moradi',    'aria@example.com',   'BC');
INSERT INTO customers VALUES (2, 'Sam Chen',       'sam@example.com',    'ON');
INSERT INTO customers VALUES (3, 'Leila Karimi',   'leila@example.com',  'BC');
INSERT INTO customers VALUES (4, 'Noah Tremblay',  'noah@example.com',   'QC');
INSERT INTO customers VALUES (5, 'Maya Singh',     'maya@example.com',   'AB');

INSERT INTO products VALUES (101, 'Laptop Pro 14',   'Computers',   1899.99);
INSERT INTO products VALUES (102, 'Phone X2',        'Mobile',       999.00);
INSERT INTO products VALUES (103, 'Headphones Q',    'Audio',        349.50);
INSERT INTO products VALUES (104, 'Monitor 27"',     'Computers',    449.00);
INSERT INTO products VALUES (105, 'Smart Watch S',   'Wearables',    299.99);

--------------------------------------------------------------------
-- Orders: ~120 deterministic rows over May 2026
-- BUG-4: NO orders between 2026-05-15 and 2026-05-17 (date gap)
--------------------------------------------------------------------

BEGIN
  FOR i IN 1..120 LOOP
    INSERT INTO orders (order_id, customer_id, product_id, store_id, quantity, order_date, status)
    VALUES (
      1000 + i,
      MOD(i, 5) + 1,                               -- customers 1..5
      101 + MOD(i, 5),                             -- products 101..105
      CASE WHEN MOD(i, 7) = 0 THEN 217 ELSE 100 + MOD(i, 3) END,
      1 + MOD(i, 3),
      -- Dates: spread over May 1–28, but skip the 15th–17th (BUG-4)
      DATE '2026-05-01' + CASE
        WHEN MOD(i, 28) + 1 BETWEEN 15 AND 17 THEN MOD(i, 28) + 4
        ELSE MOD(i, 28)
      END,
      CASE WHEN MOD(i, 10) = 0 THEN 'SHIPPED' ELSE 'COMPLETED' END
    );
  END LOOP;
  COMMIT;
END;
/

--------------------------------------------------------------------
-- BUG-2: five orders with NULL customer_id
--------------------------------------------------------------------

BEGIN
  FOR i IN 1..5 LOOP
    INSERT INTO orders (order_id, customer_id, product_id, store_id, quantity, order_date, status)
    VALUES (1200 + i, NULL, 103, 102, 1, DATE '2026-05-20', 'COMPLETED');
  END LOOP;
  COMMIT;
END;
/

--------------------------------------------------------------------
-- BUG-3: two exact duplicate order rows (order 1042 appears 3x total)
--------------------------------------------------------------------

INSERT INTO orders SELECT * FROM orders WHERE order_id = 1042;
INSERT INTO orders SELECT * FROM orders WHERE order_id = 1042 AND ROWNUM = 1;
COMMIT;

--------------------------------------------------------------------
-- Returns: ~30 legitimate returns for existing orders
--------------------------------------------------------------------

BEGIN
  FOR i IN 1..30 LOOP
    INSERT INTO returns (return_id, order_id, return_date, reason, refund_amount)
    VALUES (
      5000 + i,
      1000 + (i * 4),                              -- every 4th order
      DATE '2026-05-05' + MOD(i, 20),
      CASE MOD(i, 3) WHEN 0 THEN 'DEFECTIVE' WHEN 1 THEN 'WRONG_ITEM' ELSE 'CHANGED_MIND' END,
      50 + (i * 10)
    );
  END LOOP;
  COMMIT;
END;
/

--------------------------------------------------------------------
-- BUG-1: three ORPHANED returns — order_ids that do not exist in orders
--------------------------------------------------------------------

INSERT INTO returns VALUES (5901, 9991, DATE '2026-05-22', 'DEFECTIVE',    120.00);
INSERT INTO returns VALUES (5902, 9992, DATE '2026-05-23', 'WRONG_ITEM',    85.50);
INSERT INTO returns VALUES (5903, 9993, DATE '2026-05-24', 'CHANGED_MIND', 240.00);
COMMIT;
