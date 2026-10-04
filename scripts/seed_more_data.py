"""Seed expansion: Idempotently appends new analytical data across all sales tables."""

from sales_agent.db import get_conn


def seed_expansion():
    print("=== Expanding Sales Database with New Records ===")

    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1. Insert New Customers (Dimension Table)
            print("-> Inserting new customers...")
            cur.execute("""
                INSERT INTO sales.customers (id, name, region, signup_date)
                VALUES
                    (6, 'Nordic Logistics', 'Europe', '2024-03-15'),
                    (7, 'Apex Technologies', 'North America', '2024-04-01'),
                    (8, 'Kolkata Steel Works', 'Asia', '2024-04-10'),
                    (9, 'Sydney Retail Group', 'Oceania', '2024-05-02')
                ON CONFLICT (id) DO NOTHING;
            """)

            # 2. Insert New Products (Dimension Table)
            print("-> Inserting new products...")
            cur.execute("""
                INSERT INTO sales.products (id, name, category, unit_price)
                VALUES
                    (101, 'Cloud Data Lake Subscription', 'Software', 499.00),
                    (102, 'Enterprise Security Suite', 'Security', 750.00),
                    (103, 'AI Model Gateway License', 'Software', 299.50),
                    (104, 'Industrial Sensor Kit', 'Hardware', 150.00)
                ON CONFLICT (id) DO NOTHING;
            """)

            # 3. Insert New Orders (Fact Table - Topological Dependent)
            print("-> Inserting new orders...")
            cur.execute("""
                INSERT INTO sales.orders (id, customer_id, product_id, quantity, total_amount, status, order_date)
                VALUES
                    (201, 6, 101, 2, 998.00, 'delivered', '2024-06-01'),
                    (202, 7, 102, 1, 750.00, 'delivered', '2024-06-05'),
                    (203, 8, 104, 5, 750.00, 'shipped', '2024-06-10'),
                    (204, 9, 103, 3, 898.50, 'delivered', '2024-06-12'),
                    (205, 7, 101, 1, 499.00, 'pending', '2024-06-15')
                ON CONFLICT (id) DO NOTHING;
            """)

            # Schema guidance is owned by data/schema_docs.jsonl and load_docs().

            # Commit the transaction
            conn.commit()

    print("[SUCCESS] All tables successfully populated with new records.")


if __name__ == "__main__":
    seed_expansion()
