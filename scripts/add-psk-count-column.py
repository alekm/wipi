#!/usr/bin/env python3
"""
One-time migration: Add psk_count column to psk_sets table.
Run this if PSK import fails with "no such column: psk_sets.psk_count".

Usage (from project root):
  python scripts/add-psk-count-column.py

Or with Docker:
  docker compose exec controller python -c "
from controller.src.db.database import engine
from sqlalchemy import text, inspect
inspector = inspect(engine)
if 'psk_sets' in inspector.get_table_names():
    cols = [c['name'] for c in inspector.get_columns('psk_sets')]
    if 'psk_count' not in cols:
        with engine.connect() as conn:
            conn.execute(text('ALTER TABLE psk_sets ADD COLUMN psk_count INTEGER DEFAULT 0 NOT NULL'))
            conn.commit()
        print('Added psk_count column')
    else:
        print('psk_count already exists')
"
"""
import os
import sys

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

os.chdir(project_root)


def main():
    from sqlalchemy import create_engine, inspect, text

    db_url = os.environ.get("DATABASE_URL", "sqlite:///./data/wipi.db")
    engine = create_engine(db_url)

    inspector = inspect(engine)
    if "psk_sets" not in inspector.get_table_names():
        print("psk_sets table does not exist")
        return 1

    columns = [c["name"] for c in inspector.get_columns("psk_sets")]
    if "psk_count" in columns:
        print("psk_count column already exists")
        return 0

    print("Adding psk_count column...")
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE psk_sets ADD COLUMN psk_count INTEGER DEFAULT 0 NOT NULL"))
        conn.commit()
    print("Done. Restart the controller if it's running.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
