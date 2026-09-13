#!/usr/bin/env python3
"""
Minimal daily ping to keep the Supabase free-tier project active.

Runs once per invocation:
  - connects to PostgreSQL using the existing DATABASE_URL
  - executes SELECT 1 (read-only, zero data touched)
  - exits 0 on success, 1 on failure

Intended to be called by a Render Cron Job once per day.
"""
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()


def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    # Mirror app.py's URL normalisation so the same driver is used.
    db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
    db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)

    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Keep-alive ping succeeded.", flush=True)
    except Exception as exc:
        # Print exception type + message; DATABASE_URL is not echoed.
        print(f"ERROR: ping failed — {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
