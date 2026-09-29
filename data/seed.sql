CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.customers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    signup_date DATE NOT NULL
);

CREATE TABLE sales.products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_price NUMERIC(10,2) NOT NULL
);

CREATE TABLE sales.orders (
    id SERIAL PRIMARY KEY,
    customer_id INT REFERENCES sales.customers(id),
    product_id INT REFERENCES sales.products(id),
    quantity INT NOT NULL,
    total_amount NUMERIC(12,2) NOT NULL,
    status TEXT NOT NULL,
    order_date DATE NOT NULL
);

INSERT INTO sales.customers (name, region, signup_date) VALUES
('Acme Retail', 'Europe', '2025-11-03'),
('Bharat Traders', 'Asia', '2026-01-15'),
('Contoso GmbH', 'Europe', '2025-09-20'),
('Delta Corp', 'North America', '2026-03-01'),
('Evergreen LLC', 'Asia', '2026-05-12');

INSERT INTO sales.products (name, category, unit_price) VALUES
('Widget Pro', 'Hardware', 49.99),
('Cloud Sync', 'Software', 19.99),
('Mega Bundle', 'Hardware', 89.50),
('Support Plan', 'Services', 29.00);

INSERT INTO sales.orders (customer_id, product_id, quantity, total_amount, status, order_date) VALUES
(1, 1, 10, 499.90, 'delivered', '2026-04-05'),
(3, 2, 20, 399.80, 'delivered', '2026-05-02'),
(5, 1, 3,  149.97, 'delivered', '2026-06-25'),
(3, 1, 7,  349.93, 'cancelled', '2026-07-20'),
(4, 3, 2,  179.00, 'delivered', '2026-08-22'),
(2, 3, 5,  447.50, 'delivered', '2026-04-11'),
(4, 4, 8,  232.00, 'pending',   '2026-06-18'),
(1, 2, 12, 239.88, 'delivered', '2026-07-14'),
(2, 4, 15, 435.00, 'delivered', '2026-08-01'),
(5, 2, 30, 599.70, 'pending',   '2026-09-10');
