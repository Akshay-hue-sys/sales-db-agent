"""Idempotent database bootstrap script matching physical database catalog."""
import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("[ERROR] DATABASE_URL is not configured in .env file.")
    sys.exit(1)

# Canonical DDL matching your PostgreSQL information_schema
DDL_SCRIPT = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE IF NOT EXISTS sales.customers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    signup_date DATE DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS sales.products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS sales.orders (
    id SERIAL PRIMARY KEY,
    customer_id INT REFERENCES sales.customers(id),
    product_id INT REFERENCES sales.products(id),
    quantity INT NOT NULL,
    total_amount NUMERIC(10, 2) NOT NULL,
    status TEXT NOT NULL,
    order_date DATE DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS sales.schema_docs (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(128) NOT NULL,
    column_name VARCHAR(128),
    description TEXT NOT NULL,
    embedding vector(384)
);
"""

# Defensive DML: seeds only if the respective relation contains 0 rows
SEED_DATA_SCRIPT = """
INSERT INTO sales.customers (id, name, region, signup_date)
SELECT * FROM (VALUES
    (1, 'Acme Corp', 'North America', '2024-01-15'::date),
    (2, 'Global Dynamics', 'Europe', '2024-02-20'::date),
    (3, 'Bharat Traders', 'Asia', '2024-03-10'::date)
) AS v(id, name, region, signup_date)
WHERE NOT EXISTS (SELECT 1 FROM sales.customers LIMIT 1);

INSERT INTO sales.products (id, name, category, unit_price)
SELECT * FROM (VALUES
    (1, 'Enterprise Cloud Suite', 'Software', 1200.00),
    (2, 'Hardware Security Key', 'Hardware', 50.00),
    (3, 'Dedicated Database Node', 'Infrastructure', 600.00)
) AS v(id, name, category, unit_price)
WHERE NOT EXISTS (SELECT 1 FROM sales.products LIMIT 1);

INSERT INTO sales.orders (id, customer_id, product_id, quantity, total_amount, status, order_date)
SELECT * FROM (VALUES
    (1, 1, 1, 1, 1200.00, 'delivered', '2024-04-01'::date),
    (2, 1, 2, 3, 150.00, 'delivered', '2024-04-05'::date),
    (3, 2, 3, 1, 600.00, 'delivered', '2024-04-12'::date),
    (4, 2, 2, 8, 401.05, 'delivered', '2024-04-15'::date)
) AS v(id, customer_id, product_id, quantity, total_amount, status, order_date)
WHERE NOT EXISTS (SELECT 1 FROM sales.orders LIMIT 1);
"""

def main() -> None:
    print("[*] Bootstrapping Sales Database...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            print("  -> Applying DDL Schema & Extensions...")
            cur.execute(DDL_SCRIPT)

            print("  -> Seeding Baseline Data...")
            cur.execute(SEED_DATA_SCRIPT)

        conn.close()
        print("[SUCCESS] Database bootstrap complete. Schema and seed records verified.")
    except Exception as exc:
        print(f"[FAIL] Database bootstrap failed: {exc}")
        sys.exit(1)

if __name__ == "__main__":
    main()