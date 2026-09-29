"""Centralized database connection provider using DATABASE_URL."""
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

def get_conn() -> psycopg.Connection:
    """Open an active connection to the sales PostgreSQL database."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL environment variable is not set.")
    return psycopg.connect(url)
